from django import forms
from django.utils import timezone

from ambulances.models import Ambulance
from ambulances.services import GPS_MAX_AGE


class AssignmentForm(forms.Form):
    ambulance = forms.ModelChoiceField(
        queryset=Ambulance.objects.none(),
        empty_label="Select an available ambulance",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ambulance"].queryset = Ambulance.objects.filter(
            availability_status=Ambulance.Availability.AVAILABLE,
            patient_status=Ambulance.PatientStatus.OFF,
            latitude__isnull=False,
            longitude__isnull=False,
            location_updated_at__gte=timezone.now() - GPS_MAX_AGE,
        ).select_related("driver")
