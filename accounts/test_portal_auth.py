import time
from unittest.mock import patch

from django.contrib.auth.hashers import check_password
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from accounts.otp import otp_session_key
from ambulances.models import Ambulance
from drivers.models import Driver

PORTALS = (
    {
        "role": User.Role.CALL_TAKER,
        "login": "accounts:call_taker_login",
        "register": "accounts:call_taker_register",
        "send_otp": "accounts:call_taker_send_otp",
        "verify_otp": "accounts:call_taker_verify_otp",
        "heading": "SECURE CALL-TAKER ACCESS",
        "success_message": "Call-Taker account created successfully! Please wait for administrator approval.",
        "dashboard": "patients:create",
        "fields": {
            "call_taker_office": "Main Call-Taker Office",
            "assigned_emergency_centre": "Central Emergency Centre",
        },
        "labels": ("Call-Taker Office/Station", "Assigned Emergency Centre"),
        "other_fields": ("Dispatch Centre", "Ambulance Number"),
    },
    {
        "role": User.Role.DISPATCHER,
        "login": "accounts:dispatcher_login",
        "register": "accounts:dispatcher_register",
        "send_otp": "accounts:dispatcher_send_otp",
        "verify_otp": "accounts:dispatcher_verify_otp",
        "heading": "SECURE DISPATCHER ACCESS",
        "success_message": "Dispatcher account created successfully! Please wait for administrator approval.",
        "dashboard": "dispatcher:dashboard",
        "fields": {"dispatch_centre": "Central Dispatch", "designation": "Supervisor"},
        "labels": ("Dispatch Centre", "Designation"),
        "other_fields": ("Call-Taker Office/Station", "Ambulance Number"),
    },
    {
        "role": User.Role.DRIVER,
        "login": "drivers:login",
        "register": "drivers:register",
        "send_otp": "drivers:send_otp",
        "verify_otp": "drivers:verify_otp",
        "heading": "SECURE DRIVER ACCESS",
        "success_message": "Driver account created successfully! Please wait for administrator approval.",
        "dashboard": "drivers:dashboard",
        "fields": {
            "address": "1 Demo Road",
            "ambulance_number": "AP 31 AB 1234",
            "driving_licence_number": "DL-12345-2024",
        },
        "labels": ("Address", "Ambulance Number", "Driving Licence Number"),
        "other_fields": ("Dispatch Centre", "Call-Taker Office/Station"),
    },
)


class PortalTestMixin:
    def registration_data(self, portal, index=0, **overrides):
        data = {
            "full_name": "Jordan Example",
            "email": f"employee-{index}@example.invalid",
            "employee_id": f"EMP-{index + 100}",
            "username": f"employee-{index}",
            "phone_number": f"+1 555 123 {index:04d}",
            "password1": "Strong-password-927!",
            "password2": "Strong-password-927!",
        }
        data.update(portal["fields"])
        data.update(overrides)
        return data

    def send_otp(self, portal, phone_number, code="123456"):
        with (
            patch("accounts.otp_views.issue_otp", return_value=code),
            patch("accounts.otp_views.deliver_registration_otp") as delivery,
        ):
            response = self.client.post(
                reverse(portal["send_otp"]),
                {"phone_number": phone_number},
            )
        return response, code, delivery

    def verify_otp(self, portal, phone_number, code="123456"):
        return self.client.post(
            reverse(portal["verify_otp"]),
            {"phone_number": phone_number, "otp": code},
        )

    def verify_registration_phone(self, portal, data):
        response, code, delivery = self.send_otp(portal, data["phone_number"])
        self.assertEqual(response.status_code, 200, response.content)
        delivery.assert_called_once_with("+1555123" + data["phone_number"][-4:], code)
        verification = self.verify_otp(portal, data["phone_number"], code)
        self.assertEqual(verification.status_code, 200, verification.content)
        self.assertTrue(verification.json()["verified"])
        return code

    def expire_otp_cooldown(self, portal):
        session = self.client.session
        key = otp_session_key(portal["role"])
        if key in session:
            challenge = session[key]
            challenge["last_sent_at"] -= 61
            session[key] = challenge
            session.save()


