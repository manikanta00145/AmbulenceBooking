from django.urls import path

from notifications.views import inbox, mark_read


app_name = "notifications"

urlpatterns = [
    path("", inbox, name="inbox"),
    path("<int:notification_id>/read/", mark_read, name="mark_read"),
]
