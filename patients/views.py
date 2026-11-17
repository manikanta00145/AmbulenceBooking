from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from accounts.forms import PatientProfileForm
from ambulances.models import Ambulance
from ambulances.services import find_nearest_ambulance
from bookings.models import AmbulanceAssignment, Booking, BookingStatusHistory
from notifications.services import notify_users
from patients.forms import (
    CallTakerEmergencyRequestForm,
    EmergencyRequestForm,
    PatientEmergencyRequestForm,
)
from patients.geocoding import geocode_address
from patients.models import Patient


@login_required
@role_required("CALL_TAKER", "DISPATCHER", "PATIENT")
def create_request(request):
    is_call_taker = request.user.role == request.user.Role.CALL_TAKER
    is_patient = request.user.role == request.user.Role.PATIENT
    if is_patient:
        form_class = PatientEmergencyRequestForm
    elif is_call_taker:
        form_class = CallTakerEmergencyRequestForm
    else:
        form_class = EmergencyRequestForm
    if is_patient:
        patient_profile, _ = Patient.objects.get_or_create(
            user=request.user,
            defaults={
                "name": request.user.get_full_name() or request.user.username,
                "contact_number": request.user.phone_number or "0000000000",
                "email": request.user.email,
            },
        )
    else:
        patient_profile = None

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
                    patient = patient_profile if is_patient else form.save_patient()
                    booking = Booking.objects.create(
                        patient=patient,
                        number_of_patients=form.cleaned_data.get(
                            "number_of_patients",
                            1,
                        ),
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
                        destination_hospital=form.cleaned_data.get(
                            "destination_hospital"
                        ),
                        submission_token=submission_token,
                        created_by=request.user,
                    )
                    BookingStatusHistory.objects.create(
                        booking=booking,
                        new_status=booking.status,
                        changed_by=request.user,
                    )

                    # Assign an available ambulance if possible
                    available_amb = None
                    if booking.location_confirmed and booking.latitude is not None and booking.longitude is not None:
                        available_amb = find_nearest_ambulance(booking.latitude, booking.longitude)
                    if not available_amb:
                        available_amb = Ambulance.objects.filter(
                            availability_status=Ambulance.Availability.AVAILABLE,
                            patient_status=Ambulance.PatientStatus.OFF,
                            driver__user__is_active=True,
                            driver__user__role="DRIVER",
                        ).first()

                    if available_amb:
                        old_status = booking.status
                        booking.assigned_ambulance = available_amb
                        booking.status = Booking.Status.ASSIGNED
                        booking.save(update_fields=["assigned_ambulance", "status"])
                        available_amb.availability_status = Ambulance.Availability.UNAVAILABLE
                        available_amb.save(update_fields=["availability_status"])
                        AmbulanceAssignment.objects.create(
                            booking=booking,
                            ambulance=available_amb,
                            assigned_by=request.user,
                        )
                        BookingStatusHistory.objects.create(
                            booking=booking,
                            old_status=old_status,
                            new_status=booking.status,
                            changed_by=request.user,
                            note="Ambulance assigned upon emergency request.",
                        )
                        notify_users(
                            users=(request.user, patient.user, available_amb.driver.user),
                            title="Ambulance assigned",
                            message=f"{available_amb.vehicle_number} has been assigned to booking {booking.pk}.",
                            booking=booking,
                        )
                    else:
                        notify_users(
                            users=(request.user, patient.user),
                            title="Emergency request recorded",
                            message=f"Booking {booking.pk} has been recorded.",
                            booking=booking,
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
    if is_patient:
        bookings = (
            Booking.objects.filter(patient=patient_profile)
            .select_related("assigned_ambulance", "destination_hospital")
            .order_by("-requested_at")
        )
        return render(
            request,
            "patients/patient_dashboard.html",
            {
                "form": form,
                "patient": patient_profile,
                "bookings": bookings,
            },
        )
    return render(request, "patients/patient_form.html", {"form": form})


@login_required
@role_required("PATIENT")
def profile(request):
    patient, _ = Patient.objects.get_or_create(
        user=request.user,
        defaults={
            "name": request.user.get_full_name() or request.user.username,
            "contact_number": request.user.phone_number or "0000000000",
            "email": request.user.email,
        },
    )
    if request.method == "POST":
        form = PatientProfileForm(request.POST, instance=patient)
        if form.is_valid():
            try:
                with transaction.atomic():
                    patient = form.save(commit=False)
                    patient.user = request.user
                    patient.save()
                    first_name, _, last_name = patient.name.strip().partition(" ")
                    request.user.email = patient.email
                    request.user.phone_number = patient.contact_number
                    request.user.first_name = first_name
                    request.user.last_name = last_name
                    request.user.save(
                        update_fields=[
                            "email",
                            "phone_number",
                            "first_name",
                            "last_name",
                        ]
                    )
            except IntegrityError:
                form.add_error(
                    "contact_number",
                    "This mobile number is already registered.",
                )
            else:
                messages.success(request, "Your patient profile was updated.")
                return redirect("patients:profile")
    else:
        form = PatientProfileForm(instance=patient)
    return render(
        request,
        "patients/profile.html",
        {"form": form, "patient": patient},
    )


@login_required
@role_required("CALL_TAKER", "PATIENT", "DISPATCHER")
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
