from datetime import timedelta
from math import atan2, cos, radians, sin, sqrt

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ambulances.models import Ambulance, GPSLocation


GPS_MAX_AGE = timedelta(minutes=5)


def publish_ambulance_update(ambulance):
    channel_layer = get_channel_layer()
    location = {
        "id": ambulance.pk,
        "vehicle_number": ambulance.vehicle_number,
        "driver": ambulance.driver.get_full_name() or ambulance.driver.username,
        "latitude": float(ambulance.latitude) if ambulance.latitude is not None else None,
        "longitude": float(ambulance.longitude) if ambulance.longitude is not None else None,
        "availability": ambulance.availability_status,
        "patient_status": ambulance.patient_status,
        "updated_at": ambulance.location_updated_at.isoformat(),
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
        driver__is_active=True,
        driver__role="DRIVER",
    ).select_related("driver")
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
def update_driver_location(*, driver, latitude, longitude):
    if driver.role != driver.Role.DRIVER:
        raise ValidationError("Only ambulance drivers can update a vehicle location.")
    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError) as error:
        raise ValidationError("Valid latitude and longitude are required.") from error
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValidationError("Coordinates are outside the valid range.")

    ambulance = Ambulance.objects.select_for_update().get(driver=driver)
    ambulance.latitude = latitude
    ambulance.longitude = longitude
    ambulance.location_updated_at = timezone.now()
    ambulance.save(update_fields=["latitude", "longitude", "location_updated_at"])
    GPSLocation.objects.create(
        ambulance=ambulance,
        latitude=latitude,
        longitude=longitude,
    )
    publish_ambulance_update(ambulance)
    return ambulance
