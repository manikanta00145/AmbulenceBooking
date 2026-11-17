from django.conf import settings
from django.db import models


class Patient(models.Model):
    id = models.BigAutoField(primary_key=True, db_column="patient_id")
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="patient_profile",
    )
    name = models.CharField(max_length=120, db_column="patient_name")
    contact_number = models.CharField(max_length=30)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=250, blank=True)
    emergency_contact = models.CharField(max_length=30, blank=True)
    relationship = models.CharField(
        max_length=60,
        blank=True,
        db_column="relationship_with_patient",
    )
    gender = models.CharField(max_length=20, blank=True)
    age = models.PositiveSmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "patients"

    def __str__(self):
        return self.name


class GeocodingCache(models.Model):
    address_key = models.CharField(max_length=64, unique=True)
    address = models.CharField(max_length=250)
    latitude = models.DecimalField(max_digits=10, decimal_places=7)
    longitude = models.DecimalField(max_digits=10, decimal_places=7)
    display_name = models.CharField(max_length=500)
    expires_at = models.DateTimeField(db_index=True)


class NominatimRequestState(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    last_request_at = models.DateTimeField(null=True, blank=True)
