from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from notifications.models import Notification


@login_required
def inbox(request):
    notifications = Notification.objects.filter(recipient=request.user)
    return render(
        request,
        "notifications/inbox.html",
        {"notifications": notifications},
    )


@login_required
@require_POST
def mark_read(request, notification_id):
    notification = get_object_or_404(
        Notification,
        pk=notification_id,
        recipient=request.user,
    )
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at"])
    return redirect("notifications:inbox")
