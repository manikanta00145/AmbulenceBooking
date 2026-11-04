from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render

from accounts.forms import LoginForm, RegistrationForm


class AccountLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm


@login_required
def dashboard(request):
    if request.user.role == request.user.Role.DISPATCHER:
        return redirect("dispatcher:dashboard")
    if request.user.role == request.user.Role.DRIVER:
        return redirect("drivers:dashboard")
    return redirect("home")


def register(request):
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.role = user.Role.CALL_TAKER
            user.save()
            login(request, user)
            messages.success(request, "Your call-taker account is ready.")
            return redirect("home")
    else:
        form = RegistrationForm()
    return render(request, "accounts/register.html", {"form": form})
