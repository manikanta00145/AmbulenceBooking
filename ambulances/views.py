from django.contrib import messages
from django.shortcuts import redirect

from accounts.decorators import role_required
from ambulances.forms import AmbulanceCreateForm


@role_required("DISPATCHER")
def create(request):
    if request.method != "POST":
        return redirect("dispatcher:ambulances")
    form = AmbulanceCreateForm(request.POST)
    if form.is_valid():
        form.save()
        messages.success(request, "Ambulance registered.")
    else:
        messages.error(request, "Ambulance was not registered. Check the vehicle and driver.")
    return redirect("dispatcher:ambulances")
