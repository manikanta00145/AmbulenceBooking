from django.core.validators import MinValueValidator
from django.db import models


class Patient(models.Model):
    name = models.CharField(max_length=120)
    contact_number = models.CharField(max_length=30)
    relationship = models.CharField(max_length=60, blank=True)
    number_of_patients = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    gender = models.CharField(max_length=20, blank=True)
    age = models.PositiveSmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(number_of_patients__gte=1),
                name="patients_at_least_one_patient",
            )
        ]

    def __str__(self):
        return self.name
