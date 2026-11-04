from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from ambulances.models import Ambulance
from ambulances.services import calculate_distance, find_nearest_ambulance
class DistanceTests(TestCase):
    def test_haversine_distance_is_in_kilometers(self):
        distance = calculate_distance(0, 0, 0, 1)
        self.assertAlmostEqual(distance, 111.19, places=1)

    def test_nearest_ambulance_ignores_stale_and_unavailable_vehicles(self):
        driver_near = User.objects.create_user(username="near", role=User.Role.DRIVER)
        driver_far = User.objects.create_user(username="far", role=User.Role.DRIVER)
        driver_stale = User.objects.create_user(username="stale", role=User.Role.DRIVER)
        nearest = Ambulance.objects.create(
            vehicle_number="AMB-NEAR",
            driver=driver_near,
            latitude=12.01,
            longitude=77.0,
            location_updated_at=timezone.now(),
        )
        Ambulance.objects.create(
            vehicle_number="AMB-FAR",
            driver=driver_far,
            latitude=15.0,
            longitude=77.0,
            location_updated_at=timezone.now(),
        )
        Ambulance.objects.create(
            vehicle_number="AMB-STALE",
            driver=driver_stale,
            latitude=12.001,
            longitude=77.0,
            location_updated_at=timezone.now() - timedelta(minutes=10),
        )
        self.assertEqual(find_nearest_ambulance(12.0, 77.0), nearest)

    def test_distance_rejects_out_of_range_coordinates(self):
        with self.assertRaises(ValueError):
            calculate_distance(91, 0, 0, 0)
