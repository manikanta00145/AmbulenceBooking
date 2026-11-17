import re

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from accounts.models import User
from accounts.otp import (
    normalize_phone_number,
    phone_number_is_registered,
    registration_phone_is_verified,
)
from ambulances.models import Ambulance
from drivers.models import Driver
from patients.models import Patient


class PortalRegistrationForm(UserCreationForm):
    full_name = forms.CharField(max_length=150, label="Full Name")
    email = forms.EmailField(label="Email")
    employee_id = forms.CharField(max_length=50, label="Employee ID")
    phone_number = forms.CharField(max_length=30, label="Phone Number")
    role = None

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("full_name", "email", "employee_id", "username", "phone_number")

    def __init__(self, *args, request, **kwargs):
        self.request = request
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Username"
        self.fields["username"].widget.attrs.update(
            {"placeholder": "Choose a username", "autocomplete": "username"}
        )
        self.fields["full_name"].widget.attrs.update(
            {"placeholder": "Enter your full name", "autocomplete": "name"}
        )
        self.fields["employee_id"].widget.attrs["placeholder"] = "Enter your Employee ID"
        self.fields["phone_number"].widget.attrs.update(
            {"placeholder": "Enter your phone number", "autocomplete": "tel"}
        )
        self.fields["password1"].label = "Password"
        self.fields["password1"].widget.attrs.update(
            {"placeholder": "Create a password", "autocomplete": "new-password"}
        )
        self.fields["password2"].label = "Confirm Password"
        self.fields["password2"].widget.attrs.update(
            {"placeholder": "Confirm your password", "autocomplete": "new-password"}
        )

    def clean_full_name(self):
        full_name = " ".join(self.cleaned_data["full_name"].split())
        if len(full_name.split()) < 2:
            raise ValidationError("Enter your first and last name.")
        return full_name

    def clean_employee_id(self):
        employee_id = self.cleaned_data["employee_id"].strip()
        if User.objects.filter(employee_id__iexact=employee_id).exists():
            raise ValidationError("An account with this Employee ID already exists.")
        return employee_id

    def clean_email(self):
        email = self.cleaned_data["email"].strip().casefold()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email address already exists.")
        return email

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError("A user with that username already exists.")
        return username

    def clean_phone_number(self):
        phone_number = normalize_phone_number(self.cleaned_data["phone_number"])
        if phone_number_is_registered(phone_number):
            raise ValidationError("An account with this phone number already exists.")
        return phone_number

    def clean(self):
        cleaned_data = super().clean()
        phone_number = cleaned_data.get("phone_number")
        if phone_number and not registration_phone_is_verified(
            self.request,
            self.role,
            phone_number,
        ):
            self.add_error(
                "phone_number",
                "Verify this phone number with OTP before creating your account.",
            )
        if (
            self.role == User.Role.DISPATCHER
            and User.objects.filter(role=User.Role.DISPATCHER).exists()
        ):
            self.add_error(
                None,
                "A Dispatcher account is already registered. Contact the system administrator.",
            )
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        first_name, last_name = self.cleaned_data["full_name"].split(maxsplit=1)
        user.first_name = first_name
        user.last_name = last_name
        user.employee_id = self.cleaned_data["employee_id"]
        user.email = self.cleaned_data["email"]
        user.phone_number = self.cleaned_data["phone_number"]
        user.role = self.role
        user.is_active = False
        user.approval_status = User.ApprovalStatus.PENDING
        if commit:
            user.save()
            self.save_role_details(user)
            self.save_m2m()
        return user

    def save_role_details(self, user):
        pass


