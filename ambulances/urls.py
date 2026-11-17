from django.urls import path

from ambulances.views import create, delete, detail, edit


app_name = "ambulances"

urlpatterns = [
    path("new/", create, name="create"),
    path("<int:ambulance_id>/", detail, name="detail"),
    path("<int:ambulance_id>/edit/", edit, name="edit"),
    path("<int:ambulance_id>/delete/", delete, name="delete"),
]
