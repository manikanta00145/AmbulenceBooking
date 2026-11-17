from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class Ambulance(models.Model):
    id = models.BigAutoField(primary_key=True, db_column="ambulance_id")

    class PatientStatus(models.TextChoices):
        ON = "ON", "Patient onboard"
        OFF = "OFF", "No patient"

    class Availability(models.TextChoices):
        AVAILABLE = "Available", "Available"
        UNAVAILABLE = "Unavailable", "Unavailable"

    vehicle_number = models.CharField(max_length=20, unique=True)
    vehicle_type = models.CharField(max_length=60, blank=True)
    vehicle_model = models.CharField(max_length=100, blank=True)
    driver = models.OneToOneField(
        "drivers.Driver",
        on_delete=models.PROTECT,
        related_name="ambulance",
    )
    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ambulances",
    )
    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )
    location_updated_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        db_column="last_location_update",
    )
    location_accuracy_meters = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100000)],
    )
    patient_status = models.CharField(
        max_length=3,
        choices=PatientStatus.choices,
        default=PatientStatus.OFF,
    )
    availability_status = models.CharField(
        max_length=12,
        choices=Availability.choices,
        default=Availability.AVAILABLE,
        db_index=True,
    )

    class Meta:
        db_table = "ambulances"

    def __str__(self):
        return self.vehicle_number


class GPSLocation(models.Model):
    id = models.BigAutoField(primary_key=True, db_column="location_id")
    ambulance = models.ForeignKey(Ambulance, on_delete=models.CASCADE, related_name="locations")
    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )
    accuracy_meters = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100000)],
    )
    recorded_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-recorded_at"]
        db_table = "gps_locations"

    def __str__(self):
        return f"{self.ambulance} @ {self.recorded_at:%Y-%m-%d %H:%M:%S}"
