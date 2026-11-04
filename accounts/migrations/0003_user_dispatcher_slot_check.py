from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_remove_user_accounts_single_dispatcher_and_more"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="user",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("dispatcher_slot", "D"), ("role", "DISPATCHER"))
                    | (
                        ~models.Q(("role", "DISPATCHER"))
                        & models.Q(("dispatcher_slot__isnull", True))
                    )
                ),
                name="accounts_dispatcher_slot_matches_role",
            ),
        ),
    ]
