from django.shortcuts import render

from hospitals.models import Hospital


def directory(request):
    hospitals = Hospital.objects.filter(is_active=True).prefetch_related("ambulances")
    return render(request, "hospitals/directory.html", {"hospitals": hospitals})
