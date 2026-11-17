from django.urls import path

from hospitals.views import directory


app_name = "hospitals"

urlpatterns = [path("", directory, name="directory")]
