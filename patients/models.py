from django.db import models


class Patient(models.Model):
    id = models.BigAutoField(primary_key=True, db_column="patient_id")
    name = models.CharField(max_length=120, db_column="patient_name")
    contact_number = models.CharField(max_length=30)
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
