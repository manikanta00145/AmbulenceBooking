from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from ambulances.models import Ambulance
from bookings.models import AmbulanceAssignment, Booking
from bookings.services import assign_ambulance
from drivers.services import update_availability, update_booking_status
from patients.models import Patient


class DriverLoginPageTests(TestCase):
    def test_homepage_driver_login_link_uses_driver_login_page(self):
        response = self.client.get(reverse("home"))
        driver_login_url = reverse("drivers:login")
        driver_dashboard_url = reverse("drivers:dashboard")

        self.assertContains(
            response,
            f'href="{driver_login_url}?next={driver_dashboard_url}"',
        )

    def test_driver_login_page_uses_driver_specific_ui(self):
        response = self.client.get(reverse("drivers:login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sign in to continue to your driver dashboard.")
        self.assertContains(response, "css/portal-auth.css")
        self.assertContains(response, "js/portal-auth.js")

    def test_driver_login_authenticates_and_redirects_to_dashboard(self):
        driver = User.objects.create_user(
            username="driver-login",
            password="Test-pass123!",
            role=User.Role.DRIVER,
        )

        response = self.client.post(
            reverse("drivers:login"),
            {
                "username": driver.username,
                "password": "Test-pass123!",
                "next": reverse("drivers:dashboard"),
            },
        )

        self.assertRedirects(
            response,
            reverse("drivers:dashboard"),
            fetch_redirect_response=False,
        )
        self.assertEqual(int(self.client.session["_auth_user_id"]), driver.pk)


class DriverBookingStatusTests(TestCase):
    def setUp(self):
        self.dispatcher = User.objects.create_user(
            username="dispatch",
            role=User.Role.DISPATCHER,
        )
        self.driver = User.objects.create_user(username="driver", role=User.Role.DRIVER)
        call_taker = User.objects.create_user(username="caller")
        patient = Patient.objects.create(
            name="Case",
            contact_number="555-0123",
            age=20,
            gender="Other",
        )
        self.booking = Booking.objects.create(
            patient=patient,
            number_of_patients=1,
            emergency_type="Medical",
            location_address="1 Main Street",
            created_by=call_taker,
        )
        self.ambulance = Ambulance.objects.create(
            vehicle_number="AMB-002",
            driver=self.driver.driver_profile,
            latitude=12.0,
            longitude=77.0,
            location_updated_at=timezone.now(),
        )
        assign_ambulance(
            booking_id=self.booking.pk,
            ambulance_id=self.ambulance.pk,
            dispatcher=self.dispatcher,
        )

    def test_driver_status_workflow_updates_vehicle_and_releases_assignment(self):
        for status in [
            Booking.Status.ACCEPTED,
            Booking.Status.EN_ROUTE,
            Booking.Status.ARRIVED,
            Booking.Status.PATIENT_PICKED_UP,
        ]:
            update_booking_status(
                booking_id=self.booking.pk,
                new_status=status,
                driver=self.driver,
            )
        self.ambulance.refresh_from_db()
        self.assertEqual(self.ambulance.patient_status, Ambulance.PatientStatus.ON)

        update_booking_status(
            booking_id=self.booking.pk,
            new_status=Booking.Status.COMPLETED,
            driver=self.driver,
        )
        self.ambulance.refresh_from_db()
        assignment = AmbulanceAssignment.objects.get(booking=self.booking)
        self.assertIsNotNone(assignment.released_at)
        self.assertEqual(self.ambulance.patient_status, Ambulance.PatientStatus.OFF)
        self.assertEqual(self.ambulance.availability_status, Ambulance.Availability.AVAILABLE)

    def test_driver_cannot_skip_statuses(self):
        with self.assertRaises(ValidationError):
            update_booking_status(
                booking_id=self.booking.pk,
                new_status=Booking.Status.ARRIVED,
                driver=self.driver,
            )

    def test_driver_pages_render_and_location_updates(self):
        self.client.force_login(self.driver)
        self.assertEqual(self.client.get(reverse("drivers:dashboard")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("drivers:booking", args=[self.booking.pk])).status_code,
            200,
        )
        response = self.client.post(
            reverse("drivers:location"),
            {"latitude": "13.25", "longitude": "78.5"},
        )
        self.assertEqual(response.status_code, 200)
        self.ambulance.refresh_from_db()
        self.assertEqual(float(self.ambulance.latitude), 13.25)

    def test_driver_without_registered_ambulance_sees_setup_instructions(self):
        driver = User.objects.create_user(username="unassigned-driver", role=User.Role.DRIVER)
        self.client.force_login(driver)

        response = self.client.get(reverse("drivers:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "drivers/no_ambulance.html")
        self.assertContains(response, "No ambulance is registered for your account")
        self.assertContains(response, "dispatch coordinator")

    def test_driver_can_toggle_availability_only_without_active_assignment(self):
        with self.assertRaises(ValidationError):
            update_availability(
                driver=self.driver,
                availability_status=Ambulance.Availability.AVAILABLE,
            )
        self.booking.status = Booking.Status.CANCELLED
        self.booking.save(update_fields=["status"])
        assignment = self.booking.assignments.get(released_at__isnull=True)
        assignment.released_at = timezone.now()
        assignment.save(update_fields=["released_at"])
        update_availability(
            driver=self.driver,
            availability_status=Ambulance.Availability.UNAVAILABLE,
        )
        self.ambulance.refresh_from_db()
        self.assertEqual(self.ambulance.availability_status, Ambulance.Availability.UNAVAILABLE)
