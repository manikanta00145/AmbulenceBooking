from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from ambulances.models import Ambulance
from ambulances.services import (
    calculate_distance,
    is_gps_fresh,
    publish_ambulance_update,
)
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
        driver__user=driver,
    )
    if not AmbulanceAssignment.objects.filter(
        booking=booking,
        ambulance=ambulance,
        released_at__isnull=True,
    ).exists():
        raise ValidationError("This ambulance assignment is no longer active.")
    if new_status not in DRIVER_TRANSITIONS.get(booking.status, []):
        raise ValidationError("That status change is not allowed.")

    if new_status == Booking.Status.ARRIVED:
        if (
            not booking.location_confirmed
            or booking.latitude is None
            or booking.longitude is None
            or not -90 <= booking.latitude <= 90
            or not -180 <= booking.longitude <= 180
        ):
            raise ValidationError("The patient destination must be confirmed before arrival.")
        if (
            not is_gps_fresh(ambulance)
        ):
            raise ValidationError("A recent ambulance GPS location is required to mark arrival.")
        accuracy_meters = (
            float(ambulance.location_accuracy_meters)
            if ambulance.location_accuracy_meters is not None
            else None
        )
        if (
            accuracy_meters is None
            or accuracy_meters > settings.DRIVER_ARRIVAL_MAX_ACCURACY_METERS
        ):
            raise ValidationError(
                "GPS accuracy is insufficient to verify arrival at the destination."
            )
        distance_meters = calculate_distance(
            ambulance.latitude,
            ambulance.longitude,
            booking.latitude,
            booking.longitude,
        ) * 1000
        if (
            distance_meters + accuracy_meters
            > settings.DRIVER_ARRIVAL_RADIUS_METERS
        ):
            raise ValidationError(
                "The ambulance is not within the configured arrival radius."
            )

    updated_booking = record_status_change(
        booking=booking,
        new_status=new_status,
        actor=driver,
    )
    if new_status == Booking.Status.PATIENT_PICKED_UP:
        ambulance.patient_status = Ambulance.PatientStatus.ON
        ambulance.save(update_fields=["patient_status"])
        publish_ambulance_update(ambulance)
    elif new_status not in {Booking.Status.COMPLETED, Booking.Status.CANCELLED}:
        publish_ambulance_update(ambulance)
    return updated_booking


@transaction.atomic
def update_availability(*, driver, availability_status):
    if driver.role != driver.Role.DRIVER:
        raise PermissionDenied("Only ambulance drivers can update vehicle availability.")
    if availability_status not in Ambulance.Availability.values:
        raise ValidationError("Select a valid availability status.")

    ambulance = Ambulance.objects.select_for_update().get(driver__user=driver)
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
