from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q


class User(AbstractUser):
    class Role(models.TextChoices):
        CALL_TAKER = "CALL_TAKER", "Call taker"
        DISPATCHER = "DISPATCHER", "Dispatcher"
        DRIVER = "DRIVER", "Ambulance driver"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CALL_TAKER,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["role"],
                condition=Q(role="DISPATCHER"),
                name="accounts_single_dispatcher",
            )
        ]

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"
