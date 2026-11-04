from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.models import User


class DispatcherUniquenessTests(TestCase):
    def test_only_one_dispatcher_can_be_created(self):
        User.objects.create_user(username="dispatcher-one", role=User.Role.DISPATCHER)
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(username="dispatcher-two", role=User.Role.DISPATCHER)
