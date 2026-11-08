from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def preserve_existing_account_access(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.using(schema_editor.connection.alias).filter(is_active=False).update(
        approval_status="PENDING"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_user_phone_number_key"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="approval_status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pending"),
                    ("APPROVED", "Approved"),
                    ("REJECTED", "Rejected"),
                ],
                default="APPROVED",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="approved_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="approved_staff_accounts",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="rejected_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="rejected_staff_accounts",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="rejected_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="rejection_reason",
            field=models.TextField(blank=True),
        ),
        migrations.RunPython(preserve_existing_account_access, migrations.RunPython.noop),
    ]
