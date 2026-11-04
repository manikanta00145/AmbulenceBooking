from django.contrib import admin

from ambulances.models import Ambulance, GPSLocation


class GPSLocationInline(admin.TabularInline):
    model = GPSLocation
    extra = 0
    can_delete = False
    readonly_fields = ("latitude", "longitude", "recorded_at")


@admin.register(Ambulance)
class AmbulanceAdmin(admin.ModelAdmin):
    list_display = (
        "vehicle_number",
        "driver",
        "availability_status",
        "patient_status",
        "location_updated_at",
    )
    list_filter = ("availability_status", "patient_status")
    search_fields = ("vehicle_number", "driver__user__username", "driver__driver_name")
    inlines = [GPSLocationInline]
