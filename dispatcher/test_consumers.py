from datetime import timedelta

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser
from django.test import TransactionTestCase
from django.utils import timezone

from accounts.models import User
from ambulances.models import Ambulance
from ambulances.services import update_driver_location
from bookings.models import AmbulanceAssignment, Booking
from dispatcher.consumers import DispatcherLocationConsumer
from patients.models import Patient


class DispatcherLocationConsumerTests(TransactionTestCase):
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

    def test_driver_connections_are_rejected(self):
        driver = User.objects.create_user(
            username="websocket-driver",
            role=User.Role.DRIVER,
        )
        communicator = WebsocketCommunicator(
            DispatcherLocationConsumer.as_asgi(),
            "/ws/locations/",
        )
        communicator.scope["user"] = driver
        connected, close_code = async_to_sync(communicator.connect)()
        self.assertFalse(connected)
        self.assertEqual(close_code, 4403)

    def test_inactive_dispatcher_connections_are_rejected(self):
        dispatcher = User.objects.create_user(
            username="inactive-dispatcher",
            role=User.Role.DISPATCHER,
            is_active=False,
        )
        communicator = WebsocketCommunicator(
            DispatcherLocationConsumer.as_asgi(),
            "/ws/locations/",
        )
        communicator.scope["user"] = dispatcher
        connected, close_code = async_to_sync(communicator.connect)()
        self.assertFalse(connected)
        self.assertEqual(close_code, 4403)

    def test_driver_location_service_broadcasts_verified_assignment_update(self):
        dispatcher = User.objects.create_user(
            username="gps-event-dispatcher",
            role=User.Role.DISPATCHER,
        )
        driver = User.objects.create_user(
            username="gps-event-driver",
            role=User.Role.DRIVER,
        )
        call_taker = User.objects.create_user(username="gps-event-caller")
        patient = Patient.objects.create(
            name="GPS Event Patient",
            contact_number="555-0123",
        )
        ambulance = Ambulance.objects.create(
            vehicle_number="AMB-GPS-EVENT",
            driver=driver.driver_profile,
            latitude=12.0,
            longitude=77.0,
            location_updated_at=timezone.now() - timedelta(hours=1),
        )
        booking = Booking.objects.create(
            patient=patient,
            number_of_patients=1,
            emergency_type="Medical",
            location_address="Test",
            latitude=12.1,
            longitude=77.1,
            location_confirmed=True,
            created_by=call_taker,
            assigned_ambulance=ambulance,
            status=Booking.Status.ASSIGNED,
        )
        AmbulanceAssignment.objects.create(
            booking=booking,
            ambulance=ambulance,
            assigned_by=dispatcher,
        )
        async_to_sync(self._assert_driver_location_broadcast)(
            dispatcher,
            driver,
            booking,
        )

    async def _assert_driver_location_broadcast(self, dispatcher, driver, booking):
        communicator = WebsocketCommunicator(
            DispatcherLocationConsumer.as_asgi(),
            "/ws/locations/",
        )
        communicator.scope["user"] = dispatcher
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        updated_ambulance, updated = await database_sync_to_async(
            update_driver_location
        )(
            driver=driver,
            latitude="12.2",
            longitude="77.2",
            observed_at=str(timezone.now().timestamp() * 1000),
            accuracy_meters="6",
            booking_id=str(booking.pk),
        )
        self.assertTrue(updated)
        location = await communicator.receive_json_from()
        self.assertEqual(location["latitude"], 12.2)
        self.assertEqual(location["accuracy_meters"], 6)
        self.assertEqual(location["active_booking_id"], str(booking.pk))
        self.assertEqual(location["booking_status"], Booking.Status.ASSIGNED)
        self.assertFalse(location["gps_stale"])
        self.assertNotIn("patient", location)
        self.assertNotIn("patient_phone", location)
        self.assertEqual(updated_ambulance.pk, booking.assigned_ambulance_id)
        await communicator.disconnect()
