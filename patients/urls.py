from django.urls import path

from patients.views import create_request, geocode_address_view


app_name = "patients"

urlpatterns = [
    path("new/", create_request, name="create"),
    path("geocode/", geocode_address_view, name="geocode"),
]
