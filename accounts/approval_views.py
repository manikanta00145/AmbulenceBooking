from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import permission_required
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import User
from ambulances.models import Ambulance
from drivers.models import Driver


PORTAL_ROLES = (
    (User.Role.DRIVER, "Ambulance Drivers"),
    (User.Role.CALL_TAKER, "Call-Takers"),
    (User.Role.DISPATCHER, "Dispatchers"),
)


def _staff_accounts(role):
    return User.objects.filter(
        role=role,
        is_staff=False,
        is_superuser=False,
    )


@staff_member_required(login_url="admin:login")
@permission_required("accounts.view_user", raise_exception=True)
def approval_dashboard(request):
    sections = []
    for role, title in PORTAL_ROLES:
        accounts = _staff_accounts(role).order_by("-date_joined", "-pk")
        if role == User.Role.DRIVER:
            accounts = accounts.select_related("driver_profile__ambulance")
        sections.append(
            {
                "role": role,
                "title": title,
                "accounts": accounts,
                "pending_count": accounts.filter(
                    approval_status=User.ApprovalStatus.PENDING
                ).count(),
                "approved_count": accounts.filter(
                    approval_status=User.ApprovalStatus.APPROVED
                ).count(),
                "rejected_count": accounts.filter(
                    approval_status=User.ApprovalStatus.REJECTED
                ).count(),
            }
        )
    return render(
        request,
        "accounts/admin_approval_dashboard.html",
        {"sections": sections},
    )


@staff_member_required(login_url="admin:login")
@permission_required("accounts.view_user", raise_exception=True)
def approval_account_detail(request, user_id):
    account = get_object_or_404(
        User.objects.select_related("approved_by", "rejected_by"),
        pk=user_id,
        role__in=[role for role, _ in PORTAL_ROLES],
        is_staff=False,
        is_superuser=False,
    )
    role_details = []
    if account.role == User.Role.DRIVER:
        driver = Driver.objects.filter(user=account).first()
        ambulance = Ambulance.objects.filter(driver=driver).first() if driver else None
        role_details = [
            ("Ambulance Number", ambulance.vehicle_number if ambulance else "Not provided"),
            ("Driving Licence Number", driver.license_number if driver else "Not provided"),
        ]
    elif account.role == User.Role.CALL_TAKER:
        role_details = [
            ("Call-Taker Office/Station", account.call_taker_office),
            ("Assigned Emergency Centre", account.assigned_emergency_centre),
        ]
    else:
        role_details = [
            ("Dispatch Centre", account.dispatch_centre),
            ("Designation", account.designation),
        ]
    return render(
        request,
        "accounts/admin_approval_detail.html",
        {"account": account, "role_details": role_details},
    )


@staff_member_required(login_url="admin:login")
@permission_required("accounts.change_user", raise_exception=True)
@require_POST
def review_registration(request, user_id, decision):
    if decision not in {"approve", "reject"}:
        raise Http404
    with transaction.atomic():
        account = get_object_or_404(
            User.objects.select_for_update(),
            pk=user_id,
            role__in=[role for role, _ in PORTAL_ROLES],
            is_staff=False,
            is_superuser=False,
        )
        now = timezone.now()
        if decision == "approve":
            account.approval_status = User.ApprovalStatus.APPROVED
            account.is_active = True
            account.approved_by = request.user
            account.approved_at = now
            account.rejected_by = None
            account.rejected_at = None
            account.rejection_reason = ""
            message = f"{account.get_role_display()} account {account.username} approved."
        else:
            account.approval_status = User.ApprovalStatus.REJECTED
            account.is_active = False
            account.approved_by = None
            account.approved_at = None
            account.rejected_by = request.user
            account.rejected_at = now
            account.rejection_reason = request.POST.get("rejection_reason", "").strip()[:2000]
            message = f"{account.get_role_display()} account {account.username} rejected."
        account.save(
            update_fields=[
                "approval_status",
                "is_active",
                "approved_by",
                "approved_at",
                "rejected_by",
                "rejected_at",
                "rejection_reason",
            ]
        )
    messages.success(request, message)
    return redirect("accounts:approval_dashboard")
