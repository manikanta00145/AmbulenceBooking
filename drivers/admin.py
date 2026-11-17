from django.contrib import admin

from drivers.models import Driver

admin.site.site_title = "Ambulance Driver Administration"


@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = (
        "driver_name",
        "user",
        "user_email",
        "phone_number",
        "license_number",
        "created_at",
    )
    search_fields = (
        "driver_name",
        "user__username",
        "user__email",
        "phone_number",
        "license_number",
    )
    readonly_fields = ("created_at",)
    autocomplete_fields = ("user",)

    @admin.display(description="Email")
    def user_email(self, driver):
        return driver.user.email
