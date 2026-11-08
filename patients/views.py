from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import redirect, render

from accounts.decorators import role_required
from bookings.models import Booking, BookingStatusHistory
from patients.forms import CallTakerEmergencyRequestForm, EmergencyRequestForm


@login_required
@role_required("CALL_TAKER", "DISPATCHER")
def create_request(request):
    is_call_taker = request.user.role == request.user.Role.CALL_TAKER
    form_class = CallTakerEmergencyRequestForm if is_call_taker else EmergencyRequestForm
    if request.method == "POST":
        form = form_class(request.POST)
        if form.is_valid():
            with transaction.atomic():
                patient = form.save_patient()
                booking = Booking.objects.create(
                    patient=patient,
                    number_of_patients=form.cleaned_data["number_of_patients"],
                    emergency_type=(
                        form.cleaned_data["emergency_type"]
                        if not is_call_taker
                        else "Emergency"
                    ),
                    location_address=form.cleaned_data["location_address"],
                    latitude=form.cleaned_data.get("latitude"),
                    longitude=form.cleaned_data.get("longitude"),
                    created_by=request.user,
                )
                BookingStatusHistory.objects.create(
                    booking=booking,
                    new_status=booking.status,
                    changed_by=request.user,
                )
            messages.success(request, f"Emergency request {booking.pk} has been recorded.")
            return redirect("bookings:detail", booking_id=booking.pk)
    else:
        form = form_class()
    if is_call_taker:
        user_bookings = Booking.objects.filter(created_by=request.user)
        pending_statuses = [
            Booking.Status.PENDING,
            Booking.Status.ASSIGNED,
            Booking.Status.ACCEPTED,
            Booking.Status.EN_ROUTE,
            Booking.Status.ARRIVED,
            Booking.Status.PATIENT_PICKED_UP,
        ]
        dashboard_stats = user_bookings.aggregate(
            solved_count=Count(
                "booking_id",
                filter=Q(status=Booking.Status.COMPLETED),
            ),
            pending_count=Count(
                "booking_id",
                filter=Q(status__in=pending_statuses),
            ),
            total_count=Count("booking_id"),
        )
        pending_cases = (
            user_bookings.filter(status__in=pending_statuses)
            .select_related("patient")
            .order_by("-requested_at")[:8]
        )
        case_history = (
            user_bookings.select_related("patient")
            .order_by("-requested_at")
        )
        return render(
            request,
            "patients/call_taker_dashboard.html",
            {
                "form": form,
                "solved_count": dashboard_stats["solved_count"],
                "pending_count": dashboard_stats["pending_count"],
                "total_count": dashboard_stats["total_count"],
                "pending_cases": pending_cases,
                "case_history": case_history,
            },
        )
    return render(request, "patients/patient_form.html", {"form": form})
