from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from bookings.models import Booking, BookingStatusHistory
from patients.forms import EmergencyRequestForm


class EmergencyRequestFormTests(TestCase):
    def setUp(self):
        self.data = {
            "name": "Alex Patient",
            "contact_number": "555-0101",
            "relationship": "Parent",
            "number_of_patients": 1,
            "gender": "Female",
            "age": 34,
            "emergency_type": "Medical",
            "location_address": "10 Main Street",
            "latitude": "",
            "longitude": "",
        }

    def test_single_patient_requires_age_and_gender(self):
        self.data["gender"] = ""
        self.data["age"] = ""
        form = EmergencyRequestForm(data=self.data)
        self.assertFalse(form.is_valid())
        self.assertIn("gender", form.errors)
        self.assertIn("age", form.errors)

    def test_multiple_patients_omit_age_and_gender(self):
        self.data.update(number_of_patients=2, gender="", age="")
        form = EmergencyRequestForm(data=self.data)
        self.assertTrue(form.is_valid(), form.errors)
        patient = form.save_patient()
        self.assertIsNone(patient.age)
        self.assertEqual(patient.gender, "")

    def test_coordinates_must_be_provided_as_a_pair(self):
        self.data["latitude"] = "12.5"
        form = EmergencyRequestForm(data=self.data)
        self.assertFalse(form.is_valid())
        self.assertIn("latitude", form.errors)

    def test_call_taker_request_creates_patient_booking_and_initial_history(self):
        call_taker = User.objects.create_user(username="call-taker")
        self.client.force_login(call_taker)
        response = self.client.post(reverse("patients:create"), self.data)
        self.assertEqual(response.status_code, 302)
        booking = Booking.objects.get()
        self.assertEqual(booking.patient.name, "Alex Patient")
        self.assertEqual(booking.number_of_patients, 1)
        self.assertEqual(booking.created_by, call_taker)
        self.assertEqual(booking.status, Booking.Status.PENDING)
        self.assertEqual(
            BookingStatusHistory.objects.get(booking=booking).new_status,
            Booking.Status.PENDING,
        )
        self.assertEqual(
            self.client.get(reverse("bookings:detail", args=[booking.pk])).status_code,
            200,
        )

    def test_home_and_auth_pages_render(self):
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)
        self.assertEqual(self.client.get(reverse("accounts:login")).status_code, 200)
        self.assertEqual(self.client.get(reverse("accounts:register")).status_code, 200)
