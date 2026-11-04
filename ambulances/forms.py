from django import forms

from ambulances.models import Ambulance
from drivers.models import Driver


class AmbulanceCreateForm(forms.ModelForm):
    class Meta:
        model = Ambulance
        fields = ("vehicle_number", "driver")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["driver"].queryset = Driver.objects.filter(
            user__role="DRIVER",
            user__is_active=True,
            ambulance__isnull=True,
        ).select_related("user").order_by("user__username")
