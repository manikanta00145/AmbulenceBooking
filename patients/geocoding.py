import hashlib
import threading
import time
from datetime import timedelta
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from patients.models import GeocodingCache, NominatimRequestState


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
REQUEST_INTERVAL_SECONDS = 1
REQUEST_TIMEOUT_SECONDS = 5
CACHE_TTL = timedelta(days=30)
_request_lock = threading.Lock()


def _address_key(address):
    normalized = " ".join(address.casefold().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _cached_result(key):
    cached = GeocodingCache.objects.filter(
        address_key=key,
        expires_at__gt=timezone.now(),
    ).first()
    if cached is None:
        return None
    return {
        "ok": True,
        "latitude": str(cached.latitude),
        "longitude": str(cached.longitude),
        "display_name": cached.display_name,
        "cached": True,
    }


def geocode_address(address):
    key = _address_key(address)
    cached_result = _cached_result(key)
    if cached_result is not None:
        return cached_result

    with _request_lock, transaction.atomic():
        state = NominatimRequestState.objects.select_for_update().get(pk=1)
        cached_result = _cached_result(key)
        if cached_result is not None:
            return cached_result

        if state.last_request_at is not None:
            elapsed = (timezone.now() - state.last_request_at).total_seconds()
            remaining = REQUEST_INTERVAL_SECONDS - elapsed
            if remaining > 0:
                time.sleep(remaining)

        state.last_request_at = timezone.now()
        state.save(update_fields=["last_request_at"])
        try:
            response = requests.get(
                NOMINATIM_URL,
                params={"q": address, "format": "jsonv2", "limit": 1},
                headers={
                    "User-Agent": settings.NOMINATIM_USER_AGENT,
                    "Accept": "application/json",
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except requests.Timeout:
            state.last_request_at = timezone.now()
            state.save(update_fields=["last_request_at"])
            return {
                "ok": False,
                "error": "The address lookup timed out. Try again or select the location manually.",
            }
        except requests.RequestException:
            state.last_request_at = timezone.now()
            state.save(update_fields=["last_request_at"])
            return {
                "ok": False,
                "error": "The address lookup service is unavailable. Try again or select the location manually.",
            }
        state.last_request_at = timezone.now()
        state.save(update_fields=["last_request_at"])
        try:
            results = response.json()
        except ValueError:
            return {
                "ok": False,
                "error": "The address service returned an invalid result. Select the location manually.",
            }

        if not isinstance(results, list):
            return {
                "ok": False,
                "error": "The address service returned an invalid result. Select the location manually.",
            }
        if not results:
            return {
                "ok": False,
                "error": "No matching address was found. Select the location manually.",
            }

        try:
            latitude = Decimal(str(results[0]["lat"]))
            longitude = Decimal(str(results[0]["lon"]))
            display_name = str(results[0]["display_name"]).strip()
        except (KeyError, InvalidOperation, TypeError):
            return {
                "ok": False,
                "error": "The address service returned incomplete coordinates. Select the location manually.",
            }
        if (
            not display_name
            or not latitude.is_finite()
            or not longitude.is_finite()
            or not Decimal("-90") <= latitude <= Decimal("90")
            or not Decimal("-180") <= longitude <= Decimal("180")
        ):
            return {
                "ok": False,
                "error": "The address service returned invalid coordinates. Select the location manually.",
            }

        latitude = latitude.quantize(Decimal("0.0000001"))
        longitude = longitude.quantize(Decimal("0.0000001"))
        GeocodingCache.objects.update_or_create(
            address_key=key,
            defaults={
                "address": address,
                "latitude": latitude,
                "longitude": longitude,
                "display_name": display_name[:500],
                "expires_at": timezone.now() + CACHE_TTL,
            },
        )
        return {
            "ok": True,
            "latitude": str(latitude),
            "longitude": str(longitude),
            "display_name": display_name,
            "cached": False,
        }
