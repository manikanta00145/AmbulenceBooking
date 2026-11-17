from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from accounts.models import User
from ambulances.models import Ambulance, GPSLocation
from bookings.models import AmbulanceAssignment, Booking, BookingStatusHistory
from drivers.models import Driver
from patients.models import GeocodingCache, Patient


class SeedDemoDataTests(TestCase):
    def test_seed_creates_linked_workflow_and_is_idempotent(self):
        call_command("seed_demo_data", stdout=StringIO())

        booking = Booking.objects.get(submission_token="da09cd20-58ce-47ca-89fa-75665fda74b6")
        self.assertEqual(booking.status, Booking.Status.ASSIGNED)
        self.assertEqual(booking.created_by.username, "demo_call_taker")
        self.assertEqual(booking.assigned_ambulance.vehicle_number, "DEMO-AMB-001")
        self.assertEqual(booking.assigned_ambulance.driver.user.username, "demo_driver")
        self.assertTrue(
            AmbulanceAssignment.objects.filter(
                booking=booking,
                assigned_by__username="demo_dispatcher",
                released_at__isnull=True,
            ).exists()
        )
        self.assertTrue(BookingStatusHistory.objects.filter(booking=booking).exists())
        self.assertTrue(GPSLocation.objects.filter(ambulance=booking.assigned_ambulance).exists())
        self.assertTrue(Patient.objects.filter(pk=booking.patient_id).exists())
        self.assertTrue(Driver.objects.filter(user__username="demo_driver").exists())
        self.assertTrue(
            GeocodingCache.objects.filter(
                address="Fictional Demo Location, Visakhapatnam"
            ).exists()
        )

        counts = (
            User.objects.count(),
            Patient.objects.count(),
            Driver.objects.count(),
            Ambulance.objects.count(),
            Booking.objects.count(),
            AmbulanceAssignment.objects.count(),
            BookingStatusHistory.objects.count(),
            GPSLocation.objects.count(),
            GeocodingCache.objects.count(),
        )
        call_command("seed_demo_data", stdout=StringIO())
        self.assertEqual(
            counts,
            (
                User.objects.count(),
                Patient.objects.count(),
                Driver.objects.count(),
                Ambulance.objects.count(),
                Booking.objects.count(),
                AmbulanceAssignment.objects.count(),
                BookingStatusHistory.objects.count(),
                GPSLocation.objects.count(),
                GeocodingCache.objects.count(),
            ),
        )
        self.assertFalse(User.objects.get(username="demo_driver").has_usable_password())

    def test_seed_does_not_overwrite_existing_demo_account(self):
        existing = User.objects.create_user(
            username="demo_call_taker",
            password="existing-password",
            role=User.Role.CALL_TAKER,
            first_name="Keep this name",
        )
        password_hash = existing.password

        call_command("seed_demo_data", stdout=StringIO())

        existing.refresh_from_db()
        self.assertEqual(existing.first_name, "Keep this name")
        self.assertEqual(existing.password, password_hash)

    def test_existing_dispatcher_prevents_partial_seed(self):
        User.objects.create_user(
            username="existing_dispatcher",
            password="existing-password",
            role=User.Role.DISPATCHER,
        )

        with self.assertRaises(CommandError):
            call_command("seed_demo_data", stdout=StringIO())

        self.assertFalse(User.objects.filter(username="demo_call_taker").exists())
