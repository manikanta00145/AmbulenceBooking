from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import role_required
from ambulances.forms import AmbulanceCreateForm
from ambulances.models import Ambulance
from ambulances.services import find_nearest_ambulance
from bookings.models import Booking
from bookings.services import assign_ambulance
from dispatcher.forms import AssignmentForm


@role_required("DISPATCHER")
def dashboard(request):
    bookings = Booking.objects.select_related("patient", "assigned_ambulance").order_by(
        "requested_at"
    )
    return render(
        request,
        "dispatcher/dashboard.html",
        {
            "total_ambulances": Ambulance.objects.count(),
            "available_ambulances": Ambulance.objects.filter(
                availability_status=Ambulance.Availability.AVAILABLE,
                patient_status=Ambulance.PatientStatus.OFF,
            ).count(),
            "unavailable_ambulances": Ambulance.objects.filter(
                availability_status=Ambulance.Availability.UNAVAILABLE
            ).count(),
            "pending_bookings": Booking.objects.filter(status=Booking.Status.PENDING).count(),
            "active_bookings": Booking.objects.filter(
                status__in=[
                    Booking.Status.ASSIGNED,
                    Booking.Status.ACCEPTED,
                    Booking.Status.EN_ROUTE,
                    Booking.Status.ARRIVED,
                    Booking.Status.PATIENT_PICKED_UP,
                ]
            ).count(),
            "bookings": bookings[:10],
        },
    )


@role_required("DISPATCHER")
def booking_list(request):
    bookings = Booking.objects.filter(status=Booking.Status.PENDING).select_related("patient")
    for booking in bookings:
        booking.nearest_ambulance = find_nearest_ambulance(booking.latitude, booking.longitude)
        booking.assignment_form = AssignmentForm()
    return render(request, "dispatcher/booking_list.html", {"bookings": bookings})


@role_required("DISPATCHER")
def assign_booking_view(request, booking_id):
    if request.method != "POST":
        return redirect("dispatcher:bookings")
    form = AssignmentForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Select a valid available ambulance.")
        return redirect("dispatcher:bookings")
    booking = get_object_or_404(Booking, pk=booking_id)
    try:
        assign_ambulance(
            booking_id=booking.pk,
            ambulance_id=form.cleaned_data["ambulance"].pk,
            dispatcher=request.user,
        )
    except ValidationError as error:
        messages.error(request, "Assignment failed: " + "; ".join(error.messages))
    except (Ambulance.DoesNotExist, Booking.DoesNotExist):
        messages.error(request, "Assignment failed: the booking or ambulance no longer exists.")
    else:
        messages.success(request, f"Ambulance assigned to booking {booking.pk}.")
    return redirect("dispatcher:bookings")


@role_required("DISPATCHER")
def ambulance_list(request):
    ambulances = Ambulance.objects.select_related("driver").order_by("vehicle_number")
    return render(
        request,
        "dispatcher/ambulance_list.html",
        {
            "ambulances": ambulances,
            "form": AmbulanceCreateForm(),
        },
    )


@role_required("DISPATCHER")
def live_locations(request):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    locations = [
        {
            "id": ambulance.pk,
            "vehicle_number": ambulance.vehicle_number,
            "driver": ambulance.driver.get_full_name() or ambulance.driver.username,
            "latitude": float(ambulance.latitude),
            "longitude": float(ambulance.longitude),
            "availability": ambulance.availability_status,
            "patient_status": ambulance.patient_status,
            "updated_at": ambulance.location_updated_at.isoformat(),
        }
        for ambulance in Ambulance.objects.filter(
            latitude__isnull=False,
            longitude__isnull=False,
        ).select_related("driver")
    ]
    response = JsonResponse({"locations": locations})
    response["Cache-Control"] = "private, no-store"
    return response
