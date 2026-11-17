import re

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.utils import timezone


class User(AbstractUser):
    id = models.BigAutoField(primary_key=True, db_column="user_id")

    class Role(models.TextChoices):
        CALL_TAKER = "CALL_TAKER", "Call taker"
        DISPATCHER = "DISPATCHER", "Dispatcher"
        DRIVER = "DRIVER", "Ambulance driver"
        PATIENT = "PATIENT", "Patient"

    class ApprovalStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    phone_number = models.CharField(max_length=30, blank=True)
    phone_number_key = models.CharField(
        max_length=15,
        unique=True,
        null=True,
        blank=True,
        editable=False,
    )
    employee_id = models.CharField(max_length=50, unique=True, null=True, blank=True)
    call_taker_office = models.CharField(max_length=120, blank=True)
    assigned_emergency_centre = models.CharField(max_length=120, blank=True)
    dispatch_centre = models.CharField(max_length=120, blank=True)
    designation = models.CharField(max_length=120, blank=True)
    approval_status = models.CharField(
        max_length=10,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.APPROVED,
    )
    approved_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_staff_accounts",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rejected_staff_accounts",
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    date_joined = models.DateTimeField(
        "date joined",
        default=timezone.now,
        db_column="created_at",
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CALL_TAKER,
    )
    dispatcher_slot = models.CharField(
        max_length=1,
        null=True,
        blank=True,
        unique=True,
        editable=False,
    )

    def save(self, *args, **kwargs):
        self.dispatcher_slot = "D" if self.role == self.Role.DISPATCHER else None
        phone_digits = re.sub(r"\D", "", self.phone_number or "")
        self.phone_number_key = (
            phone_digits if 7 <= len(phone_digits) <= 15 else None
        )
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            update_fields = set(update_fields)
            if "role" in update_fields:
                update_fields.add("dispatcher_slot")
            if "phone_number" in update_fields:
                update_fields.add("phone_number_key")
            kwargs["update_fields"] = update_fields
        super().save(*args, **kwargs)

    class Meta:
        db_table = "users"
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(role="DISPATCHER", dispatcher_slot="D")
                    | (~Q(role="DISPATCHER") & Q(dispatcher_slot__isnull=True))
                ),
                name="accounts_dispatcher_slot_matches_role",
            )
        ]

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"
