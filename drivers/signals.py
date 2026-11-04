from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import User
from drivers.models import Driver


@receiver(post_save, sender=User)
def ensure_driver_profile(sender, instance, **kwargs):
    if instance.role == User.Role.DRIVER:
        Driver.objects.get_or_create(
            user=instance,
            defaults={
                "driver_name": instance.get_full_name() or instance.username,
                "phone_number": instance.phone_number,
            },
        )
