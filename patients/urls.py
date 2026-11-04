from django.urls import path

from patients.views import create_request


app_name = "patients"

urlpatterns = [
    path("new/", create_request, name="create"),
]
