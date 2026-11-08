from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from accounts.models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        (
            "Contact details",
            {
                "fields": (
                    "employee_id",
                    "phone_number",
                    "call_taker_office",
                    "assigned_emergency_centre",
                    "dispatch_centre",
                    "designation",
                    "approval_status",
                    "approved_by",
                    "approved_at",
                    "rejected_by",
                    "rejected_at",
                    "rejection_reason",
                )
            },
        ),
        ("System role", {"fields": ("role",)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Contact details", {"fields": ("employee_id", "phone_number")}),
        ("System role", {"fields": ("role",)}),
    )
    list_display = (
        "username",
        "employee_id",
        "email",
        "phone_number",
        "first_name",
        "last_name",
        "role",
        "approval_status",
        "is_staff",
        "is_active",
    )
    list_filter = ("role", "approval_status", "is_staff", "is_active")
    readonly_fields = (
        "approval_status",
        "approved_by",
        "approved_at",
        "rejected_by",
        "rejected_at",
    )
