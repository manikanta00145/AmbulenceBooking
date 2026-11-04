from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from accounts.models import User
from dispatcher.consumers import DispatcherLocationConsumer


class DispatcherLocationConsumerTests(TestCase):
    def test_dispatcher_receives_location_group_updates(self):
        dispatcher = User.objects.create_user(
            username="dispatcher",
            role=User.Role.DISPATCHER,
        )
        async_to_sync(self._assert_location_update)(dispatcher)

    async def _assert_location_update(self, dispatcher):
        communicator = WebsocketCommunicator(
            DispatcherLocationConsumer.as_asgi(),
            "/ws/locations/",
        )
        communicator.scope["user"] = dispatcher
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        location = {
            "id": 1,
            "vehicle_number": "AMB-001",
            "latitude": 12.5,
            "longitude": 77.5,
        }
        await get_channel_layer().group_send(
            "dispatch_locations",
            {"type": "location.update", "location": location},
        )
        self.assertEqual(await communicator.receive_json_from(), location)
        await communicator.disconnect()

    def test_non_dispatcher_connections_are_rejected(self):
        communicator = WebsocketCommunicator(
            DispatcherLocationConsumer.as_asgi(),
            "/ws/locations/",
        )
        communicator.scope["user"] = AnonymousUser()
        connected, close_code = async_to_sync(communicator.connect)()
        self.assertFalse(connected)
        self.assertEqual(close_code, 4403)
