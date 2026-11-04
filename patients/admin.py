from django.contrib import admin

from patients.models import Patient


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("name", "contact_number", "gender", "age", "created_at")
    search_fields = ("name", "contact_number")
    readonly_fields = ("created_at",)