class DriverRegistrationForm(PortalRegistrationForm):
    role = User.Role.DRIVER
    address = forms.CharField(max_length=250, label="Address")
    ambulance_number = forms.CharField(max_length=20, label="Ambulance Number")
    vehicle_type = forms.CharField(max_length=60, required=False)
    vehicle_model = forms.CharField(max_length=100, required=False)
    driving_licence_number = forms.CharField(
        max_length=60,
        label="Driving Licence Number",
    )

    class Meta(PortalRegistrationForm.Meta):
        fields = (
            "full_name",
            "email",
            "employee_id",
            "address",
            "ambulance_number",
            "vehicle_type",
            "vehicle_model",
            "driving_licence_number",
            "username",
            "phone_number",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ambulance_number"].widget.attrs.update(
            {
                "placeholder": "AP 31 AB 1234",
                "autocapitalize": "characters",
            }
        )
        self.fields["driving_licence_number"].widget.attrs.update(
            {"placeholder": "Enter your driving licence number"}
        )

    def clean_ambulance_number(self):
        raw_number = " ".join(self.cleaned_data["ambulance_number"].upper().split())
        match = re.fullmatch(r"AP\s*(\d{2})\s*([A-Z]{1,2})\s*(\d{4})", raw_number)
        if not match:
            raise ValidationError("Use the AP 31 AB 1234 vehicle number format.")
        vehicle_number = f"AP {match.group(1)} {match.group(2)} {match.group(3)}"
        if Ambulance.objects.filter(vehicle_number__iexact=vehicle_number).exists():
            raise ValidationError("An ambulance with this number is already registered.")
        return vehicle_number

    def clean_driving_licence_number(self):
        licence_number = self.cleaned_data["driving_licence_number"].strip().upper()
        if Driver.objects.filter(license_number__iexact=licence_number).exists():
            raise ValidationError("This Driving Licence Number is already registered.")
        return licence_number

    def save_role_details(self, user):
        driver = user.driver_profile
        driver.license_number = self.cleaned_data["driving_licence_number"]
        driver.save(update_fields=["license_number"])
        Ambulance.objects.create(
            vehicle_number=self.cleaned_data["ambulance_number"],
            driver=driver,
            vehicle_type=self.cleaned_data["vehicle_type"].strip(),
            vehicle_model=self.cleaned_data["vehicle_model"].strip(),
        )
        driver.address = self.cleaned_data["address"].strip()
        driver.save(update_fields=["address"])


class CallTakerRegistrationForm(PortalRegistrationForm):
    role = User.Role.CALL_TAKER
    call_taker_office = forms.CharField(
        max_length=120,
        label="Call-Taker Office/Station",
    )
    assigned_emergency_centre = forms.CharField(
        max_length=120,
        label="Assigned Emergency Centre",
    )

    class Meta(PortalRegistrationForm.Meta):
        fields = (
            "full_name",
            "email",
            "employee_id",
            "call_taker_office",
            "assigned_emergency_centre",
            "username",
            "phone_number",
        )

    def save_role_details(self, user):
        user.call_taker_office = self.cleaned_data["call_taker_office"].strip()
        user.assigned_emergency_centre = self.cleaned_data[
            "assigned_emergency_centre"
        ].strip()
        user.save(update_fields=["call_taker_office", "assigned_emergency_centre"])


class DispatcherRegistrationForm(PortalRegistrationForm):
    role = User.Role.DISPATCHER
    dispatch_centre = forms.CharField(max_length=120, label="Dispatch Centre")
    designation = forms.CharField(max_length=120, label="Designation")

    class Meta(PortalRegistrationForm.Meta):
        fields = (
            "full_name",
            "email",
            "employee_id",
            "dispatch_centre",
            "designation",
            "username",
            "phone_number",
        )

    def save_role_details(self, user):
        user.dispatch_centre = self.cleaned_data["dispatch_centre"].strip()
        user.designation = self.cleaned_data["designation"].strip()
        user.save(update_fields=["dispatch_centre", "designation"])


RegistrationForm = CallTakerRegistrationForm


class PhoneNumberForm(forms.Form):
    phone_number = forms.CharField(max_length=30)

    def clean_phone_number(self):
        phone_number = normalize_phone_number(self.cleaned_data["phone_number"])
        if phone_number_is_registered(phone_number):
            raise ValidationError("An account with this phone number already exists.")
        return phone_number


