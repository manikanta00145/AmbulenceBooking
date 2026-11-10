from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import role_required
from ambulances.forms import AmbulanceCreateForm
from ambulances.models import Ambulance
from ambulances.services import GPS_MAX_AGE, find_nearest_ambulance
from bookings.models import Booking, BookingStatusHistory
from bookings.services import assign_ambulance
from dispatcher.forms import AssignmentForm


ACTIVE_BOOKING_STATUSES = [
    Booking.Status.PENDING,
    Booking.Status.ASSIGNED,
    Booking.Status.ACCEPTED,
    Booking.Status.EN_ROUTE,
    Booking.Status.ARRIVED,
    Booking.Status.PATIENT_PICKED_UP,
]


@role_required("DISPATCHER")
def dashboard(request):
    active_bookings = Booking.objects.filter(status__in=ACTIVE_BOOKING_STATUSES).count()
    completed_today = BookingStatusHistory.objects.filter(
        new_status=Booking.Status.COMPLETED,
        changed_at__date=timezone.localdate(),
    ).count()
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
            "active_bookings": active_bookings,
            "completed_today": completed_today,
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
    now = timezone.now()
    ambulances = list(
        Ambulance.objects.select_related("driver__user").order_by("vehicle_number")
    )
    active_assignments = dict(
        Booking.objects.filter(
            status__in=ACTIVE_BOOKING_STATUSES,
            assigned_ambulance__isnull=False,
        ).values_list("assigned_ambulance_id", "pk")
    )
    locations = [
        {
            "id": ambulance.pk,
            "vehicle_number": ambulance.vehicle_number,
            "driver": ambulance.driver.driver_name or ambulance.driver.user.username,
            "driver_phone": ambulance.driver.phone_number or ambulance.driver.user.phone_number,
            "latitude": float(ambulance.latitude) if ambulance.latitude is not None else None,
            "longitude": float(ambulance.longitude) if ambulance.longitude is not None else None,
            "availability": ambulance.availability_status,
            "patient_status": ambulance.patient_status,
            "updated_at": ambulance.location_updated_at.isoformat(),
            "gps_stale": (
                ambulance.latitude is None
                or ambulance.longitude is None
                or ambulance.location_updated_at < now - GPS_MAX_AGE
            ),
            "active_booking_id": active_assignments.get(ambulance.pk),
        }
        for ambulance in ambulances
    ]
    active_bookings = Booking.objects.filter(
        status__in=ACTIVE_BOOKING_STATUSES,
    ).select_related(
        "patient",
        "assigned_ambulance__driver__user",
    )
    emergencies = []
    for booking in active_bookings:
        ambulance = booking.assigned_ambulance
        driver = ambulance.driver if ambulance else None
        suggested_ambulance = None
        if (
            booking.status == Booking.Status.PENDING
            and ambulance is None
            and booking.latitude is not None
            and booking.longitude is not None
        ):
            suggested_ambulance = find_nearest_ambulance(
                booking.latitude,
                booking.longitude,
            )
        emergencies.append(
            {
                "id": str(booking.pk),
                "patient": booking.patient.name,
                "patient_phone": booking.patient.contact_number,
                "address": booking.location_address,
                "number_of_patients": booking.number_of_patients,
                "latitude": float(booking.latitude) if booking.latitude is not None else None,
                "longitude": float(booking.longitude) if booking.longitude is not None else None,
                "requested_at": booking.requested_at.isoformat(),
                "status": booking.status,
                "ambulance_id": ambulance.pk if ambulance else None,
                "ambulance": ambulance.vehicle_number if ambulance else None,
                "driver": (
                    driver.driver_name or driver.user.username
                    if driver
                    else None
                ),
                "driver_phone": (
                    driver.phone_number or driver.user.phone_number
                    if driver
                    else None
                ),
                "ambulance_latitude": (
                    float(ambulance.latitude)
                    if ambulance and ambulance.latitude is not None
                    else None
                ),
                "ambulance_longitude": (
                    float(ambulance.longitude)
                    if ambulance and ambulance.longitude is not None
                    else None
                ),
                "last_location_update": (
                    ambulance.location_updated_at.isoformat() if ambulance else None
                ),
                "gps_stale": (
                    ambulance.latitude is None
                    or ambulance.longitude is None
                    or ambulance.location_updated_at < now - GPS_MAX_AGE
                    if ambulance
                    else True
                ),
                "suggested_ambulance": (
                    {
                        "id": suggested_ambulance.pk,
                        "vehicle_number": suggested_ambulance.vehicle_number,
                    }
                    if suggested_ambulance
                    else None
                ),
            }
        )

    completed_today = BookingStatusHistory.objects.filter(
        new_status=Booking.Status.COMPLETED,
        changed_at__date=timezone.localdate(),
    ).count()
    response = JsonResponse(
        {
            "locations": locations,
            "emergencies": emergencies,
            "stats": {
                "total_ambulances": len(locations),
                "available_ambulances": sum(
                    location["availability"] == Ambulance.Availability.AVAILABLE
                    and location["patient_status"] == Ambulance.PatientStatus.OFF
                    for location in locations
                ),
                "busy_ambulances": sum(
                    location["availability"] == Ambulance.Availability.UNAVAILABLE
                    for location in locations
                ),
                "active_emergencies": len(emergencies),
                "completed_today": completed_today,
            },
        }
    )
    response["Cache-Control"] = "private, no-store"
    return response
