from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from ambulances.models import Ambulance
from ambulances.services import GPS_MAX_AGE, publish_ambulance_update
from bookings.models import AmbulanceAssignment, Booking, BookingStatusHistory


@transaction.atomic
def assign_ambulance(*, booking_id, ambulance_id, dispatcher):
    if dispatcher.role != dispatcher.Role.DISPATCHER:
        raise PermissionDenied("Only the authorized dispatcher can assign ambulances.")

    booking = Booking.objects.select_for_update().get(pk=booking_id)
    ambulance = Ambulance.objects.select_for_update().get(pk=ambulance_id)

    if booking.status != Booking.Status.PENDING or booking.assigned_ambulance_id:
        raise ValidationError("This booking has already been assigned or is no longer pending.")
    if (
        booking.latitude is None
        or booking.longitude is None
        or not booking.location_confirmed
    ):
        raise ValidationError(
            "The patient location must be confirmed before dispatch."
        )
    if (
        ambulance.availability_status != Ambulance.Availability.AVAILABLE
        or ambulance.patient_status != Ambulance.PatientStatus.OFF
    ):
        raise ValidationError("The selected ambulance is no longer available.")
    if ambulance.latitude is None or ambulance.longitude is None:
        raise ValidationError("The selected ambulance has no GPS coordinates.")
    if ambulance.location_updated_at < timezone.now() - GPS_MAX_AGE:
        raise ValidationError("The selected ambulance GPS location is stale.")
    if (
        not ambulance.driver.user.is_active
        or ambulance.driver.user.role != ambulance.driver.user.Role.DRIVER
    ):
        raise ValidationError("The selected ambulance does not have an active driver.")
    if AmbulanceAssignment.objects.filter(ambulance=ambulance, released_at__isnull=True).exists():
        raise ValidationError("The selected ambulance already has an active assignment.")

    old_status = booking.status
    booking.assigned_ambulance = ambulance
    booking.status = Booking.Status.ASSIGNED
    booking.save(update_fields=["assigned_ambulance", "status"])
    ambulance.availability_status = Ambulance.Availability.UNAVAILABLE
    ambulance.save(update_fields=["availability_status"])
    publish_ambulance_update(ambulance)
    AmbulanceAssignment.objects.create(
        booking=booking,
        ambulance=ambulance,
        assigned_by=dispatcher,
    )
    BookingStatusHistory.objects.create(
        booking=booking,
        old_status=old_status,
        new_status=booking.status,
        changed_by=dispatcher,
    )
    return booking


@transaction.atomic
def record_status_change(*, booking, new_status, actor, note=""):
    locked_booking = Booking.objects.select_for_update().get(pk=booking.pk)
    old_status = locked_booking.status
    if old_status == new_status:
        return locked_booking

    locked_booking.status = new_status
    locked_booking.save(update_fields=["status"])
    BookingStatusHistory.objects.create(
        booking=locked_booking,
        old_status=old_status,
        new_status=new_status,
        changed_by=actor,
        note=note,
    )
    if new_status in {Booking.Status.COMPLETED, Booking.Status.CANCELLED}:
        active_assignment = AmbulanceAssignment.objects.select_for_update().filter(
            booking=locked_booking,
            released_at__isnull=True,
        ).first()
        if active_assignment:
            active_assignment.released_at = timezone.now()
            active_assignment.save(update_fields=["released_at"])
            ambulance = Ambulance.objects.select_for_update().get(
                pk=active_assignment.ambulance_id
            )
            ambulance.availability_status = Ambulance.Availability.AVAILABLE
            ambulance.patient_status = Ambulance.PatientStatus.OFF
            ambulance.save(update_fields=["availability_status", "patient_status"])
            publish_ambulance_update(ambulance)
    return locked_booking