class PatientRegistrationForm(UserCreationForm):
    full_name = forms.CharField(max_length=150, label="Full name")
    email = forms.EmailField(label="Email")
    phone_number = forms.CharField(max_length=30, label="Mobile number")
    age = forms.IntegerField(min_value=0, max_value=120)
    gender = forms.ChoiceField(
        choices=[("", "Select gender"), ("Female", "Female"), ("Male", "Male"), ("Other", "Other")]
    )
    address = forms.CharField(max_length=250)
    emergency_contact = forms.CharField(max_length=30)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("full_name", "email", "phone_number", "username")

    def clean_full_name(self):
        full_name = " ".join(self.cleaned_data["full_name"].split())
        if len(full_name.split()) < 2:
            raise ValidationError("Enter your first and last name.")
        return full_name

    def clean_email(self):
        email = self.cleaned_data["email"].strip().casefold()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email address already exists.")
        if Patient.objects.filter(email__iexact=email).exists():
            raise ValidationError("A patient profile with this email address already exists.")
        return email

    def clean_phone_number(self):
        phone_number = normalize_phone_number(self.cleaned_data["phone_number"])
        if phone_number_is_registered(phone_number):
            raise ValidationError("An account with this phone number already exists.")
        return phone_number

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError("A user with that username already exists.")
        return username

    def save(self, commit=True):
        user = super().save(commit=False)
        first_name, last_name = self.cleaned_data["full_name"].split(maxsplit=1)
        user.first_name = first_name
        user.last_name = last_name
        user.email = self.cleaned_data["email"]
        user.phone_number = self.cleaned_data["phone_number"]
        user.role = User.Role.PATIENT
        user.is_active = True
        user.approval_status = User.ApprovalStatus.APPROVED
        if commit:
            user.save()
        return user


class PatientProfileForm(forms.ModelForm):
    email = forms.EmailField()
    contact_number = forms.CharField(max_length=30, label="Mobile number")

    class Meta:
        model = Patient
        fields = (
            "name",
            "email",
            "contact_number",
            "age",
            "gender",
            "address",
            "emergency_contact",
        )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().casefold()
        users = User.objects.filter(email__iexact=email)
        if self.instance.user_id:
            users = users.exclude(pk=self.instance.user_id)
        patients = Patient.objects.filter(email__iexact=email).exclude(pk=self.instance.pk)
        if users.exists() or patients.exists():
            raise ValidationError("This email address is already registered.")
        return email

    def clean_contact_number(self):
        phone_number = normalize_phone_number(self.cleaned_data["contact_number"])
        user_id = self.instance.user_id
        if phone_number_is_registered(phone_number, exclude_user_id=user_id):
            raise ValidationError("This mobile number is already registered.")
        return phone_number


class LoginForm(AuthenticationForm):
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, *args, required_role=None, **kwargs):
        self.required_role = required_role
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Username or email"
        self.fields["username"].widget.attrs.update(
            {"placeholder": "Enter your username or email", "autocomplete": "username"}
        )
        self.fields["password"].widget.attrs.update(
            {"placeholder": "Enter your password", "autocomplete": "current-password"}
        )

    def clean(self):
        username = self.data.get(self.add_prefix("username"), "").strip()
        if "@" in username:
            matches = list(
                User.objects.filter(email__iexact=username).values_list(
                    "username",
                    flat=True,
                )[:2]
            )
            if len(matches) == 1:
                data = self.data.copy()
                data[self.add_prefix("username")] = matches[0]
                self.data = data
        return super().clean()

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if user.approval_status != User.ApprovalStatus.APPROVED:
            raise ValidationError(
                _("This account is awaiting administrator approval or has been rejected."),
                code="invalid_login",
            )
        if (
            self.required_role
            and not user.is_superuser
            and user.role != self.required_role
        ):
            raise ValidationError(
                _("This account is not authorized to use this portal."),
                code="invalid_login",
            )
