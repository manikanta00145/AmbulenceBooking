from django.contrib import admin

from patients.models import GeocodingCache, NominatimRequestState, Patient


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("name", "contact_number", "email", "age", "created_at")
    search_fields = ("name", "contact_number", "email", "user__username")
    readonly_fields = ("created_at",)


@admin.register(GeocodingCache)
class GeocodingCacheAdmin(admin.ModelAdmin):
    list_display = ("address", "latitude", "longitude", "expires_at")
    search_fields = ("address", "display_name")


@admin.register(NominatimRequestState)
class NominatimRequestStateAdmin(admin.ModelAdmin):
    list_display = ("id", "last_request_at")
