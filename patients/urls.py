from django.urls import path

from patients.views import create_request, geocode_address_view, profile


app_name = "patients"

urlpatterns = [
    path("new/", create_request, name="create"),
    path("dashboard/", create_request, name="dashboard"),
    path("profile/", profile, name="profile"),
    path("geocode/", geocode_address_view, name="geocode"),
]
