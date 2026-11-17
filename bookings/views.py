from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render

from bookings.models import Booking


@login_required
def detail(request, booking_id):
    booking = get_object_or_404(
        Booking.objects.select_related("patient", "created_by", "assigned_ambulance"),
        pk=booking_id,
    )
    visible_to_call_taker = (
        request.user.role == request.user.Role.CALL_TAKER
        and booking.created_by_id == request.user.pk
    )
    visible_to_assigned_driver = (
        request.user.role == request.user.Role.DRIVER
        and booking.assigned_ambulance_id is not None
        and booking.assigned_ambulance.driver.user_id == request.user.pk
    )
    visible_to_patient = (
        request.user.role == request.user.Role.PATIENT
        and (
            booking.created_by_id == request.user.pk
            or (booking.patient_id and booking.patient.user_id == request.user.pk)
        )
    )
    if not (
        request.user.is_superuser
        or request.user.role == request.user.Role.DISPATCHER
        or visible_to_call_taker
        or visible_to_assigned_driver
        or visible_to_patient
    ):
        raise PermissionDenied
    return render(request, "bookings/booking_details.html", {"booking": booking})
