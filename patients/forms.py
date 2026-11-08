from django import forms

from patients.models import Patient


class EmergencyRequestForm(forms.Form):
    name = forms.CharField(max_length=120, label="Patient name")
    contact_number = forms.CharField(max_length=30, label="Caller contact number")
    relationship = forms.CharField(max_length=60, required=False)
    number_of_patients = forms.IntegerField(min_value=1, initial=1)
    gender = forms.ChoiceField(
        choices=[("", "Select gender"), ("Female", "Female"), ("Male", "Male"), ("Other", "Other")],
        required=False,
    )
    age = forms.IntegerField(min_value=0, max_value=120, required=False)
    emergency_type = forms.CharField(max_length=80)
    location_address = forms.CharField(max_length=250, label="Pickup address")
    latitude = forms.DecimalField(
        min_value=-90,
        max_value=90,
        required=False,
        decimal_places=7,
        max_digits=10,
    )
    longitude = forms.DecimalField(
        min_value=-180,
        max_value=180,
        required=False,
        decimal_places=7,
        max_digits=10,
    )

    def clean(self):
        cleaned_data = super().clean()
        patient_count = cleaned_data.get("number_of_patients")
        if patient_count == 1:
            if not cleaned_data.get("gender"):
                self.add_error("gender", "Select the patient's gender.")
            if cleaned_data.get("age") is None:
                self.add_error("age", "Enter the patient's age.")
        elif patient_count and patient_count > 1:
            cleaned_data["gender"] = ""
            cleaned_data["age"] = None

        latitude = cleaned_data.get("latitude")
        longitude = cleaned_data.get("longitude")
        if (latitude is None) != (longitude is None):
            self.add_error("latitude", "Provide both coordinates or leave both blank.")
        return cleaned_data

    def save_patient(self):
        return Patient.objects.create(
            name=self.cleaned_data["name"],
            contact_number=self.cleaned_data["contact_number"],
            relationship=self.cleaned_data["relationship"],
            gender=self.cleaned_data["gender"],
            age=self.cleaned_data["age"],
        )


class CallTakerEmergencyRequestForm(forms.Form):
    name = forms.CharField(max_length=120, label="Patient Name")
    contact_number = forms.RegexField(
        regex=r"^[0-9+\-\s]{10,15}$",
        max_length=30,
        label="Contact Number",
        error_messages={"invalid": "Enter a valid contact number."},
    )
    number_of_patients = forms.TypedChoiceField(
        choices=[("", "Select number of patients"), *[(i, str(i)) for i in range(1, 11)]],
        coerce=int,
        label="Number of Patients",
        error_messages={"required": "Select the number of patients."},
    )
    location_address = forms.CharField(
        max_length=250,
        label="Pickup Address",
        error_messages={"required": "Enter the pickup address."},
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs.update(
            {"placeholder": "Enter the patient's full name", "autocomplete": "name"}
        )
        self.fields["contact_number"].widget.attrs.update(
            {"placeholder": "Enter a contact number", "autocomplete": "tel"}
        )
        self.fields["number_of_patients"].widget.attrs["aria-label"] = (
            "Number of patients"
        )
        self.fields["location_address"].widget.attrs.update(
            {
                "placeholder": "Type the complete pickup address",
                "autocomplete": "street-address",
            }
        )

    def save_patient(self):
        return Patient.objects.create(
            name=self.cleaned_data["name"].strip(),
            contact_number=self.cleaned_data["contact_number"].strip(),
        )