class PortalPageTests(PortalTestMixin, TestCase):
    def test_portal_logins_and_registration_pages_have_role_specific_links(self):
        for portal in PORTALS:
            with self.subTest(role=portal["role"]):
                login_response = self.client.get(reverse(portal["login"]))
                self.assertEqual(login_response.status_code, 200)
                self.assertContains(login_response, portal["heading"])
                self.assertContains(login_response, reverse(portal["register"]))
                self.assertContains(login_response, "portal-auth.css")
                self.assertContains(login_response, "portal-auth.js")
                self.assertContains(login_response, "data-password-toggle")
                self.assertNotContains(login_response, "Ambulance_Dispatcher")

                registration_response = self.client.get(reverse(portal["register"]))
                self.assertEqual(registration_response.status_code, 200)
                self.assertContains(registration_response, "Send OTP")
                self.assertContains(registration_response, "Verify OTP")
                self.assertContains(registration_response, "Resend OTP")
                self.assertContains(registration_response, "Create Account")
                self.assertContains(
                    registration_response,
                    reverse(portal["login"]),
                )
                for label in (
                    "Full Name",
                    "Email",
                    "Employee ID",
                    "Username",
                    "Phone Number",
                    "Password",
                    "Confirm Password",
                    *portal["labels"],
                ):
                    self.assertContains(registration_response, label)
                for label in portal["other_fields"]:
                    self.assertNotContains(registration_response, label)

    def test_authenticated_driver_can_open_registration_from_login_link(self):
        driver = User.objects.create_user(
            username="existing-driver",
            role=User.Role.DRIVER,
        )
        self.client.force_login(driver)

        login_response = self.client.get(reverse("drivers:login"))
        register_url = reverse("drivers:register")
        self.assertContains(login_response, f'href="{register_url}">Create Account</a>')

        registration_response = self.client.get(register_url)

        self.assertEqual(registration_response.status_code, 200)
        self.assertTemplateUsed(registration_response, "accounts/portal_register.html")
        self.assertContains(registration_response, "Driver registration")
        self.assertContains(registration_response, "Driving Licence Number")

    def test_homepage_links_to_all_portal_login_pages(self):
        response = self.client.get(reverse("home"))
        for portal in PORTALS:
            with self.subTest(role=portal["role"]):
                self.assertContains(response, reverse(portal["login"]))


