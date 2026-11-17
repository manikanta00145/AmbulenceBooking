from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from accounts.models import User


def role_required(*roles):
    portal_logins = {
        ("CALL_TAKER",): "accounts:call_taker_login",
        ("DISPATCHER",): "accounts:dispatcher_login",
        ("DRIVER",): "drivers:login",
        ("PATIENT",): "accounts:patient_login",
    }
    login_url = portal_logins.get(tuple(roles))

    def decorator(view):
        @wraps(view)
        @login_required(login_url=login_url)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_active:
                raise PermissionDenied
            if request.user.approval_status != User.ApprovalStatus.APPROVED:
                raise PermissionDenied
            if request.user.is_superuser:
                return view(request, *args, **kwargs)
            if request.user.role not in roles:
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapped

    return decorator
