from django.contrib import admin

from drivers.models import Driver

admin.site.site_title = "Ambulance Driver Administration"


@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ("driver_name", "user", "phone_number", "license_number", "created_at")
    search_fields = ("driver_name", "user__username", "phone_number", "license_number")
    readonly_fields = ("created_at",)
    autocomplete_fields = ("user",)