class RegistrationOtpTests(PortalTestMixin, TestCase):
    def test_otp_is_session_bound_hashed_and_not_returned_to_client(self):
        response, code, delivery = self.send_otp(
            PORTALS[0],
            "+1 555 123 0001",
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertNotIn(code, response.content.decode())
        delivery.assert_called_once_with("+15551230001", code)
        challenge = self.client.session[otp_session_key(PORTALS[0]["role"])]
        self.assertNotEqual(challenge["otp_hash"], code)
        self.assertTrue(check_password(code, challenge["otp_hash"]))
        self.assertEqual(challenge["session_key"], self.client.session.session_key)
        self.assertFalse(challenge["verified"])

    def test_phone_otp_workflows_are_independent_by_role(self):
        phone_number = "+1 555 123 0001"
        response, code, _ = self.send_otp(PORTALS[0], phone_number)
        self.assertEqual(response.status_code, 200)

        wrong_role_response = self.verify_otp(PORTALS[2], phone_number, code)
        self.assertEqual(wrong_role_response.status_code, 400)
        self.assertFalse(wrong_role_response.json().get("verified", False))

        correct_role_response = self.verify_otp(PORTALS[0], phone_number, code)
        self.assertEqual(correct_role_response.status_code, 200)
        self.assertTrue(correct_role_response.json()["verified"])

    def test_incorrect_code_is_limited_to_five_attempts(self):
        portal = PORTALS[0]
        phone_number = "+1 555 123 0002"
        self.send_otp(portal, phone_number)

        for attempt in range(5):
            response = self.verify_otp(portal, phone_number, "000000")
            with self.subTest(attempt=attempt + 1):
                self.assertIn(response.status_code, (400, 429))
                self.assertFalse(response.json().get("verified", False))

        challenge = self.client.session[otp_session_key(portal["role"])]
        self.assertEqual(challenge["attempts"], 5)
        self.assertEqual(challenge["otp_hash"], "")
        locked_response = self.verify_otp(portal, phone_number, "123456")
        self.assertEqual(locked_response.status_code, 400)

    def test_expired_code_is_rejected(self):
        portal = PORTALS[0]
        phone_number = "+1 555 123 0003"
        self.send_otp(portal, phone_number)
        session = self.client.session
        challenge = session[otp_session_key(portal["role"])]
        challenge["issued_at"] = time.time() - 301
        session[otp_session_key(portal["role"])] = challenge
        session.save()

        response = self.verify_otp(portal, phone_number)

        self.assertEqual(response.status_code, 400)
        self.assertIn("expired", response.json()["message"].lower())
        self.assertFalse(
            self.client.session[otp_session_key(portal["role"])]["verified"]
        )

    def test_resend_invalidates_previous_code_and_enforces_cooldown(self):
        portal = PORTALS[0]
        phone_number = "+1 555 123 0004"
        first_response, first_code, _ = self.send_otp(portal, phone_number, "123456")
        self.assertEqual(first_response.status_code, 200)

        cooldown_response, _, _ = self.send_otp(portal, phone_number, "654321")
        self.assertEqual(cooldown_response.status_code, 429)
        self.assertGreater(cooldown_response.json()["retry_after"], 0)

        session = self.client.session
        challenge = session[otp_session_key(portal["role"])]
        challenge["last_sent_at"] -= 61
        session[otp_session_key(portal["role"])] = challenge
        session.save()
        second_response, second_code, _ = self.send_otp(
            portal,
            phone_number,
            "654321",
        )
        self.assertEqual(second_response.status_code, 200)
        self.assertNotEqual(first_code, second_code)

        old_code_response = self.verify_otp(portal, phone_number, first_code)
        self.assertEqual(old_code_response.status_code, 400)
        new_code_response = self.verify_otp(portal, phone_number, second_code)
        self.assertEqual(new_code_response.status_code, 200)
        self.assertTrue(new_code_response.json()["verified"])

    def test_verification_is_bound_to_phone_and_browser_session(self):
        portal = PORTALS[0]
        phone_number = "+1 555 123 0005"
        self.send_otp(portal, phone_number)

        other_phone_response = self.verify_otp(
            portal,
            "+1 555 123 0006",
        )
        self.assertEqual(other_phone_response.status_code, 400)

        other_client = Client()
        other_session_response = other_client.post(
            reverse(portal["verify_otp"]),
            {"phone_number": phone_number, "otp": "123456"},
        )
        self.assertEqual(other_session_response.status_code, 400)

    def test_missing_otp_cannot_create_account(self):
        portal = PORTALS[0]
        data = self.registration_data(portal)
        response = self.client.post(reverse(portal["register"]), data)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "account created successfully")
        self.assertContains(
            response,
            "Verify this phone number with OTP before creating your account.",
        )
        self.assertFalse(User.objects.filter(username=data["username"]).exists())

    def test_otp_endpoint_requires_csrf(self):
        portal = PORTALS[0]
        csrf_client = Client(enforce_csrf_checks=True)

        response = csrf_client.post(
            reverse(portal["send_otp"]),
            {"phone_number": "+1 555 123 0007"},
        )

        self.assertEqual(response.status_code, 403)


