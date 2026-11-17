from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import role_required
from ambulances.forms import AmbulanceCreateForm, AmbulanceUpdateForm
from ambulances.models import Ambulance


@role_required("DISPATCHER")
def create(request):
    if request.method != "POST":
        return redirect("dispatcher:ambulances")
    form = AmbulanceCreateForm(request.POST)
    if form.is_valid():
        form.save()
        messages.success(request, "Ambulance registered successfully.")
    else:
        messages.error(request, "Ambulance was not registered. Check the vehicle and driver.")
    return redirect("dispatcher:ambulances")


@role_required("DISPATCHER")
def edit(request, ambulance_id):
    ambulance = get_object_or_404(Ambulance, pk=ambulance_id)
    if request.method == "POST":
        form = AmbulanceUpdateForm(request.POST, instance=ambulance)
        if form.is_valid():
            form.save()
            messages.success(request, f"Ambulance {ambulance.vehicle_number} updated.")
            return redirect("dispatcher:ambulances")
    else:
        form = AmbulanceUpdateForm(instance=ambulance)
    return render(
        request,
        "ambulances/ambulance_edit.html",
        {"form": form, "ambulance": ambulance},
    )


@role_required("DISPATCHER")
def delete(request, ambulance_id):
    ambulance = get_object_or_404(Ambulance, pk=ambulance_id)
    if request.method == "POST":
        vehicle_number = ambulance.vehicle_number
        ambulance.delete()
        messages.success(request, f"Ambulance {vehicle_number} deleted successfully.")
        return redirect("dispatcher:ambulances")
    return render(
        request,
        "ambulances/ambulance_confirm_delete.html",
        {"ambulance": ambulance},
    )


@role_required("DISPATCHER")
def detail(request, ambulance_id):
    ambulance = get_object_or_404(
        Ambulance.objects.select_related("driver", "hospital"),
        pk=ambulance_id,
    )
    return render(request, "ambulances/ambulance_detail.html", {"ambulance": ambulance})
