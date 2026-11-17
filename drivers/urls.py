from django.urls import path

from accounts.views import DriverLoginView, DriverRegistrationView
from accounts.otp_views import DriverRegistrationOtpView
from drivers import views


app_name = "drivers"

urlpatterns = [
    path(
        "login/",
        DriverLoginView.as_view(template_name="drivers/driver_login.html"),
        name="login",
    ),
    path(
        "register/",
        DriverRegistrationView.as_view(),
        name="register",
    ),
    path(
        "register/send-otp/",
        DriverRegistrationOtpView.as_view(),
        {"action": "send"},
        name="send_otp",
    ),
    path(
        "register/verify-otp/",
        DriverRegistrationOtpView.as_view(),
        {"action": "verify"},
        name="verify_otp",
    ),
    path("", views.dashboard, name="dashboard"),
    path(
        "navigation/<uuid:booking_uuid>/",
        views.navigation,
        name="navigation",
    ),
    path("bookings/<uuid:booking_id>/", views.assigned_booking, name="booking"),
    path("location/", views.update_location, name="location"),
    path("availability/", views.update_availability_view, name="availability"),
]
