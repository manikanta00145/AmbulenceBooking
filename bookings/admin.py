from django.contrib import admin

from bookings.models import AmbulanceAssignment, Booking, BookingStatusHistory


class BookingStatusHistoryInline(admin.TabularInline):
    model = BookingStatusHistory
    extra = 0
    readonly_fields = ("old_status", "new_status", "changed_by", "changed_at", "note")
    can_delete = False


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("booking_id", "patient", "status", "assigned_ambulance", "requested_at")
    list_filter = ("status", "requested_at")
    search_fields = ("booking_id", "patient__name", "patient__contact_number")
    readonly_fields = ("booking_id", "requested_at")
    inlines = [BookingStatusHistoryInline]


@admin.register(AmbulanceAssignment)
class AmbulanceAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "booking",
        "ambulance",
        "assigned_by",
        "assigned_at",
        "assignment_status",
        "released_at",
    )
    list_filter = ("assignment_status",)
    readonly_fields = ("assigned_at",)
