from django.urls import path

from bookings.views import detail


app_name = "bookings"

urlpatterns = [
    path("<uuid:booking_id>/", detail, name="detail"),
]
