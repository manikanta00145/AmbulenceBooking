from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from ambulances.models import Ambulance, GPSLocation
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
            latitude=12.0,
            longitude=77.0,
            location_confirmed=True,
            created_by=call_taker,
        )
        self.ambulance = Ambulance.objects.create(
            vehicle_number="AMB-002",
            driver=self.driver.driver_profile,
            latitude=12.0,
            longitude=77.0,
            location_updated_at=timezone.now(),
            location_accuracy_meters=5,
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
        dashboard_response = self.client.get(reverse("drivers:dashboard"))
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertContains(dashboard_response, "data-patient-latitude")
        self.assertContains(dashboard_response, "Navigate to patient")
        booking_response = self.client.get(
            reverse("drivers:booking", args=[self.booking.pk])
        )
        self.assertEqual(booking_response.status_code, 200)
        self.assertContains(booking_response, "Open pickup map")
        self.assertContains(booking_response, "Open live navigation")
        self.ambulance.location_updated_at = timezone.now() - timedelta(hours=1)
        self.ambulance.save(update_fields=["location_updated_at"])
        response = self.client.post(
            reverse("drivers:location"),
            {
                "latitude": "13.25",
                "longitude": "78.5",
                "accuracy_meters": "5",
                "observed_at": str(timezone.now().timestamp() * 1000),
                "booking_id": str(self.booking.pk),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.ambulance.refresh_from_db()
        self.assertEqual(float(self.ambulance.latitude), 13.25)
        self.assertEqual(float(self.ambulance.location_accuracy_meters), 5)
        self.assertEqual(GPSLocation.objects.filter(ambulance=self.ambulance).count(), 1)

    def test_location_endpoint_rejects_invalid_coordinates_and_stale_fix(self):
        self.client.force_login(self.driver)
        url = reverse("drivers:location")
        payload = {
            "longitude": "77.0",
            "accuracy_meters": "5",
            "observed_at": str(timezone.now().timestamp() * 1000),
            "booking_id": str(self.booking.pk),
        }

        invalid = self.client.post(url, {**payload, "latitude": "91"})
        stale = self.client.post(
            url,
            {
                **payload,
                "latitude": "12.0",
                "observed_at": str(
                    (timezone.now() - timedelta(minutes=6)).timestamp() * 1000
                ),
            },
        )

        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(stale.status_code, 400)
        self.assertEqual(GPSLocation.objects.filter(ambulance=self.ambulance).count(), 0)

    def test_driver_cannot_submit_gps_for_another_drivers_booking(self):
        other_driver = User.objects.create_user(
            username="gps-owner-mismatch",
            role=User.Role.DRIVER,
        )
        other_ambulance = Ambulance.objects.create(
            vehicle_number="AMB-OTHER-GPS",
            driver=other_driver.driver_profile,
            latitude=12.1,
            longitude=77.1,
            location_updated_at=timezone.now() - timedelta(seconds=10),
            location_accuracy_meters=5,
        )
        self.client.force_login(other_driver)

        response = self.client.post(
            reverse("drivers:location"),
            {
                "latitude": "12.2",
                "longitude": "77.2",
                "accuracy_meters": "5",
                "observed_at": str(timezone.now().timestamp() * 1000),
                "booking_id": str(self.booking.pk),
            },
        )

        self.assertEqual(response.status_code, 400)
        other_ambulance.refresh_from_db()
        self.assertEqual(float(other_ambulance.latitude), 12.1)

    def test_location_endpoint_rejects_released_assignment(self):
        assignment = AmbulanceAssignment.objects.get(
            booking=self.booking,
            released_at__isnull=True,
        )
        assignment.released_at = timezone.now()
        assignment.save(update_fields=["released_at"])
        self.client.force_login(self.driver)

        response = self.client.post(
            reverse("drivers:location"),
            {
                "latitude": "12.2",
                "longitude": "77.2",
                "accuracy_meters": "5",
                "observed_at": str(timezone.now().timestamp() * 1000),
                "booking_id": str(self.booking.pk),
            },
        )

        self.assertEqual(response.status_code, 400)
        self.ambulance.refresh_from_db()
        self.assertEqual(float(self.ambulance.latitude), 12.0)

    @override_settings(
        DRIVER_GPS_MIN_INTERVAL_SECONDS=5,
        DRIVER_GPS_MIN_MOVEMENT_METERS=15,
        DRIVER_GPS_HEARTBEAT_SECONDS=60,
    )
    def test_location_updates_are_throttled_by_interval_movement_and_heartbeat(self):
        self.client.force_login(self.driver)
        url = reverse("drivers:location")

        def submit(latitude, longitude):
            return self.client.post(
                url,
                {
                    "latitude": str(latitude),
                    "longitude": str(longitude),
                    "accuracy_meters": "5",
                    "observed_at": str(timezone.now().timestamp() * 1000),
                    "booking_id": str(self.booking.pk),
                },
            )

        self.assertFalse(submit(12.1, 77.1).json()["updated"])
        self.ambulance.location_updated_at = timezone.now() - timedelta(seconds=10)
        self.ambulance.save(update_fields=["location_updated_at"])
        self.assertFalse(submit(12.0, 77.0).json()["updated"])
        self.ambulance.location_updated_at = timezone.now() - timedelta(seconds=61)
        self.ambulance.save(update_fields=["location_updated_at"])
        self.assertTrue(submit(12.0, 77.0).json()["updated"])
        self.assertEqual(GPSLocation.objects.filter(ambulance=self.ambulance).count(), 1)

    def test_navigation_page_shows_only_fresh_gps_and_confirmed_destination(self):
        self.client.force_login(self.driver)
        url = reverse("drivers:navigation", args=[self.booking.pk])

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="driver-navigation-map"')
        self.assertContains(response, 'data-start-latitude="12.0"')
        self.assertContains(response, 'data-destination-latitude="12.0"')

        self.ambulance.latitude = None
        self.ambulance.longitude = None
        self.ambulance.save(update_fields=["latitude", "longitude"])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No recent valid ambulance GPS location is available.")
        self.assertContains(response, 'data-start-latitude=""')

    def test_navigation_blocks_unconfirmed_destination(self):
        self.booking.location_confirmed = False
        self.booking.save(update_fields=["location_confirmed"])
        self.client.force_login(self.driver)

        response = self.client.get(
            reverse("drivers:navigation", args=[self.booking.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Destination not verified")
        self.assertNotContains(response, 'id="driver-navigation-map"')

    def test_arrival_requires_fresh_accurate_gps_within_radius(self):
        update_booking_status(
            booking_id=self.booking.pk,
            new_status=Booking.Status.ACCEPTED,
            driver=self.driver,
        )
        update_booking_status(
            booking_id=self.booking.pk,
            new_status=Booking.Status.EN_ROUTE,
            driver=self.driver,
        )
        self.ambulance.latitude = 12.01
        self.ambulance.location_updated_at = timezone.now()
        self.ambulance.location_accuracy_meters = 5
        self.ambulance.save(
            update_fields=[
                "latitude",
                "location_updated_at",
                "location_accuracy_meters",
            ]
        )

        with self.assertRaisesMessage(ValidationError, "arrival radius"):
            update_booking_status(
                booking_id=self.booking.pk,
                new_status=Booking.Status.ARRIVED,
                driver=self.driver,
            )
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.EN_ROUTE)

    def test_arrival_rejects_stale_or_inaccurate_gps(self):
        update_booking_status(
            booking_id=self.booking.pk,
            new_status=Booking.Status.ACCEPTED,
            driver=self.driver,
        )
        update_booking_status(
            booking_id=self.booking.pk,
            new_status=Booking.Status.EN_ROUTE,
            driver=self.driver,
        )
        self.ambulance.location_accuracy_meters = 100
        self.ambulance.save(update_fields=["location_accuracy_meters"])
        with self.assertRaisesMessage(ValidationError, "GPS accuracy is insufficient"):
            update_booking_status(
                booking_id=self.booking.pk,
                new_status=Booking.Status.ARRIVED,
                driver=self.driver,
            )

        self.ambulance.location_accuracy_meters = 5
        self.ambulance.location_updated_at = timezone.now() - timedelta(minutes=6)
        self.ambulance.save(
            update_fields=["location_accuracy_meters", "location_updated_at"]
        )
        with self.assertRaisesMessage(ValidationError, "recent ambulance GPS"):
            update_booking_status(
                booking_id=self.booking.pk,
                new_status=Booking.Status.ARRIVED,
                driver=self.driver,
            )

    def test_navigation_does_not_render_stale_gps_as_a_live_start_point(self):
        self.ambulance.location_updated_at = timezone.now() - timedelta(minutes=6)
        self.ambulance.save(update_fields=["location_updated_at"])
        self.client.force_login(self.driver)

        response = self.client.get(
            reverse("drivers:navigation", args=[self.booking.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "not shown as live")
        self.assertContains(response, 'data-start-latitude=""')

    def test_navigation_requires_driver_ownership_and_active_assignment(self):
        other_driver = User.objects.create_user(
            username="other-navigation-driver",
            role=User.Role.DRIVER,
        )
        self.client.force_login(other_driver)
        response = self.client.get(
            reverse("drivers:navigation", args=[self.booking.pk])
        )
        self.assertEqual(response.status_code, 404)

        self.client.force_login(self.driver)
        assignment = self.booking.assignments.get(released_at__isnull=True)
        assignment.released_at = timezone.now()
        assignment.save(update_fields=["released_at"])
        response = self.client.get(
            reverse("drivers:navigation", args=[self.booking.pk])
        )
        self.assertEqual(response.status_code, 404)

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
