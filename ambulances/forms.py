from django import forms

from accounts.models import User
from ambulances.models import Ambulance


class AmbulanceCreateForm(forms.ModelForm):
    class Meta:
        model = Ambulance
        fields = ("vehicle_number", "driver")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["driver"].queryset = User.objects.filter(
            role=User.Role.DRIVER,
            is_active=True,
            ambulance__isnull=True,
        ).order_by("username")
