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

    phone_number = models.CharField(max_length=30, blank=True)
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
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "role" in update_fields:
            kwargs["update_fields"] = set(update_fields) | {"dispatcher_slot"}
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
