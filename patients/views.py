from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from bookings.models import Booking, BookingStatusHistory
from patients.forms import CallTakerEmergencyRequestForm, EmergencyRequestForm
from patients.geocoding import geocode_address


@login_required
@role_required("CALL_TAKER", "DISPATCHER")
def create_request(request):
    is_call_taker = request.user.role == request.user.Role.CALL_TAKER
    form_class = CallTakerEmergencyRequestForm if is_call_taker else EmergencyRequestForm
    if request.method == "POST":
        form = form_class(request.POST)
        if form.is_valid():
            submission_token = form.cleaned_data.get("submission_token")
            existing_booking = (
                Booking.objects.filter(submission_token=submission_token).first()
                if submission_token
                else None
            )
            if existing_booking:
                messages.info(
                    request,
                    "This emergency request was already recorded.",
                )
                return redirect("bookings:detail", booking_id=existing_booking.pk)
            try:
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
                        location_confirmed=form.cleaned_data.get(
                            "location_confirmed",
                            False,
                        ),
                        submission_token=submission_token,
                        created_by=request.user,
                    )
                    BookingStatusHistory.objects.create(
                        booking=booking,
                        new_status=booking.status,
                        changed_by=request.user,
                    )
            except IntegrityError:
                if not submission_token:
                    raise
                existing_booking = Booking.objects.filter(
                    submission_token=submission_token
                ).first()
                if existing_booking is None:
                    raise
                messages.info(request, "This emergency request was already recorded.")
                return redirect("bookings:detail", booking_id=existing_booking.pk)
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


@login_required
@role_required("CALL_TAKER")
@require_POST
def geocode_address_view(request):
    address = request.POST.get("address", "").strip()
    if not address or len(address) > 250:
        response = JsonResponse(
            {"ok": False, "error": "Enter a valid address of 1 to 250 characters."},
            status=400,
        )
    else:
        response = JsonResponse(geocode_address(address))
    response["Cache-Control"] = "private, no-store"
    return response
