from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from ambulances.models import Ambulance
from bookings.models import Booking
from bookings.services import assign_ambulance
from patients.models import Patient


class DispatcherPageTests(TestCase):
    def setUp(self):
        self.dispatcher = User.objects.create_user(
            username="dispatcher",
            role=User.Role.DISPATCHER,
        )

    def test_dispatcher_pages_render(self):
        self.client.force_login(self.dispatcher)
        for name in [
            "dispatcher:dashboard",
            "dispatcher:bookings",
            "dispatcher:ambulances",
        ]:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_locations_endpoint_requires_dispatcher_role(self):
        call_taker = User.objects.create_user(username="call-taker")
        self.client.force_login(call_taker)
        self.assertEqual(self.client.get(reverse("dispatcher:locations")).status_code, 403)

    def test_dashboard_renders_live_dispatch_operations_panel(self):
        self.client.force_login(self.dispatcher)

        response = self.client.get(reverse("dispatcher:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Emergency operations")
        self.assertContains(response, "Map focus: Visakhapatnam")
        self.assertContains(response, "dispatcher-dashboard.css")
        self.assertContains(response, "stat-completed")

    def test_live_locations_returns_real_fleet_and_active_case_details(self):
        driver = User.objects.create_user(
            username="dispatch-driver",
            role=User.Role.DRIVER,
            phone_number="555-0199",
        )
        ambulance = Ambulance.objects.create(
            vehicle_number="AMB-LIVE-1",
            driver=driver.driver_profile,
            latitude=17.7,
            longitude=83.2,
            location_updated_at=timezone.now(),
        )
        no_gps_driver = User.objects.create_user(
            username="dispatch-driver-no-gps",
            role=User.Role.DRIVER,
        )
        no_gps_ambulance = Ambulance.objects.create(
            vehicle_number="AMB-NO-GPS",
            driver=no_gps_driver.driver_profile,
        )
        call_taker = User.objects.create_user(username="dispatch-call-taker")
        patient = Patient.objects.create(
            name="Live Case Patient",
            contact_number="555-0177",
        )
        booking = Booking.objects.create(
            patient=patient,
            number_of_patients=2,
            emergency_type="Medical",
            location_address="Visakhapatnam test address",
            latitude=17.71,
            longitude=83.21,
            created_by=call_taker,
        )
        assigned_driver = User.objects.create_user(
            username="dispatch-driver-assigned",
            role=User.Role.DRIVER,
        )
        assigned_ambulance = Ambulance.objects.create(
            vehicle_number="AMB-LIVE-2",
            driver=assigned_driver.driver_profile,
            latitude=17.72,
            longitude=83.22,
            location_updated_at=timezone.now(),
        )
        assigned_patient = Patient.objects.create(
            name="Assigned Case Patient",
            contact_number="555-0188",
        )
        assigned_booking = Booking.objects.create(
            patient=assigned_patient,
            number_of_patients=1,
            emergency_type="Trauma",
            location_address="Another Visakhapatnam test address",
            latitude=17.73,
            longitude=83.23,
            created_by=call_taker,
        )
        assign_ambulance(
            booking_id=assigned_booking.pk,
            ambulance_id=assigned_ambulance.pk,
            dispatcher=self.dispatcher,
        )
        self.client.force_login(self.dispatcher)

        response = self.client.get(reverse("dispatcher:locations"))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["locations"]), 3)
        live_location = next(item for item in data["locations"] if item["id"] == ambulance.pk)
        missing_location = next(
            item for item in data["locations"] if item["id"] == no_gps_ambulance.pk
        )
        self.assertEqual(live_location["driver_phone"], "555-0199")
        self.assertFalse(live_location["gps_stale"])
        self.assertIsNone(missing_location["latitude"])
        self.assertTrue(missing_location["gps_stale"])

        self.assertEqual(len(data["emergencies"]), 2)
        case = next(item for item in data["emergencies"] if item["id"] == str(booking.pk))
        self.assertEqual(case["id"], str(booking.pk))
        self.assertEqual(case["patient"], "Live Case Patient")
        self.assertEqual(case["number_of_patients"], 2)
        self.assertEqual(case["status"], Booking.Status.PENDING)
        self.assertIsNone(case["ambulance_id"])
        self.assertEqual(
            case["suggested_ambulance"]["vehicle_number"],
            ambulance.vehicle_number,
        )
        assigned_case = next(
            item for item in data["emergencies"] if item["id"] == str(assigned_booking.pk)
        )
        self.assertEqual(assigned_case["ambulance_id"], assigned_ambulance.pk)
        self.assertEqual(assigned_case["driver"], assigned_driver.driver_profile.driver_name)
        self.assertEqual(data["stats"]["total_ambulances"], 3)
        self.assertEqual(data["stats"]["active_emergencies"], 2)
