from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Hospital(models.Model):
    name = models.CharField(max_length=150)
    address = models.CharField(max_length=250)
    contact_number = models.CharField(max_length=30)
    email = models.EmailField(blank=True)
    facilities = models.TextField(blank=True)
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
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "address"],
                name="hospitals_unique_name_address",
            )
        ]

    def __str__(self):
        return self.name
