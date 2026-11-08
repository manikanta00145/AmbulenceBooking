from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class OtpDeliveryUnavailable(Exception):
    pass


def console_otp_delivery(phone_number, otp):
    if not settings.DEBUG:
        raise ImproperlyConfigured(
            "The console OTP delivery backend is available only when DEBUG is enabled."
        )
    print(f"[DEVELOPMENT OTP] Phone {phone_number}: {otp}")


def deliver_registration_otp(phone_number, otp):
    backend_path = settings.REGISTRATION_OTP_DELIVERY_BACKEND
    if not backend_path:
        raise OtpDeliveryUnavailable(
            "Phone verification is not configured. Contact the system administrator."
        )

    from django.utils.module_loading import import_string

    backend = import_string(backend_path)
    backend(phone_number, otp)
