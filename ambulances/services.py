from datetime import datetime, timedelta, timezone as datetime_timezone
from math import atan2, cos, isfinite, radians, sin, sqrt

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ambulances.models import Ambulance, GPSLocation
from bookings.models import AmbulanceAssignment, Booking


GPS_MAX_AGE = timedelta(minutes=5)


def is_gps_fresh(ambulance, *, now=None):
    now = now or timezone.now()
    return (
        ambulance.latitude is not None
        and ambulance.longitude is not None
        and -90 <= ambulance.latitude <= 90
        and -180 <= ambulance.longitude <= 180
        and now - GPS_MAX_AGE <= ambulance.location_updated_at <= now
    )


def publish_ambulance_update(ambulance):
    channel_layer = get_channel_layer()
    active_booking = Booking.objects.filter(
        assigned_ambulance_id=ambulance.pk,
        status__in=[
            Booking.Status.ASSIGNED,
            Booking.Status.ACCEPTED,
            Booking.Status.EN_ROUTE,
            Booking.Status.ARRIVED,
            Booking.Status.PATIENT_PICKED_UP,
        ],
    ).values("booking_id", "status").first()
    location = {
        "id": ambulance.pk,
        "vehicle_number": ambulance.vehicle_number,
        "driver": ambulance.driver.driver_name or ambulance.driver.user.username,
        "driver_phone": ambulance.driver.phone_number or ambulance.driver.user.phone_number,
        "latitude": float(ambulance.latitude) if ambulance.latitude is not None else None,
        "longitude": float(ambulance.longitude) if ambulance.longitude is not None else None,
        "accuracy_meters": (
            float(ambulance.location_accuracy_meters)
            if ambulance.location_accuracy_meters is not None
            else None
        ),
        "availability": ambulance.availability_status,
        "patient_status": ambulance.patient_status,
        "updated_at": ambulance.location_updated_at.isoformat(),
        "gps_stale": not is_gps_fresh(ambulance),
        "active_booking_id": (
            str(active_booking["booking_id"]) if active_booking else None
        ),
        "booking_status": active_booking["status"] if active_booking else None,
    }

    def send_update():
        async_to_sync(channel_layer.group_send)(
            "dispatch_locations",
            {"type": "location.update", "location": location},
        )

    transaction.on_commit(send_update)


