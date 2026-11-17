from django import forms
from django.db import models

from ambulances.models import Ambulance
from drivers.models import Driver
from hospitals.models import Hospital


class AmbulanceCreateForm(forms.ModelForm):
    class Meta:
        model = Ambulance
        fields = (
            "vehicle_number",
            "vehicle_type",
            "vehicle_model",
            "driver",
            "hospital",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["driver"].queryset = Driver.objects.filter(
            user__role="DRIVER",
            user__is_active=True,
            ambulance__isnull=True,
        ).select_related("user").order_by("user__username")
        self.fields["hospital"].queryset = Hospital.objects.filter(is_active=True)


class AmbulanceUpdateForm(forms.ModelForm):
    class Meta:
        model = Ambulance
        fields = (
            "vehicle_number",
            "vehicle_type",
            "vehicle_model",
            "driver",
            "hospital",
            "availability_status",
            "patient_status",
            "latitude",
            "longitude",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = kwargs.get("instance")
        assigned_driver_id = instance.driver_id if instance else None
        driver_filter = models.Q(ambulance__isnull=True)
        if assigned_driver_id:
            driver_filter |= models.Q(pk=assigned_driver_id)
        self.fields["driver"].queryset = Driver.objects.filter(
            driver_filter,
            user__role="DRIVER",
            user__is_active=True,
        ).select_related("user").order_by("user__username")
        self.fields["hospital"].queryset = Hospital.objects.filter(is_active=True)
