from django.urls import path

from ambulances.views import create


app_name = "ambulances"

urlpatterns = [
    path("new/", create, name="create"),
]