class PortalRegistrationTests(PortalTestMixin, TestCase):
    def test_each_role_registration_saves_role_data_and_requires_approval(self):
        for index, portal in enumerate(PORTALS):
            with self.subTest(role=portal["role"]):
                data = self.registration_data(portal, index=index)
                self.verify_registration_phone(portal, data)
                response = self.client.post(reverse(portal["register"]), data)

                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, "accounts/registration_success.html")
                self.assertContains(response, portal["success_message"])
                self.assertContains(
                    response,
                    f'data-redirect-url="{reverse(portal["login"])}"',
                )
                self.assertContains(response, "registration-success.js")
                user = User.objects.get(employee_id=data["employee_id"])
                self.assertEqual(user.role, portal["role"])
                self.assertFalse(user.is_active)
                self.assertFalse(user.is_staff)
                self.assertFalse(user.is_superuser)
                self.assertEqual(
                    user.approval_status,
                    User.ApprovalStatus.PENDING,
                )
                self.assertEqual(user.first_name, "Jordan")
                self.assertEqual(user.last_name, "Example")
                self.assertTrue(user.check_password(data["password1"]))
                self.assertNotIn("_auth_user_id", self.client.session)

                if portal["role"] == User.Role.CALL_TAKER:
                    self.assertEqual(user.call_taker_office, data["call_taker_office"])
                    self.assertEqual(
                        user.assigned_emergency_centre,
                        data["assigned_emergency_centre"],
                    )
                elif portal["role"] == User.Role.DISPATCHER:
                    self.assertEqual(user.dispatch_centre, data["dispatch_centre"])
                    self.assertEqual(user.designation, data["designation"])
                else:
                    driver = Driver.objects.get(user=user)
                    ambulance = Ambulance.objects.get(driver=driver)
                    self.assertEqual(driver.license_number, data["driving_licence_number"])
                    self.assertEqual(ambulance.vehicle_number, "AP 31 AB 1234")

    def test_duplicate_username_employee_id_and_phone_are_rejected(self):
        existing = User.objects.create_user(
            username="existing",
            employee_id="EMP-DUP",
            phone_number="+15551234567",
        )
        cases = (
            (
                PORTALS[0],
                {"username": "existing", "employee_id": "EMP-NEW", "phone_number": "+1 555 111 0001"},
                "A user with that username already exists.",
            ),
            (
                PORTALS[2],
                {"username": "new-employee", "employee_id": "emp-dup", "phone_number": "+1 555 111 0002"},
                "An account with this Employee ID already exists.",
            ),
            (
                PORTALS[1],
                {"username": "new-phone", "employee_id": "EMP-PHONE", "phone_number": "+1 (555) 123-4567"},
                "An account with this phone number already exists.",
            ),
        )

        for index, (portal, overrides, error) in enumerate(cases):
            with self.subTest(error=error):
                data = self.registration_data(portal, index=index + 10, **overrides)
                response, code, _ = self.send_otp(portal, data["phone_number"])
                if error == "An account with this phone number already exists.":
                    self.assertEqual(response.status_code, 400)
                else:
                    self.assertEqual(response.status_code, 200)
                    verification = self.verify_otp(portal, data["phone_number"], code)
                    self.assertEqual(verification.status_code, 200)
                registration_response = self.client.post(reverse(portal["register"]), data)
                self.assertEqual(registration_response.status_code, 200)
                self.assertContains(registration_response, error)
                self.assertFalse(
                    User.objects.filter(username=data["username"]).exclude(pk=existing.pk).exists()
                )

    def test_phone_number_has_a_database_uniqueness_key(self):
        User.objects.create_user(
            username="phone-owner",
            phone_number="+1 (555) 765-4321",
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(
                username="duplicate-phone-owner",
                phone_number="+15557654321",
            )

    def test_driver_vehicle_format_and_duplicate_vehicle_and_licence_are_rejected(self):
        existing_driver = User.objects.create_user(
            username="registered-driver",
            role=User.Role.DRIVER,
        )
        existing_driver.driver_profile.license_number = "DL-EXISTING"
        existing_driver.driver_profile.save(update_fields=["license_number"])
        Ambulance.objects.create(
            vehicle_number="AP 31 AB 1234",
            driver=existing_driver.driver_profile,
        )

        portal = PORTALS[2]
        invalid_data = self.registration_data(
            portal,
            index=30,
            ambulance_number="KA 01 AA 0001",
            driving_licence_number="DL-NEW",
        )
        invalid_response, _, _ = self.send_otp(portal, invalid_data["phone_number"])
        self.assertEqual(invalid_response.status_code, 200)
        invalid_result = self.client.post(reverse(portal["register"]), invalid_data)
        self.assertContains(invalid_result, "Use the AP 31 AB 1234 vehicle number format.")

        vehicle_data = self.registration_data(
            portal,
            index=31,
            ambulance_number="ap31ab1234",
            driving_licence_number="DL-NEW",
        )
        self.expire_otp_cooldown(portal)
        vehicle_otp, _, _ = self.send_otp(portal, vehicle_data["phone_number"])
        self.assertEqual(vehicle_otp.status_code, 200)
        self.verify_otp(portal, vehicle_data["phone_number"])
        vehicle_result = self.client.post(reverse(portal["register"]), vehicle_data)
        self.assertContains(vehicle_result, "An ambulance with this number is already registered.")

        licence_data = self.registration_data(
            portal,
            index=32,
            ambulance_number="AP 31 AC 1234",
            driving_licence_number="dl-existing",
        )
        self.expire_otp_cooldown(portal)
        licence_otp, _, _ = self.send_otp(portal, licence_data["phone_number"])
        self.assertEqual(licence_otp.status_code, 200)
        self.verify_otp(portal, licence_data["phone_number"])
        licence_result = self.client.post(reverse(portal["register"]), licence_data)
        self.assertContains(licence_result, "This Driving Licence Number is already registered.")

    def test_password_mismatch_is_rejected_after_phone_verification(self):
        portal = PORTALS[0]
        data = self.registration_data(
            portal,
            password2="Not-the-same-password!",
        )
        self.verify_registration_phone(portal, data)

        response = self.client.post(reverse(portal["register"]), data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The two password fields didn’t match.")
        self.assertFalse(User.objects.filter(username=data["username"]).exists())

    def test_existing_dispatcher_blocks_registration(self):
        User.objects.create_user(
            username="existing-dispatcher",
            role=User.Role.DISPATCHER,
        )
        portal = PORTALS[1]
        data = self.registration_data(portal, index=40)
        self.verify_registration_phone(portal, data)

        response = self.client.post(reverse(portal["register"]), data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "A Dispatcher account is already registered. Contact the system administrator.",
        )
        self.assertFalse(User.objects.filter(username=data["username"]).exists())

    def test_successful_registration_clears_otp_challenge(self):
        portal = PORTALS[0]
        data = self.registration_data(portal, index=41)
        self.verify_registration_phone(portal, data)

        response = self.client.post(reverse(portal["register"]), data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, portal["success_message"])
        self.assertContains(
            response,
            f'data-redirect-url="{reverse(portal["login"])}"',
        )
        self.assertNotIn(otp_session_key(portal["role"]), self.client.session)


class OtpDeliveryTests(TestCase):
    @override_settings(
        DEBUG=True,
        REGISTRATION_OTP_DELIVERY_BACKEND="accounts.otp_delivery.console_otp_delivery",
    )
    def test_send_endpoint_prints_code_in_development_without_returning_it(self):
        otp = "012345"
        with (
            patch("accounts.otp_views.issue_otp", return_value=otp),
            patch("builtins.print") as print_mock,
        ):
            response = self.client.post(
                reverse("drivers:send_otp"),
                {"phone_number": "+1 555 123 0009"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(otp, response.content.decode())
        print_mock.assert_called_once()
        self.assertIn(otp, print_mock.call_args.args[0])

    @override_settings(DEBUG=True)
    def test_console_delivery_prints_otp_only_in_debug(self):
        from accounts.otp_delivery import console_otp_delivery

        with patch("builtins.print") as print_mock:
            console_otp_delivery("+15551230000", "123456")

        print_mock.assert_called_once()
        self.assertIn("123456", print_mock.call_args.args[0])

    @override_settings(DEBUG=False)
    def test_console_delivery_refuses_to_print_outside_debug(self):
        from django.core.exceptions import ImproperlyConfigured

        from accounts.otp_delivery import console_otp_delivery

        with patch("builtins.print") as print_mock:
            with self.assertRaises(ImproperlyConfigured):
                console_otp_delivery("+15551230000", "123456")

        print_mock.assert_not_called()

    @override_settings(REGISTRATION_OTP_DELIVERY_BACKEND="")
    def test_send_otp_reports_missing_production_delivery_backend(self):
        with patch("accounts.otp_views.issue_otp", return_value="123456"):
            response = self.client.post(
                reverse("drivers:send_otp"),
                {"phone_number": "+1 555 123 0008"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertNotIn("123456", response.content.decode())


class PortalLoginAccessTests(TestCase):
    def test_active_users_can_log_in_only_through_their_portal(self):
        for index, portal in enumerate(PORTALS):
            with self.subTest(role=portal["role"]):
                user = User.objects.create_user(
                    username=f"active-{index}",
                    password="Strong-password-927!",
                    role=portal["role"],
                )
                response = self.client.post(
                    reverse(portal["login"]),
                    {"username": user.username, "password": "Strong-password-927!"},
                )

                self.assertRedirects(
                    response,
                    reverse(portal["dashboard"]),
                    fetch_redirect_response=False,
                )
                self.client.logout()

    def test_wrong_role_is_rejected_by_portal_login(self):
        for index, portal in enumerate(PORTALS):
            user = User.objects.create_user(
                username=f"wrong-role-{index}",
                password="Strong-password-927!",
                role=portal["role"],
            )
            other_portal = PORTALS[(index + 1) % len(PORTALS)]
            with self.subTest(role=portal["role"], portal=other_portal["role"]):
                response = self.client.post(
                    reverse(other_portal["login"]),
                    {"username": user.username, "password": "Strong-password-927!"},
                )

                self.assertEqual(response.status_code, 200)
                self.assertContains(
                    response,
                    "This account is not authorized to use this portal.",
                )
                self.assertNotIn("_auth_user_id", self.client.session)

    def test_pending_accounts_cannot_log_in_until_approved(self):
        pending = User.objects.create_user(
            username="pending-driver",
            password="Strong-password-927!",
            role=User.Role.DRIVER,
            is_active=False,
            approval_status=User.ApprovalStatus.PENDING,
        )

        response = self.client.post(
            reverse("drivers:login"),
            {"username": pending.username, "password": "Strong-password-927!"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

        pending.is_active = True
        pending.approval_status = User.ApprovalStatus.APPROVED
        pending.save(update_fields=["is_active", "approval_status"])
        response = self.client.post(
            reverse("drivers:login"),
            {"username": pending.username, "password": "Strong-password-927!"},
        )
        self.assertRedirects(
            response,
            reverse("drivers:dashboard"),
            fetch_redirect_response=False,
        )

    def test_role_protected_pages_return_forbidden_to_other_roles(self):
        call_taker = User.objects.create_user(username="call-taker-access-check")
        self.client.force_login(call_taker)

        response = self.client.get(reverse("drivers:dashboard"))

        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_role_redirect_uses_matching_portal(self):
        for route, login_route in (
            ("drivers:dashboard", "drivers:login"),
            ("dispatcher:dashboard", "accounts:dispatcher_login"),
        ):
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertRedirects(
                    response,
                    f"{reverse(login_route)}?next={reverse(route)}",
                    fetch_redirect_response=False,
                )
