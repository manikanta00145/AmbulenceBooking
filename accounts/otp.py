import re
import secrets
import time

from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError

from accounts.models import User

OTP_LENGTH = 6
OTP_LIFETIME_SECONDS = 5 * 60
OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_MAX_ATTEMPTS = 5
OTP_SESSION_PREFIX = "registration_otp:"


def normalize_phone_number(value):
    value = value.strip()
    if not re.fullmatch(r"[0-9+().\-\s]+", value):
        raise ValidationError("Enter a valid phone number.")
    digits = re.sub(r"\D", "", value)
    if not 7 <= len(digits) <= 15:
        raise ValidationError("Enter a phone number containing 7 to 15 digits.")
    return ("+" if value.lstrip().startswith("+") else "") + digits


def phone_number_digits(value):
    return re.sub(r"\D", "", value or "")


def phone_number_is_registered(phone_number, exclude_user_id=None):
    digits = phone_number_digits(phone_number)
    users = User.objects.exclude(phone_number="")
    if exclude_user_id is not None:
        users = users.exclude(pk=exclude_user_id)
    return any(
        phone_number_digits(existing)
        == digits
        for existing in users.values_list("phone_number", flat=True)
    )


def otp_session_key(role):
    return f"{OTP_SESSION_PREFIX}{role.lower()}"


def issue_otp():
    return f"{secrets.randbelow(10**OTP_LENGTH):0{OTP_LENGTH}d}"


def get_verified_phone(request, role):
    challenge = request.session.get(otp_session_key(role), {})
    if (
        challenge.get("verified")
        and challenge.get("session_key") == request.session.session_key
        and time.time() < challenge.get("issued_at", 0) + OTP_LIFETIME_SECONDS
    ):
        return challenge.get("phone_number")
    return None


def registration_phone_is_verified(request, role, phone_number):
    try:
        normalized_phone = normalize_phone_number(phone_number)
    except ValidationError:
        return False
    return get_verified_phone(request, role) == normalized_phone


def clear_registration_otp(request, role):
    request.session.pop(otp_session_key(role), None)


def otp_matches(challenge, submitted_otp):
    stored_hash = challenge.get("otp_hash", "")
    return bool(stored_hash) and check_password(submitted_otp, stored_hash)


def hash_otp(otp):
    return make_password(otp)
