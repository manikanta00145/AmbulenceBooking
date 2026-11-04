from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0002_remove_ambulanceassignment_bookings_one_active_assignment_and_more"),
        ("patients", "0002_remove_patient_patients_at_least_one_patient_and_more"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="patient",
            name="patients_at_least_one_patient",
        ),
        migrations.RemoveField(
            model_name="patient",
            name="number_of_patients",
        ),
    ]
