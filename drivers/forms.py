from django import forms

from ambulances.models import Ambulance
from bookings.models import Booking


DRIVER_TRANSITIONS = {
    Booking.Status.ASSIGNED: [Booking.Status.ACCEPTED],
    Booking.Status.ACCEPTED: [Booking.Status.EN_ROUTE],
    Booking.Status.EN_ROUTE: [Booking.Status.ARRIVED],
    Booking.Status.ARRIVED: [Booking.Status.PATIENT_PICKED_UP],
    Booking.Status.PATIENT_PICKED_UP: [Booking.Status.COMPLETED],
}


class BookingStatusForm(forms.Form):
    status = forms.ChoiceField()

    def __init__(self, *args, current_status, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].choices = [
            (status, Booking.Status(status).label)
            for status in DRIVER_TRANSITIONS.get(current_status, [])
        ]


class AvailabilityForm(forms.Form):
    availability_status = forms.ChoiceField(choices=Ambulance.Availability.choices)