def calculate_distance(lat1, lon1, lat2, lon2):
    """Return great-circle distance in kilometers."""
    lat1, lon1, lat2, lon2 = map(float, (lat1, lon1, lat2, lon2))
    if not (-90 <= lat1 <= 90 and -90 <= lat2 <= 90):
        raise ValueError("Latitude must be between -90 and 90 degrees.")
    if not (-180 <= lon1 <= 180 and -180 <= lon2 <= 180):
        raise ValueError("Longitude must be between -180 and 180 degrees.")
    earth_radius_km = 6371.0
    delta_lat = radians(lat2 - lat1)
    delta_lon = radians(lon2 - lon1)
    haversine = (
        sin(delta_lat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(delta_lon / 2) ** 2
    )
    return earth_radius_km * 2 * atan2(sqrt(haversine), sqrt(max(0.0, 1 - haversine)))


def find_nearest_ambulance(patient_latitude, patient_longitude):
    if patient_latitude is None or patient_longitude is None:
        return None
    cutoff = timezone.now() - GPS_MAX_AGE
    candidates = Ambulance.objects.filter(
        availability_status=Ambulance.Availability.AVAILABLE,
        patient_status=Ambulance.PatientStatus.OFF,
        latitude__isnull=False,
        longitude__isnull=False,
        location_updated_at__gte=cutoff,
        location_updated_at__lte=timezone.now(),
        driver__user__is_active=True,
        driver__user__role="DRIVER",
    ).select_related("driver__user")
    return min(
        candidates,
        key=lambda ambulance: calculate_distance(
            patient_latitude,
            patient_longitude,
            ambulance.latitude,
            ambulance.longitude,
        ),
        default=None,
    )


@transaction.atomic
def update_driver_location(
    *,
    driver,
    latitude,
    longitude,
    observed_at=None,
    accuracy_meters=None,
    booking_id=None,
):
    if driver.role != driver.Role.DRIVER:
        raise ValidationError("Only ambulance drivers can update a vehicle location.")
    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError) as error:
        raise ValidationError("Valid latitude and longitude are required.") from error
    if not (
        isfinite(latitude)
        and isfinite(longitude)
        and -90 <= latitude <= 90
        and -180 <= longitude <= 180
    ):
        raise ValidationError("Coordinates are outside the valid range.")

    try:
        observed_at = datetime.fromtimestamp(
            float(observed_at) / 1000,
            tz=datetime_timezone.utc,
        )
    except (TypeError, ValueError, OverflowError, OSError) as error:
        raise ValidationError("A valid GPS fix timestamp is required.") from error
    now = timezone.now()
    if (
        observed_at > now + timedelta(seconds=30)
        or observed_at < now - GPS_MAX_AGE
    ):
        raise ValidationError("The GPS fix is stale or has an invalid timestamp.")

    if accuracy_meters in (None, ""):
        accuracy_meters = None
    else:
        try:
            accuracy_meters = float(accuracy_meters)
        except (TypeError, ValueError) as error:
            raise ValidationError("GPS accuracy must be a valid number.") from error
        if not isfinite(accuracy_meters) or not 0 <= accuracy_meters <= 100000:
            raise ValidationError("GPS accuracy must be between 0 and 100000 meters.")

    booking = None
    if booking_id:
        booking = Booking.objects.select_for_update().filter(pk=booking_id).first()
        if booking is None:
            raise ValidationError("The active booking could not be found.")

    ambulance = Ambulance.objects.select_for_update().select_related(
        "driver__user"
    ).get(driver__user=driver)
    if booking is not None:
        if (
            booking.assigned_ambulance_id != ambulance.pk
            or booking.status
            not in {
                Booking.Status.ASSIGNED,
                Booking.Status.ACCEPTED,
                Booking.Status.EN_ROUTE,
                Booking.Status.ARRIVED,
                Booking.Status.PATIENT_PICKED_UP,
            }
            or not AmbulanceAssignment.objects.filter(
                booking=booking,
                ambulance=ambulance,
                released_at__isnull=True,
            ).exists()
        ):
            raise ValidationError("This driver does not have an active assignment for that booking.")

    has_previous_location = (
        ambulance.latitude is not None and ambulance.longitude is not None
    )
    if has_previous_location:
        elapsed_seconds = (now - ambulance.location_updated_at).total_seconds()
        if 0 <= elapsed_seconds < settings.DRIVER_GPS_MIN_INTERVAL_SECONDS:
            return ambulance, False
        distance_meters = calculate_distance(
            ambulance.latitude,
            ambulance.longitude,
            latitude,
            longitude,
        ) * 1000
        if (
            0 <= elapsed_seconds
            and distance_meters < settings.DRIVER_GPS_MIN_MOVEMENT_METERS
            and elapsed_seconds < settings.DRIVER_GPS_HEARTBEAT_SECONDS
        ):
            return ambulance, False

    ambulance.latitude = latitude
    ambulance.longitude = longitude
    ambulance.location_accuracy_meters = accuracy_meters
    ambulance.location_updated_at = now
    ambulance.save(
        update_fields=[
            "latitude",
            "longitude",
            "location_accuracy_meters",
            "location_updated_at",
        ]
    )
    GPSLocation.objects.create(
        ambulance=ambulance,
        latitude=latitude,
        longitude=longitude,
        accuracy_meters=accuracy_meters,
    )
    publish_ambulance_update(ambulance)
    return ambulance, True
