from django.urls import path

from drivers import views


app_name = "drivers"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("bookings/<uuid:booking_id>/", views.assigned_booking, name="booking"),
    path("location/", views.update_location, name="location"),
    path("availability/", views.update_availability_view, name="availability"),
]
