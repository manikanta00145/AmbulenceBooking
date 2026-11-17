import hashlib
import uuid
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from ambulances.models import Ambulance, GPSLocation
from bookings.models import Booking
from bookings.services import assign_ambulance
from drivers.models import Driver
from patients.models import GeocodingCache, NominatimRequestState, Patient


DEMO_BOOKING_TOKEN = uuid.UUID("da09cd20-58ce-47ca-89fa-75665fda74b6")
DEMO_LATITUDE = Decimal("17.6868000")
DEMO_LONGITUDE = Decimal("83.2185000")
DEMO_ADDRESS = "Fictional Demo Location, Visakhapatnam"


class Command(BaseCommand):
    help = "Create idempotent, fictional records for the project workflows."

    @transaction.atomic
    def handle(self, *_args, **_options):
        _ = (_args, _options)
        dispatcher_name = "demo_dispatcher"
        if (
            not User.objects.filter(username=dispatcher_name).exists()
            and User.objects.filter(role=User.Role.DISPATCHER).exists()
        ):
            raise CommandError(
                "A dispatcher already exists; demo data was not added because "
                "the project permits only one dispatcher."
            )

        call_taker = self._get_demo_user(
            username="demo_call_taker",
            role=User.Role.CALL_TAKER,
            first_name="Demo",
            last_name="Call Taker",
            phone_number="+1-202-555-0101",
        )
        dispatcher = self._get_demo_user(
            username=dispatcher_name,
            role=User.Role.DISPATCHER,
            first_name="Demo",
            last_name="Dispatcher",
            phone_number="+1-202-555-0102",
        )
        driver_user = self._get_demo_user(
            username="demo_driver",
            role=User.Role.DRIVER,
            first_name="Demo",
            last_name="Driver",
            phone_number="+1-202-555-0103",
        )

        driver, _ = Driver.objects.get_or_create(
            user=driver_user,
            defaults={
                "driver_name": "Fictional Demo Driver",
                "phone_number": driver_user.phone_number,
                "license_number": "DEMO-DRIVER-LICENSE-001",
            },
        )
        ambulance, _ = Ambulance.objects.get_or_create(
            vehicle_number="DEMO-AMB-001",
            defaults={
                "driver": driver,
                "latitude": DEMO_LATITUDE,
                "longitude": DEMO_LONGITUDE,
                "location_updated_at": timezone.now(),
                "availability_status": Ambulance.Availability.AVAILABLE,
                "patient_status": Ambulance.PatientStatus.OFF,
            },
        )
        if ambulance.driver_id != driver.pk:
            raise CommandError(
                "DEMO-AMB-001 already belongs to another driver; no records were changed."
            )

        patient, _ = Patient.objects.get_or_create(
            name="Fictional Demo Patient",
            contact_number="DEMO-000-0001",
            defaults={
                "relationship": "Demo record",
                "gender": "Other",
                "age": 34,
            },
        )
        booking, _ = Booking.objects.get_or_create(
            submission_token=DEMO_BOOKING_TOKEN,
            defaults={
                "patient": patient,
                "number_of_patients": 1,
                "emergency_type": "Demo emergency",
                "location_address": "Fictional Demo Location, Visakhapatnam",
                "latitude": DEMO_LATITUDE,
                "longitude": DEMO_LONGITUDE,
                "location_confirmed": True,
                "created_by": call_taker,
            },
        )
        if booking.patient_id != patient.pk or booking.created_by_id != call_taker.pk:
            raise CommandError(
                "The demo booking token is already used by another record; "
                "no records were changed."
            )

        GPSLocation.objects.get_or_create(
            ambulance=ambulance,
            latitude=DEMO_LATITUDE,
            longitude=DEMO_LONGITUDE,
        )
        GeocodingCache.objects.get_or_create(
            address_key=hashlib.sha256(
                " ".join(DEMO_ADDRESS.casefold().split()).encode("utf-8")
            ).hexdigest(),
            defaults={
                "address": DEMO_ADDRESS,
                "latitude": DEMO_LATITUDE,
                "longitude": DEMO_LONGITUDE,
                "display_name": "Fictional Demo Location",
                "expires_at": timezone.now() + timedelta(days=30),
            },
        )
        NominatimRequestState.objects.get_or_create(pk=1)

        if (
            booking.status == Booking.Status.PENDING
            and not booking.assigned_ambulance_id
        ):
            assign_ambulance(
                booking_id=booking.pk,
                ambulance_id=ambulance.pk,
                dispatcher=dispatcher,
            )
        elif booking.assigned_ambulance_id != ambulance.pk:
            raise CommandError(
                "The demo booking is not linked to the demo ambulance; "
                "no existing records were overwritten."
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Fictional demo users, patient, driver, ambulance, booking, "
                "assignment, GPS, and geocoding records are ready."
            )
        )

    def _get_demo_user(self, *, username, role, first_name, last_name, phone_number):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "role": role,
                "first_name": first_name,
                "last_name": last_name,
                "phone_number": phone_number,
                "is_active": True,
                "approval_status": User.ApprovalStatus.APPROVED,
            },
        )
        if user.role != role:
            raise CommandError(
                f"'{username}' exists with a different role; no records were changed."
            )
        if not user.is_active or user.approval_status != User.ApprovalStatus.APPROVED:
            raise CommandError(
                f"'{username}' is not active and approved; it was not modified."
            )
        if created:
            user.set_unusable_password()
            user.save(update_fields=["password"])
        return user
