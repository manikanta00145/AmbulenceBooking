from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from ambulances.models import Ambulance
from ambulances.services import publish_ambulance_update
from bookings.models import AmbulanceAssignment, Booking
from bookings.services import record_status_change
from drivers.forms import DRIVER_TRANSITIONS


@transaction.atomic
def update_booking_status(*, booking_id, new_status, driver):
    if driver.role != driver.Role.DRIVER:
        raise PermissionDenied("Only the assigned driver can update this booking.")
    booking = Booking.objects.select_for_update().get(pk=booking_id)
    if booking.assigned_ambulance_id is None:
        raise ValidationError("This booking has no assigned ambulance.")
    ambulance = Ambulance.objects.select_for_update().get(
        pk=booking.assigned_ambulance_id,
        driver=driver,
    )
    if not AmbulanceAssignment.objects.filter(
        booking=booking,
        ambulance=ambulance,
        released_at__isnull=True,
    ).exists():
        raise ValidationError("This ambulance assignment is no longer active.")
    if new_status not in DRIVER_TRANSITIONS.get(booking.status, []):
        raise ValidationError("That status change is not allowed.")

    updated_booking = record_status_change(
        booking=booking,
        new_status=new_status,
        actor=driver,
    )
    if new_status == Booking.Status.PATIENT_PICKED_UP:
        ambulance.patient_status = Ambulance.PatientStatus.ON
        ambulance.save(update_fields=["patient_status"])
        publish_ambulance_update(ambulance)
    return updated_booking


@transaction.atomic
def update_availability(*, driver, availability_status):
    if driver.role != driver.Role.DRIVER:
        raise PermissionDenied("Only ambulance drivers can update vehicle availability.")
    if availability_status not in Ambulance.Availability.values:
        raise ValidationError("Select a valid availability status.")

    ambulance = Ambulance.objects.select_for_update().get(driver=driver)
    if AmbulanceAssignment.objects.filter(
        ambulance=ambulance,
        released_at__isnull=True,
    ).exists():
        raise ValidationError("Availability cannot be changed while an assignment is active.")
    if (
        availability_status == Ambulance.Availability.AVAILABLE
        and ambulance.patient_status != Ambulance.PatientStatus.OFF
    ):
        raise ValidationError("An ambulance with a patient onboard cannot be marked available.")
    ambulance.availability_status = availability_status
    ambulance.save(update_fields=["availability_status"])
    publish_ambulance_update(ambulance)
    return ambulance
