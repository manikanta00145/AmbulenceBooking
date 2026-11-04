from django.urls import path

from dispatcher import views


app_name = "dispatcher"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("bookings/", views.booking_list, name="bookings"),
    path("bookings/<uuid:booking_id>/assign/", views.assign_booking_view, name="assign"),
    path("ambulances/", views.ambulance_list, name="ambulances"),
    path("locations/", views.live_locations, name="locations"),
]
