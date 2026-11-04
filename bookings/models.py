import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from patients.models import Patient


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = "Pending", "Pending"
        ASSIGNED = "Assigned", "Assigned"
        ACCEPTED = "Accepted", "Accepted"
        EN_ROUTE = "En Route", "En Route"
        ARRIVED = "Arrived", "Arrived"
        PATIENT_PICKED_UP = "Patient Picked Up", "Patient Picked Up"
        COMPLETED = "Completed", "Completed"
        CANCELLED = "Cancelled", "Cancelled"

    booking_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name="bookings")
    number_of_patients = models.PositiveIntegerField(default=1)
    emergency_type = models.CharField(max_length=80)
    location_address = models.CharField(max_length=250, db_column="pickup_address")
    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        db_column="patient_latitude",
    )
    longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        db_column="patient_longitude",
    )
    requested_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        db_column="booking_time",
    )
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        db_column="booking_status",
    )
    assigned_ambulance = models.ForeignKey(
        "ambulances.Ambulance",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bookings",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_bookings",
        db_column="call_taker_id",
    )

    class Meta:
        ordering = ["-requested_at"]
        db_table = "bookings"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(number_of_patients__gte=1),
                name="bookings_at_least_one_patient",
            )
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.number_of_patients is None or self.number_of_patients < 1:
            raise ValidationError(
                {"number_of_patients": "There must be at least one patient."}
            )
        if self.number_of_patients == 1 and self.patient_id:
            patient = self.patient
            errors = []
            if not patient.gender:
                errors.append("Gender is required for a single-patient booking.")
            if patient.age is None:
                errors.append("Age is required for a single-patient booking.")
            if errors:
                raise ValidationError({"patient": errors})

    def __str__(self):
        return f"Booking {self.booking_id}"


class BookingStatusHistory(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="status_history")
    old_status = models.CharField(max_length=24, blank=True)
    new_status = models.CharField(max_length=24, choices=Booking.Status.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="booking_status_changes",
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    note = models.CharField(max_length=250, blank=True)

    class Meta:
        ordering = ["changed_at", "pk"]

    def __str__(self):
        return f"{self.booking_id}: {self.old_status} -> {self.new_status}"


class AmbulanceAssignment(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "Active", "Active"
        RELEASED = "Released", "Released"

    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name="assignments")
    id = models.BigAutoField(primary_key=True, db_column="assignment_id")
    ambulance = models.ForeignKey(
        "ambulances.Ambulance",
        on_delete=models.PROTECT,
        related_name="assignments",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ambulance_assignments",
        db_column="dispatcher_id",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    released_at = models.DateTimeField(null=True, blank=True)
    assignment_status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    active_booking_key = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    active_ambulance_key = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        unique=True,
        editable=False,
    )

    class Meta:
        ordering = ["-assigned_at"]
        db_table = "ambulance_assignments"

    def save(self, *args, **kwargs):
        if self.released_at is None:
            self.assignment_status = self.Status.ACTIVE
            self.active_booking_key = self.booking_id
            self.active_ambulance_key = self.ambulance_id
        else:
            self.assignment_status = self.Status.RELEASED
            self.active_booking_key = None
            self.active_ambulance_key = None
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = set(update_fields) | {
                "assignment_status",
                "active_booking_key",
                "active_ambulance_key",
            }
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.booking_id} -> {self.ambulance}"
