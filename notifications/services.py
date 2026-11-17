from notifications.models import Notification


def notify_users(*, users, title, message, booking=None):
    recipients = {user.pk: user for user in users if user is not None}
    if not recipients:
        return
    Notification.objects.bulk_create(
        [
            Notification(
                recipient=user,
                booking=booking,
                title=title,
                message=message,
            )
            for user in recipients.values()
        ]
    )
