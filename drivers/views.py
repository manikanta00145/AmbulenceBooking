from django.contrib import messages
from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from ambulances.models import Ambulance
from ambulances.services import GPS_MAX_AGE, is_gps_fresh, update_driver_location
from bookings.models import Booking
from drivers.forms import AvailabilityForm, BookingStatusForm
from drivers.services import update_availability, update_booking_status


@role_required("DRIVER")
def dashboard(request):
    ambulance = Ambulance.objects.filter(driver__user=request.user).first()
    if ambulance is None:
        return render(request, "drivers/no_ambulance.html")
    has_gps_coordinates = (
        ambulance.latitude is not None
        and ambulance.longitude is not None
        and -90 <= ambulance.latitude <= 90
        and -180 <= ambulance.longitude <= 180
    )
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
            "gps_min_interval_ms": int(
                settings.DRIVER_GPS_MIN_INTERVAL_SECONDS * 1000
            ),
            "gps_min_movement_meters": settings.DRIVER_GPS_MIN_MOVEMENT_METERS,
            "gps_heartbeat_ms": int(
                settings.DRIVER_GPS_HEARTBEAT_SECONDS * 1000
            ),
            "gps_stale_after_seconds": int(GPS_MAX_AGE.total_seconds()),
            "gps_accuracy_meters": ambulance.location_accuracy_meters,
            "gps_latitude": (
                float(ambulance.latitude) if has_gps_coordinates else None
            ),
            "gps_longitude": (
                float(ambulance.longitude) if has_gps_coordinates else None
            ),
            "gps_last_updated_at": (
                ambulance.location_updated_at
                if has_gps_coordinates
                else None
            ),
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
        {
            "booking": booking,
            "form": form,
            "navigation_available": booking.status
            in {
                Booking.Status.ASSIGNED,
                Booking.Status.ACCEPTED,
                Booking.Status.EN_ROUTE,
                Booking.Status.ARRIVED,
                Booking.Status.PATIENT_PICKED_UP,
            },
            "status_action_label": _status_action_label(booking.status),
        },
    )


@role_required("DRIVER")
def navigation(request, booking_uuid):
    ambulance = get_object_or_404(
        Ambulance.objects.select_related("driver__user"),
        driver__user=request.user,
    )
    booking = get_object_or_404(
        Booking.objects.select_related("patient"),
        pk=booking_uuid,
        assigned_ambulance=ambulance,
        status__in=[
            Booking.Status.ASSIGNED,
            Booking.Status.ACCEPTED,
            Booking.Status.EN_ROUTE,
            Booking.Status.ARRIVED,
            Booking.Status.PATIENT_PICKED_UP,
        ],
        assignments__ambulance=ambulance,
        assignments__released_at__isnull=True,
    )

    form = BookingStatusForm(request.POST or None, current_status=booking.status)
    if request.method == "POST" and form.is_valid():
        try:
            updated_booking = update_booking_status(
                booking_id=booking.pk,
                new_status=form.cleaned_data["status"],
                driver=request.user,
            )
        except ValidationError as error:
            messages.error(request, "Status update failed: " + "; ".join(error.messages))
        else:
            messages.success(request, "Journey status updated.")
            if updated_booking.status in {
                Booking.Status.COMPLETED,
                Booking.Status.CANCELLED,
            }:
                return redirect("drivers:booking", booking_id=booking.pk)
            return redirect("drivers:navigation", booking_uuid=booking.pk)

    destination_verified = (
        booking.location_confirmed
        and booking.latitude is not None
        and booking.longitude is not None
        and -90 <= booking.latitude <= 90
        and -180 <= booking.longitude <= 180
    )
    has_gps_coordinates = (
        ambulance.latitude is not None
        and ambulance.longitude is not None
        and -90 <= ambulance.latitude <= 90
        and -180 <= ambulance.longitude <= 180
    )
    gps_is_fresh = has_gps_coordinates and is_gps_fresh(ambulance)

    return render(
        request,
        "drivers/navigation.html",
        {
            "booking": booking,
            "ambulance": ambulance,
            "form": form,
            "assignment_history": booking.assignments.select_related("ambulance").order_by(
                "assigned_at"
            ),
            "destination_verified": destination_verified,
            "start_location_available": gps_is_fresh,
            "start_latitude": (
                float(ambulance.latitude) if gps_is_fresh else None
            ),
            "start_longitude": (
                float(ambulance.longitude) if gps_is_fresh else None
            ),
            "gps_latitude": (
                float(ambulance.latitude) if has_gps_coordinates else None
            ),
            "gps_longitude": (
                float(ambulance.longitude) if has_gps_coordinates else None
            ),
            "destination_latitude": (
                float(booking.latitude) if destination_verified else None
            ),
            "destination_longitude": (
                float(booking.longitude) if destination_verified else None
            ),
            "last_location_update": (
                ambulance.location_updated_at if has_gps_coordinates else None
            ),
            "gps_accuracy_meters": ambulance.location_accuracy_meters,
            "gps_min_interval_ms": int(
                settings.DRIVER_GPS_MIN_INTERVAL_SECONDS * 1000
            ),
            "gps_min_movement_meters": settings.DRIVER_GPS_MIN_MOVEMENT_METERS,
            "gps_heartbeat_ms": int(
                settings.DRIVER_GPS_HEARTBEAT_SECONDS * 1000
            ),
            "gps_stale_after_seconds": int(GPS_MAX_AGE.total_seconds()),
            "route_available": booking.status
            in {
                Booking.Status.ASSIGNED,
                Booking.Status.ACCEPTED,
                Booking.Status.EN_ROUTE,
            },
            "status_action_label": _status_action_label(booking.status),
        },
    )


def _status_action_label(status):
    return {
        Booking.Status.ASSIGNED: "Accept assignment",
        Booking.Status.ACCEPTED: "Start journey",
        Booking.Status.EN_ROUTE: "Mark arrived",
        Booking.Status.ARRIVED: "Mark patient picked up",
        Booking.Status.PATIENT_PICKED_UP: "Complete journey",
    }.get(status, "Update status")


@role_required("DRIVER")
@require_POST
def update_location(request):
    try:
        ambulance, updated = update_driver_location(
            driver=request.user,
            latitude=request.POST.get("latitude"),
            longitude=request.POST.get("longitude"),
            observed_at=request.POST.get("observed_at"),
            accuracy_meters=request.POST.get("accuracy_meters"),
            booking_id=request.POST.get("booking_id"),
        )
    except ValidationError as error:
        messages.error(request, "Location update failed: " + "; ".join(error.messages))
        return JsonResponse({"error": "; ".join(error.messages)}, status=400)
    except Ambulance.DoesNotExist:
        message = "Location update failed: no ambulance is registered for this driver."
        messages.error(request, message)
        return JsonResponse({"error": message}, status=400)
    response = JsonResponse(
        {
            "updated": updated,
            "vehicle_number": ambulance.vehicle_number,
            "latitude": float(ambulance.latitude),
            "longitude": float(ambulance.longitude),
            "accuracy_meters": (
                float(ambulance.location_accuracy_meters)
                if ambulance.location_accuracy_meters is not None
                else None
            ),
            "updated_at": ambulance.location_updated_at.isoformat(),
        }
    )
    response["Cache-Control"] = "private, no-store"
    return response


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
