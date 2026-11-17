from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.generic.edit import FormView

from accounts.forms import (
    CallTakerRegistrationForm,
    DispatcherRegistrationForm,
    DriverRegistrationForm,
    LoginForm,
    PatientRegistrationForm,
)
from accounts.models import User
from accounts.otp import (
    clear_registration_otp,
    get_verified_phone,
    phone_number_is_registered,
)
from ambulances.models import Ambulance
from drivers.models import Driver
from patients.models import Patient


class AccountLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm


class PortalLoginView(LoginView):
    template_name = "accounts/portal_login.html"
    authentication_form = LoginForm
    portal_role = None
    portal_title = ""
    dashboard_url_name = ""
    registration_url_name = ""
    login_url_name = ""
    portal_role_label = ""

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["required_role"] = self.portal_role
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "portal_title": self.portal_title,
                "portal_role": self.portal_role,
                "registration_url_name": self.registration_url_name,
                "login_url_name": self.login_url_name,
                "portal_role_label": self.portal_role_label,
            }
        )
        return context

    def get_success_url(self):
        return self.get_redirect_url() or reverse(self.dashboard_url_name)


class CallTakerLoginView(PortalLoginView):
    portal_role = User.Role.CALL_TAKER
    portal_title = "Call-Taker"
    dashboard_url_name = "patients:create"
    registration_url_name = "accounts:call_taker_register"
    login_url_name = "accounts:call_taker_login"
    portal_role_label = "CALL-TAKER"


class DispatcherLoginView(PortalLoginView):
    portal_role = User.Role.DISPATCHER
    portal_title = "Dispatcher"
    dashboard_url_name = "dispatcher:dashboard"
    registration_url_name = "accounts:dispatcher_register"
    login_url_name = "accounts:dispatcher_login"
    portal_role_label = "DISPATCHER"


class DriverLoginView(PortalLoginView):
    portal_role = User.Role.DRIVER
    portal_title = "Driver"
    dashboard_url_name = "drivers:dashboard"
    registration_url_name = "drivers:register"
    login_url_name = "drivers:login"
    portal_role_label = "DRIVER"


class PatientLoginView(PortalLoginView):
    portal_role = User.Role.PATIENT
    portal_title = "Patient"
    dashboard_url_name = "patients:dashboard"
    registration_url_name = "accounts:patient_register"
    login_url_name = "accounts:patient_login"
    portal_role_label = "PATIENT"


class PatientRegistrationView(FormView):
    template_name = "accounts/patient_register.html"
    form_class = PatientRegistrationForm

    def form_valid(self, form):
        try:
            with transaction.atomic():
                user = form.save()
                Patient.objects.create(
                    user=user,
                    name=form.cleaned_data["full_name"],
                    email=form.cleaned_data["email"],
                    contact_number=form.cleaned_data["phone_number"],
                    age=form.cleaned_data["age"],
                    gender=form.cleaned_data["gender"],
                    address=form.cleaned_data["address"],
                    emergency_contact=form.cleaned_data["emergency_contact"],
                )
        except IntegrityError:
            form.add_error(
                None,
                "The account could not be created because one of these details "
                "was registered at the same time. Review your email and mobile number.",
            )
            return self.form_invalid(form)

        messages.success(self.request, "Patient account created. You can now sign in.")
        return render(
            self.request,
            "accounts/registration_success.html",
            {
                "portal_title": "Patient",
                "portal_role_label": "PATIENT",
                "redirect_url": reverse("accounts:patient_login"),
                "approval_required": False,
            },
        )


