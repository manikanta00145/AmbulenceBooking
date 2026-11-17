from django.contrib.auth import views as auth_views
from django.urls import path

from accounts.models import User
from accounts.views import (
    AccountLoginView,
    CallTakerRegistrationView,
    CallTakerLoginView,
    DispatcherRegistrationView,
    DispatcherLoginView,
    PatientLoginView,
    PatientRegistrationView,
    dashboard,
    logout_view,
)
from accounts.otp_views import CallTakerRegistrationOtpView, DispatcherRegistrationOtpView
from accounts.approval_views import (
    approval_account_detail,
    approval_dashboard,
    review_registration,
)


app_name = "accounts"

urlpatterns = [
    path("admin/approvals/", approval_dashboard, name="approval_dashboard"),
    path(
        "admin/approvals/<int:user_id>/",
        approval_account_detail,
        name="approval_account_detail",
    ),
    path(
        "admin/approvals/<int:user_id>/<str:decision>/",
        review_registration,
        name="review_registration",
    ),
    path("login/", AccountLoginView.as_view(), name="login"),
    path("call-taker/login/", CallTakerLoginView.as_view(), name="call_taker_login"),
    path("dispatcher/login/", DispatcherLoginView.as_view(), name="dispatcher_login"),
    path("patient/login/", PatientLoginView.as_view(), name="patient_login"),
    path(
        "call-taker/register/send-otp/",
        CallTakerRegistrationOtpView.as_view(),
        {"action": "send"},
        name="call_taker_send_otp",
    ),
    path(
        "call-taker/register/verify-otp/",
        CallTakerRegistrationOtpView.as_view(),
        {"action": "verify"},
        name="call_taker_verify_otp",
    ),
    path(
        "dispatcher/register/send-otp/",
        DispatcherRegistrationOtpView.as_view(),
        {"action": "send"},
        name="dispatcher_send_otp",
    ),
    path(
        "dispatcher/register/verify-otp/",
        DispatcherRegistrationOtpView.as_view(),
        {"action": "verify"},
        name="dispatcher_verify_otp",
    ),
    path("logout/", logout_view, name="logout"),
    path(
        "register/",
        CallTakerRegistrationView.as_view(),
        name="register",
    ),
    path(
        "call-taker/register/",
        CallTakerRegistrationView.as_view(),
        name="call_taker_register",
    ),
    path(
        "dispatcher/register/",
        DispatcherRegistrationView.as_view(),
        name="dispatcher_register",
    ),
    path(
        "patient/register/",
        PatientRegistrationView.as_view(),
        name="patient_register",
    ),
    path("dashboard/", dashboard, name="dashboard"),
]
