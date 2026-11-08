import time

from django.contrib.auth.hashers import check_password
from django.core.exceptions import ImproperlyConfigured
from django.http import JsonResponse
from django.views import View

from accounts.forms import PhoneNumberForm
from accounts.models import User
from accounts.otp import (
    OTP_LENGTH,
    OTP_LIFETIME_SECONDS,
    OTP_MAX_ATTEMPTS,
    OTP_RESEND_COOLDOWN_SECONDS,
    hash_otp,
    issue_otp,
    otp_session_key,
)
from accounts.otp_delivery import OtpDeliveryUnavailable, deliver_registration_otp


class RegistrationOtpView(View):
    role = None

    def post(self, request, *args, **kwargs):
        action = kwargs["action"]
        if action == "send":
            return self.send_otp(request)
        if action == "verify":
            return self.verify_otp(request)
        return JsonResponse(
            {"ok": False, "message": "Unsupported OTP action."},
            status=400,
        )

    def send_otp(self, request):
        phone_form = PhoneNumberForm(request.POST)
        if not phone_form.is_valid():
            return JsonResponse(
                {
                    "ok": False,
                    "message": " ".join(
                        error
                        for errors in phone_form.errors.values()
                        for error in errors
                    ),
                },
                status=400,
            )

        key = otp_session_key(self.role)
        challenge = request.session.get(key, {})
        now = time.time()
        retry_after = int(
            challenge.get("last_sent_at", 0)
            + OTP_RESEND_COOLDOWN_SECONDS
            - now
        )
        if retry_after > 0:
            return JsonResponse(
                {
                    "ok": False,
                    "message": "Please wait before requesting another verification code.",
                    "retry_after": retry_after,
                },
                status=429,
            )

        phone_number = phone_form.cleaned_data["phone_number"]
        request.session.save()
        code = issue_otp()
        challenge = {
            "phone_number": phone_number,
            "session_key": request.session.session_key,
            "issued_at": 0,
            "last_sent_at": now,
            "attempts": 0,
            "otp_hash": "",
            "verified": False,
        }
        request.session[key] = challenge
        request.session.save()

        try:
            deliver_registration_otp(phone_number, code)
        except (OtpDeliveryUnavailable, ImproperlyConfigured) as error:
            return JsonResponse(
                {"ok": False, "message": str(error)},
                status=503,
            )

        challenge["issued_at"] = time.time()
        challenge["otp_hash"] = hash_otp(code)
        request.session[key] = challenge
        request.session.save()
        return JsonResponse(
            {
                "ok": True,
                "message": "Verification code sent. It expires in 5 minutes.",
                "expires_in": OTP_LIFETIME_SECONDS,
                "retry_after": OTP_RESEND_COOLDOWN_SECONDS,
            }
        )

    def verify_otp(self, request):
        phone_form = PhoneNumberForm(request.POST)
        if not phone_form.is_valid():
            return JsonResponse(
                {
                    "ok": False,
                    "message": " ".join(
                        error
                        for errors in phone_form.errors.values()
                        for error in errors
                    ),
                },
                status=400,
            )

        key = otp_session_key(self.role)
        challenge = request.session.get(key)
        phone_number = phone_form.cleaned_data["phone_number"]
        if not isinstance(challenge, dict):
            return JsonResponse(
                {
                    "ok": False,
                    "message": "Request a verification code before verifying your phone.",
                },
                status=400,
            )
        if challenge.get("session_key") != request.session.session_key:
            request.session.pop(key, None)
            return JsonResponse(
                {
                    "ok": False,
                    "message": "This verification request expired. Request a new code.",
                },
                status=400,
            )
        if challenge.get("phone_number") != phone_number:
            return JsonResponse(
                {
                    "ok": False,
                    "message": "The verification code was sent to a different phone number.",
                },
                status=400,
            )

        now = time.time()
        if now >= challenge.get("issued_at", 0) + OTP_LIFETIME_SECONDS:
            challenge["otp_hash"] = ""
            challenge["verified"] = False
            request.session[key] = challenge
            return JsonResponse(
                {
                    "ok": False,
                    "message": "The verification code expired. Request a new code.",
                },
                status=400,
            )
        if challenge.get("verified"):
            return JsonResponse(
                {"ok": True, "verified": True, "message": "Phone number verified."}
            )
        if not challenge.get("otp_hash"):
            return JsonResponse(
                {
                    "ok": False,
                    "message": "Request a new verification code before verifying your phone.",
                },
                status=400,
            )
        if challenge.get("attempts", 0) >= OTP_MAX_ATTEMPTS:
            return JsonResponse(
                {
                    "ok": False,
                    "message": "Maximum verification attempts reached. Request a new code.",
                },
                status=429,
            )

        challenge["attempts"] += 1
        submitted_code = request.POST.get("otp", "").strip()
        valid_code = (
            len(submitted_code) == OTP_LENGTH
            and submitted_code.isdigit()
            and check_password(submitted_code, challenge["otp_hash"])
        )
        if valid_code:
            challenge["verified"] = True
            challenge["otp_hash"] = ""
            request.session[key] = challenge
            return JsonResponse(
                {"ok": True, "verified": True, "message": "Phone number verified."}
            )

        request.session[key] = challenge
        remaining_attempts = OTP_MAX_ATTEMPTS - challenge["attempts"]
        message = "Incorrect verification code."
        if remaining_attempts:
            message += f" {remaining_attempts} attempts remaining."
        else:
            message += " Maximum attempts reached. Request a new code."
            challenge["otp_hash"] = ""
            request.session[key] = challenge
        return JsonResponse(
            {
                "ok": False,
                "message": message,
                "attempts_remaining": remaining_attempts,
            },
            status=400 if remaining_attempts else 429,
        )


class CallTakerRegistrationOtpView(RegistrationOtpView):
    role = User.Role.CALL_TAKER


class DispatcherRegistrationOtpView(RegistrationOtpView):
    role = User.Role.DISPATCHER


class DriverRegistrationOtpView(RegistrationOtpView):
    role = User.Role.DRIVER
