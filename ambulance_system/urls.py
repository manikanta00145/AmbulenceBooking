from django.contrib import admin
from django.urls import include, path

from ambulance_system.views import home


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", home, name="home"),
    path("accounts/", include("accounts.urls")),
    path("patients/", include("patients.urls")),
    path("bookings/", include("bookings.urls")),
    path("ambulances/", include("ambulances.urls")),
    path("dispatcher/", include("dispatcher.urls")),
    path("drivers/", include("drivers.urls")),
    path("hospitals/", include("hospitals.urls")),
    path("notifications/", include("notifications.urls")),
]
