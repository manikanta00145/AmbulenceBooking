from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from ambulances.models import Ambulance


class ApprovalDashboardTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="approval-admin",
            password="Admin-password-927!",
            email="admin@example.test",
        )
        self.client.force_login(self.admin)

    def create_staff_account(self, role, username, **kwargs):
        defaults = {
            "employee_id": f"EMP-{username}",
            "phone_number": "+1 555 123 0000",
            "role": role,
            "is_active": False,
            "approval_status": User.ApprovalStatus.PENDING,
        }
        defaults.update(kwargs)
        return User.objects.create_user(username=username, **defaults)

    def test_dashboard_shows_role_sections_counts_and_profile_fields(self):
        driver = self.create_staff_account(
            User.Role.DRIVER,
            "pending-driver",
            phone_number="+1 555 123 0001",
        )
        driver.driver_profile.license_number = "DL-APPROVAL-1"
        driver.driver_profile.save(update_fields=["license_number"])
        Ambulance.objects.create(
            vehicle_number="AP 31 AB 1234",
            driver=driver.driver_profile,
        )
        call_taker = self.create_staff_account(
            User.Role.CALL_TAKER,
            "pending-call-taker",
            phone_number="+1 555 123 0002",
            call_taker_office="North Station",
            assigned_emergency_centre="Central Centre",
        )
        dispatcher = self.create_staff_account(
            User.Role.DISPATCHER,
            "pending-dispatcher",
            phone_number="+1 555 123 0003",
            dispatch_centre="Main Dispatch",
            designation="Shift Lead",
        )

        response = self.client.get(reverse("accounts:approval_dashboard"))

        self.assertEqual(response.status_code, 200)
        for expected in (
            "Ambulance Drivers",
            "Call-Takers",
            "Dispatchers",
            "EMP-pending-driver",
            "AP 31 AB 1234",
            "DL-APPROVAL-1",
            "North Station",
            "Central Centre",
            "Main Dispatch",
            "Shift Lead",
            "View details",
            "Approve",
            "Reject",
        ):
            with self.subTest(expected=expected):
                self.assertContains(response, expected)
        self.assertEqual(len(response.context["sections"]), 3)
        self.assertEqual(
            [section["pending_count"] for section in response.context["sections"]],
            [1, 1, 1],
        )
        self.assertFalse(driver.is_staff or call_taker.is_staff or dispatcher.is_staff)

    def test_staff_without_user_permissions_cannot_access_approval_dashboard(self):
        self.client.force_login(
            User.objects.create_user(username="staff-without-permissions", is_staff=True)
        )

        response = self.client.get(reverse("accounts:approval_dashboard"))

        self.assertEqual(response.status_code, 403)

    def test_non_staff_cannot_access_approval_dashboard(self):
        self.client.force_login(User.objects.create_user(username="ordinary-user"))

        response = self.client.get(reverse("accounts:approval_dashboard"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_approval_and_rejection_update_status_and_reviewer_audit(self):
        account = self.create_staff_account(
            User.Role.CALL_TAKER,
            "reviewed-call-taker",
            phone_number="+1 555 123 0004",
            password="Rejected-account-password-927!",
        )
        approve_url = reverse(
            "accounts:review_registration",
            args=(account.pk, "approve"),
        )

        response = self.client.post(approve_url)
        account.refresh_from_db()

        self.assertRedirects(
            response,
            reverse("accounts:approval_dashboard"),
            fetch_redirect_response=False,
        )
        self.assertEqual(account.approval_status, User.ApprovalStatus.APPROVED)
        self.assertTrue(account.is_active)
        self.assertEqual(account.approved_by, self.admin)
        self.assertIsNotNone(account.approved_at)
        self.assertIsNone(account.rejected_at)

        reject_url = reverse(
            "accounts:review_registration",
            args=(account.pk, "reject"),
        )
        response = self.client.post(
            reject_url,
            {"rejection_reason": "Employment details need clarification."},
        )
        account.refresh_from_db()

        self.assertRedirects(
            response,
            reverse("accounts:approval_dashboard"),
            fetch_redirect_response=False,
        )
        self.assertEqual(account.approval_status, User.ApprovalStatus.REJECTED)
        self.assertFalse(account.is_active)
        self.assertEqual(account.rejected_by, self.admin)
        self.assertIsNotNone(account.rejected_at)
        self.assertEqual(
            account.rejection_reason,
            "Employment details need clarification.",
        )
        self.assertIsNone(account.approved_at)

        self.client.logout()
        login_response = self.client.post(
            reverse("accounts:call_taker_login"),
            {
                "username": account.username,
                "password": "Rejected-account-password-927!",
            },
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_review_action_requires_post_and_change_permission(self):
        account = self.create_staff_account(
            User.Role.DRIVER,
            "approval-action-check",
            phone_number="+1 555 123 0005",
        )
        url = reverse(
            "accounts:review_registration",
            args=(account.pk, "approve"),
        )
        self.assertEqual(self.client.get(url).status_code, 405)

        staff_user = User.objects.create_user(
            username="approval-view-only",
            is_staff=True,
        )
        staff_user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="accounts",
                codename="view_user",
            )
        )
        self.client.force_login(staff_user)

        response = self.client.post(url)

        self.assertEqual(response.status_code, 403)
        account.refresh_from_db()
        self.assertEqual(account.approval_status, User.ApprovalStatus.PENDING)

    def test_pending_active_accounts_cannot_login_or_use_protected_views(self):
        pending = self.create_staff_account(
            User.Role.DRIVER,
            "pending-active-driver",
            is_active=True,
            password="Pending-account-password-927!",
        )

        self.client.logout()
        response = self.client.post(
            reverse("drivers:login"),
            {
                "username": pending.username,
                "password": "Pending-account-password-927!",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "awaiting administrator approval")
        self.assertNotIn("_auth_user_id", self.client.session)

        self.client.force_login(pending)
        response = self.client.get(reverse("drivers:dashboard"))
        self.assertEqual(response.status_code, 403)
