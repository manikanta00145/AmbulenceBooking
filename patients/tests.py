from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from bookings.models import Booking, BookingStatusHistory
from patients.forms import CallTakerEmergencyRequestForm, EmergencyRequestForm
from patients.models import Patient


class EmergencyRequestFormTests(TestCase):
    def setUp(self):
        self.data = {
            "name": "Alex Patient",
            "contact_number": "555-010-0101",
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

    def test_call_taker_form_contains_only_required_dashboard_fields(self):
        form = CallTakerEmergencyRequestForm()

        self.assertEqual(
            tuple(form.fields),
            ("name", "contact_number", "number_of_patients", "location_address"),
        )
        self.assertEqual(
            [value for value, _ in form.fields["number_of_patients"].choices[1:]],
            list(range(1, 11)),
        )

    def test_call_taker_form_validates_and_saves_without_map_or_extra_fields(self):
        form = CallTakerEmergencyRequestForm(
            data={
                "name": "Taylor Patient",
                "contact_number": "+1 555 123 0001",
                "number_of_patients": "2",
                "location_address": "10 Main Street",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        patient = form.save_patient()
        self.assertEqual(patient.name, "Taylor Patient")
        self.assertEqual(patient.contact_number, "+1 555 123 0001")
        self.assertEqual(patient.gender, "")
        self.assertIsNone(patient.age)

    def test_call_taker_contact_and_patient_count_are_validated(self):
        data = {
            "name": "Taylor Patient",
            "contact_number": "not a phone",
            "number_of_patients": "11",
            "location_address": "10 Main Street",
        }
        form = CallTakerEmergencyRequestForm(data=data)

        self.assertFalse(form.is_valid())
        self.assertIn("contact_number", form.errors)
        self.assertIn("number_of_patients", form.errors)

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

    def test_call_taker_dashboard_shows_database_stats_and_role_scoped_cases(self):
        call_taker = User.objects.create_user(username="dashboard-call-taker")
        another_call_taker = User.objects.create_user(username="another-call-taker")
        self.client.force_login(call_taker)
        patient = Patient.objects.create(
            name="Dashboard Patient",
            contact_number="555-0101",
        )
        Booking.objects.create(
            patient=patient,
            number_of_patients=2,
            emergency_type="Emergency",
            location_address="12 River Road",
            created_by=call_taker,
            status=Booking.Status.PENDING,
        )
        Booking.objects.create(
            patient=Patient.objects.create(
                name="Completed Patient",
                contact_number="555-0102",
            ),
            number_of_patients=1,
            emergency_type="Emergency",
            location_address="14 Lake Road",
            created_by=call_taker,
            status=Booking.Status.COMPLETED,
        )
        Booking.objects.create(
            patient=Patient.objects.create(
                name="Other Operator Patient",
                contact_number="555-0103",
            ),
            number_of_patients=1,
            emergency_type="Emergency",
            location_address="16 Hill Road",
            created_by=another_call_taker,
            status=Booking.Status.PENDING,
        )

        response = self.client.get(reverse("patients:create"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "patients/call_taker_dashboard.html")
        self.assertEqual(response.context["solved_count"], 1)
        self.assertEqual(response.context["pending_count"], 1)
        self.assertEqual(response.context["total_count"], 2)
        self.assertContains(response, "Dashboard Patient")
        self.assertContains(response, "Completed Patient")
        self.assertNotContains(response, "Other Operator Patient")
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertContains(response, "call-taker-dashboard.css")
        self.assertContains(response, "call-taker-dashboard.js")
        self.assertContains(response, "/static/images/call-taker-hero-ambulance.png")
        self.assertContains(response, "Welcome Back,")
        self.assertContains(response, "Call-Taker!")
        self.assertContains(response, "Number of Patients")
        self.assertContains(response, "REQUESTED AT")
        self.assertContains(response, "ACTION")

    def test_dispatcher_keeps_existing_new_request_page(self):
        dispatcher = User.objects.create_user(
            username="request-dispatcher",
            role=User.Role.DISPATCHER,
        )
        self.client.force_login(dispatcher)

        response = self.client.get(reverse("patients:create"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "patients/patient_form.html")

    def test_home_and_auth_pages_render(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="hero-image"')
        self.assertContains(response, "/static/images/ambulence-homepage.png")
        self.assertContains(response, "/static/css/home.css")
        self.assertNotContains(response, "Ambulance dispatch, made clear.")
        self.assertContains(
            response,
            f'{reverse("accounts:call_taker_login")}?next={reverse("patients:create")}',
        )
        self.assertContains(
            response,
            f'{reverse("accounts:dispatcher_login")}?next={reverse("dispatcher:dashboard")}',
        )
        self.assertContains(
            response,
            f'{reverse("drivers:login")}?next={reverse("drivers:dashboard")}',
        )
        self.assertEqual(self.client.get(reverse("accounts:login")).status_code, 200)
        self.assertEqual(self.client.get(reverse("accounts:register")).status_code, 200)

    def test_authenticated_users_see_the_existing_homepage_and_role_dashboard_link(self):
        portal_dashboards = (
            (User.Role.CALL_TAKER, "patients:create"),
            (User.Role.DISPATCHER, "dispatcher:dashboard"),
            (User.Role.DRIVER, "drivers:dashboard"),
        )

        for index, (role, dashboard_name) in enumerate(portal_dashboards):
            with self.subTest(role=role):
                user = User.objects.create_user(
                    username=f"homepage-{index}",
                    role=role,
                )
                self.client.force_login(user)

                response = self.client.get(reverse("home"))

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'class="hero-image"')
                self.assertContains(response, "/static/images/ambulence-homepage.png")
                self.assertContains(response, reverse(dashboard_name))
                self.assertNotContains(response, "Ambulance dispatch, made clear.")
                self.client.logout()
