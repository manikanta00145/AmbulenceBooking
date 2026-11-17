from django.conf import settings
from django.contrib.sessions.models import Session
from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.models import User


class DatabaseSessionStorageTests(TestCase):
    def test_session_data_is_stored_in_database_and_cookie_contains_session_key(self):
        session = self.client.session
        session["workflow_state"] = "persisted"
        session.save()

        stored_session = Session.objects.get(session_key=session.session_key)
        self.assertEqual(stored_session.get_decoded()["workflow_state"], "persisted")
        self.assertEqual(
            self.client.cookies[settings.SESSION_COOKIE_NAME].value,
            session.session_key,
        )


class DispatcherUniquenessTests(TestCase):
    def test_only_one_dispatcher_can_be_created(self):
        User.objects.create_user(username="dispatcher-one", role=User.Role.DISPATCHER)
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(username="dispatcher-two", role=User.Role.DISPATCHER)

    def test_role_changes_keep_the_database_dispatcher_constraint_consistent(self):
        user = User.objects.create_user(username="dispatcher")
        user.role = User.Role.DISPATCHER
        user.save(update_fields=["role"])
        user.refresh_from_db()
        self.assertEqual(user.dispatcher_slot, "D")

        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.filter(pk=user.pk).update(role=User.Role.CALL_TAKER)


class RoleAuthorisationTests(TestCase):
    def test_superuser_is_allowed_through_role_checks(self):
        user = User.objects.create_superuser(username="admin", password="secret123")
        self.client.force_login(user)

        response = self.client.get("/dispatcher/")

        self.assertEqual(response.status_code, 200)
