from django.contrib import admin

from notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "recipient", "booking", "created_at", "read_at")
    list_filter = ("created_at", "read_at")
    search_fields = ("title", "message", "recipient__username", "booking__booking_id")
    readonly_fields = ("created_at",)