class PortalRegistrationView(FormView):
    template_name = "accounts/portal_register.html"
    form_class = None
    role = None
    portal_title = ""
    portal_role_label = ""
    login_url_name = ""
    send_otp_url_name = ""
    verify_otp_url_name = ""
    success_message = ""

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "portal_title": self.portal_title,
                "portal_role": self.role,
                "portal_role_label": self.portal_role_label,
                "login_url_name": self.login_url_name,
                "send_otp_url_name": self.send_otp_url_name,
                "verify_otp_url_name": self.verify_otp_url_name,
                "verified_phone": get_verified_phone(self.request, self.role),
            }
        )
        return context

    def form_valid(self, form):
        try:
            with transaction.atomic():
                form.save()
        except IntegrityError:
            employee_id = form.cleaned_data["employee_id"]
            username = form.cleaned_data["username"]
            if User.objects.filter(employee_id__iexact=employee_id).exists():
                form.add_error(
                    "employee_id",
                    "An account with this Employee ID already exists.",
                )
            elif User.objects.filter(username__iexact=username).exists():
                form.add_error(
                    "username",
                    "An account with this username already exists.",
                )
            elif phone_number_is_registered(form.cleaned_data["phone_number"]):
                form.add_error(
                    "phone_number",
                    "An account with this phone number already exists.",
                )
            elif "ambulance_number" in form.cleaned_data and Ambulance.objects.filter(
                vehicle_number__iexact=form.cleaned_data["ambulance_number"]
            ).exists():
                form.add_error(
                    "ambulance_number",
                    "An ambulance with this number is already registered.",
                )
            elif (
                "driving_licence_number" in form.cleaned_data
                and Driver.objects.filter(
                    license_number__iexact=form.cleaned_data["driving_licence_number"]
                ).exists()
            ):
                form.add_error(
                    "driving_licence_number",
                    "This Driving Licence Number is already registered.",
                )
            elif (
                self.role == User.Role.DISPATCHER
                and User.objects.filter(role=User.Role.DISPATCHER).exists()
            ):
                form.add_error(
                    None,
                    "A Dispatcher account is already registered. Contact the system administrator.",
                )
            else:
                raise
            return self.form_invalid(form)
        clear_registration_otp(self.request, self.role)
        messages.success(self.request, self.success_message)
        return render(
            self.request,
            "accounts/registration_success.html",
            {
                "portal_title": self.portal_title,
                "portal_role_label": self.portal_role_label,
                "redirect_url": reverse(self.login_url_name),
                "approval_required": True,
            },
        )

    def get_success_url(self):
        return reverse(self.login_url_name)


class CallTakerRegistrationView(PortalRegistrationView):
    form_class = CallTakerRegistrationForm
    role = User.Role.CALL_TAKER
    portal_title = "Call-Taker"
    portal_role_label = "CALL-TAKER"
    login_url_name = "accounts:call_taker_login"
    send_otp_url_name = "accounts:call_taker_send_otp"
    verify_otp_url_name = "accounts:call_taker_verify_otp"
    success_message = "Call-Taker account created successfully! Please wait for administrator approval."


class DispatcherRegistrationView(PortalRegistrationView):
    form_class = DispatcherRegistrationForm
    role = User.Role.DISPATCHER
    portal_title = "Dispatcher"
    portal_role_label = "DISPATCHER"
    login_url_name = "accounts:dispatcher_login"
    send_otp_url_name = "accounts:dispatcher_send_otp"
    verify_otp_url_name = "accounts:dispatcher_verify_otp"
    success_message = "Dispatcher account created successfully! Please wait for administrator approval."


class DriverRegistrationView(PortalRegistrationView):
    form_class = DriverRegistrationForm
    role = User.Role.DRIVER
    portal_title = "Driver"
    portal_role_label = "DRIVER"
    login_url_name = "drivers:login"
    send_otp_url_name = "drivers:send_otp"
    verify_otp_url_name = "drivers:verify_otp"
    success_message = "Driver account created successfully! Please wait for administrator approval."


def logout_view(request):
    from django.contrib.auth import logout as auth_logout
    auth_logout(request)
    messages.info(request, "You have been logged out.")
    return redirect("home")


@login_required
def dashboard(request):
    if request.user.role == request.user.Role.DISPATCHER:
        return redirect("dispatcher:dashboard")
    if request.user.role == request.user.Role.DRIVER:
        return redirect("drivers:dashboard")
    if request.user.role == request.user.Role.PATIENT:
        return redirect("patients:dashboard")
    return redirect("home")
