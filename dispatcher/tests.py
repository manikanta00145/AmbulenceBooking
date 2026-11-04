from django.test import TestCase
from django.urls import reverse

from accounts.models import User


class DispatcherPageTests(TestCase):
    def setUp(self):
        self.dispatcher = User.objects.create_user(
            username="dispatcher",
            role=User.Role.DISPATCHER,
        )

    def test_dispatcher_pages_render(self):
        self.client.force_login(self.dispatcher)
        for name in [
            "dispatcher:dashboard",
            "dispatcher:bookings",
            "dispatcher:ambulances",
        ]:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_locations_endpoint_requires_dispatcher_role(self):
        call_taker = User.objects.create_user(username="call-taker")
        self.client.force_login(call_taker)
        self.assertEqual(self.client.get(reverse("dispatcher:locations")).status_code, 403)
