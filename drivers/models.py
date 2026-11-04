from django.conf import settings
from django.db import models


class Driver(models.Model):
    id = models.BigAutoField(primary_key=True, db_column="driver_id")
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="driver_profile",
    )
    driver_name = models.CharField(max_length=120)
    phone_number = models.CharField(max_length=30, blank=True)
    license_number = models.CharField(max_length=60, null=True, blank=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "drivers"

    def __str__(self):
        return self.driver_name or self.user.username
