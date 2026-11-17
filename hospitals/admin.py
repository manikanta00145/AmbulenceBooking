from django.contrib import admin

from hospitals.models import Hospital


@admin.register(Hospital)
class HospitalAdmin(admin.ModelAdmin):
    list_display = ("name", "contact_number", "email", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "address", "contact_number", "email")
    readonly_fields = ("created_at", "updated_at")
