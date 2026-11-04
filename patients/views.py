from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render

from accounts.decorators import role_required
from bookings.models import Booking, BookingStatusHistory
from patients.forms import EmergencyRequestForm


@login_required
@role_required("CALL_TAKER", "DISPATCHER")
def create_request(request):
    if request.method == "POST":
        form = EmergencyRequestForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                patient = form.save_patient()
                booking = Booking.objects.create(
                    patient=patient,
                    emergency_type=form.cleaned_data["emergency_type"],
                    location_address=form.cleaned_data["location_address"],
                    latitude=form.cleaned_data["latitude"],
                    longitude=form.cleaned_data["longitude"],
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
        form = EmergencyRequestForm()
    return render(request, "patients/patient_form.html", {"form": form})
