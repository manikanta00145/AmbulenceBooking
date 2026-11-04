from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from ambulances.models import Ambulance
from bookings.models import AmbulanceAssignment, Booking, BookingStatusHistory
from bookings.services import assign_ambulance
from patients.models import Patient


class AmbulanceAssignmentTests(TestCase):
    def setUp(self):
        self.dispatcher = User.objects.create_user(
            username="dispatch",
            role=User.Role.DISPATCHER,
        )
        self.driver = User.objects.create_user(username="driver", role=User.Role.DRIVER)
        self.call_taker = User.objects.create_user(username="caller")
        self.patient = Patient.objects.create(
            name="Case",
            contact_number="555-0123",
            age=20,
            gender="Other",
        )
        self.booking = Booking.objects.create(
            patient=self.patient,
            number_of_patients=1,
            emergency_type="Medical",
            location_address="1 Main Street",
            latitude=12.0,
            longitude=77.0,
            created_by=self.call_taker,
        )
        self.ambulance = Ambulance.objects.create(
            vehicle_number="AMB-001",
            driver=self.driver.driver_profile,
            latitude=12.01,
            longitude=77.0,
            location_updated_at=timezone.now(),
        )

    def test_assignment_reserves_ambulance_and_records_history(self):
        updated = assign_ambulance(
            booking_id=self.booking.pk,
            ambulance_id=self.ambulance.pk,
            dispatcher=self.dispatcher,
        )
        self.ambulance.refresh_from_db()
        self.assertEqual(updated.status, Booking.Status.ASSIGNED)
        self.assertEqual(updated.assigned_ambulance, self.ambulance)
        self.assertEqual(self.ambulance.availability_status, Ambulance.Availability.UNAVAILABLE)
        self.assertTrue(
            AmbulanceAssignment.objects.filter(
                booking=updated,
                ambulance=self.ambulance,
                released_at__isnull=True,
            ).exists()
        )
        self.assertEqual(
            BookingStatusHistory.objects.filter(booking=updated).latest("changed_at").new_status,
            Booking.Status.ASSIGNED,
        )

    def test_call_taker_cannot_assign_ambulance(self):
        with self.assertRaises(PermissionDenied):
            assign_ambulance(
                booking_id=self.booking.pk,
                ambulance_id=self.ambulance.pk,
                dispatcher=self.call_taker,
            )

    def test_stale_location_cannot_be_assigned(self):
        self.ambulance.location_updated_at = timezone.now() - timedelta(minutes=10)
        self.ambulance.save(update_fields=["location_updated_at"])
        with self.assertRaises(ValidationError):
            assign_ambulance(
                booking_id=self.booking.pk,
                ambulance_id=self.ambulance.pk,
                dispatcher=self.dispatcher,
            )
