from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from ambulances.models import Ambulance
from ambulances.services import update_driver_location
from bookings.models import Booking
from drivers.forms import AvailabilityForm, BookingStatusForm
from drivers.services import update_availability, update_booking_status


@role_required("DRIVER")
def dashboard(request):
    ambulance = get_object_or_404(Ambulance, driver__user=request.user)
    bookings = Booking.objects.filter(
        assigned_ambulance=ambulance,
        status__in=[
            Booking.Status.ASSIGNED,
            Booking.Status.ACCEPTED,
            Booking.Status.EN_ROUTE,
            Booking.Status.ARRIVED,
            Booking.Status.PATIENT_PICKED_UP,
        ],
    ).select_related("patient")
    return render(
        request,
        "drivers/driver_dashboard.html",
        {
            "ambulance": ambulance,
            "bookings": bookings,
            "location_url": "/drivers/location/",
            "availability_form": AvailabilityForm(
                initial={"availability_status": ambulance.availability_status}
            ),
        },
    )


@role_required("DRIVER")
def assigned_booking(request, booking_id):
    ambulance = get_object_or_404(Ambulance, driver__user=request.user)
    booking = get_object_or_404(
        Booking.objects.select_related("patient", "assigned_ambulance"),
        pk=booking_id,
        assigned_ambulance=ambulance,
    )
    if request.method == "POST":
        form = BookingStatusForm(request.POST, current_status=booking.status)
        if form.is_valid():
            try:
                update_booking_status(
                    booking_id=booking.pk,
                    new_status=form.cleaned_data["status"],
                    driver=request.user,
                )
            except ValidationError as error:
                messages.error(request, "Status update failed: " + "; ".join(error.messages))
            else:
                messages.success(request, "Booking status updated.")
                return redirect("drivers:booking", booking_id=booking.pk)
    else:
        form = BookingStatusForm(current_status=booking.status)
    return render(
        request,
        "drivers/assigned_booking.html",
        {"booking": booking, "form": form},
    )


@role_required("DRIVER")
@require_POST
def update_location(request):
    try:
        ambulance = update_driver_location(
            driver=request.user,
            latitude=request.POST.get("latitude"),
            longitude=request.POST.get("longitude"),
        )
    except ValidationError as error:
        messages.error(request, "Location update failed: " + "; ".join(error.messages))
        return JsonResponse({"error": "; ".join(error.messages)}, status=400)
    except Ambulance.DoesNotExist:
        message = "Location update failed: no ambulance is registered for this driver."
        messages.error(request, message)
        return JsonResponse({"error": message}, status=400)
    return JsonResponse(
        {
            "updated": True,
            "vehicle_number": ambulance.vehicle_number,
            "updated_at": ambulance.location_updated_at.isoformat(),
        }
    )


@role_required("DRIVER")
@require_POST
def update_availability_view(request):
    form = AvailabilityForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Select a valid availability status.")
        return redirect("drivers:dashboard")
    try:
        update_availability(
            driver=request.user,
            availability_status=form.cleaned_data["availability_status"],
        )
    except ValidationError as error:
        messages.error(request, "Availability update failed: " + "; ".join(error.messages))
    except Ambulance.DoesNotExist:
        messages.error(request, "Availability update failed: no ambulance is registered.")
    else:
        messages.success(request, "Availability updated.")
    return redirect("drivers:dashboard")
