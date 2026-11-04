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
    emergency_type = models.CharField(max_length=80)
    location_address = models.CharField(max_length=250)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    requested_at = models.DateTimeField(default=timezone.now, db_index=True)
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
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
    )

    class Meta:
        ordering = ["-requested_at"]

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
    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name="assignments")
    ambulance = models.ForeignKey(
        "ambulances.Ambulance",
        on_delete=models.PROTECT,
        related_name="assignments",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ambulance_assignments",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    released_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-assigned_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["booking"],
                condition=models.Q(released_at__isnull=True),
                name="bookings_one_active_assignment",
            ),
            models.UniqueConstraint(
                fields=["ambulance"],
                condition=models.Q(released_at__isnull=True),
                name="bookings_one_active_assignment_per_ambulance",
            ),
        ]

    def __str__(self):
        return f"{self.booking_id} -> {self.ambulance}"
