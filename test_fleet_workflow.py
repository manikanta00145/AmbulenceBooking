import os
import random
import uuid
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ambulance_system.settings")
django.setup()

from decimal import Decimal
from django.test import Client
from django.urls import reverse
from accounts.models import User
from ambulances.models import Ambulance, GPSLocation
from bookings.models import AmbulanceAssignment, Booking, BookingStatusHistory
from drivers.models import Driver
from hospitals.models import Hospital
from patients.models import Patient


def run_fleet_test():
    print("=" * 60)
    print("STARTING FLEET & DISPATCH WORKFLOW TEST (MYSQL)")
    print("=" * 60)

    uid = uuid.uuid4().hex[:6]
    driver_uname = f"driver_{uid}"
    driver_email = f"driver_{uid}@test.com"
    driver_phone = f"+9198{random.randint(10000000, 99999999)}"
    driver_pwd = "MySecretX9#Special!"
    veh_num = f"AP 31 AB {random.randint(1000, 9999)}"

    # 1. Create and approve a Driver user
    print("\n[Step 1] Creating driver in MySQL...")
    driver_user = User.objects.create_user(
        username=driver_uname,
        email=driver_email,
        password=driver_pwd,
        first_name="Test",
        last_name="Driver",
        phone_number=driver_phone,
        role=User.Role.DRIVER,
        is_active=True,
        approval_status=User.ApprovalStatus.APPROVED,
    )
    driver_profile = driver_user.driver_profile
    driver_profile.license_number = f"DL-{uid.upper()}-999"
    driver_profile.address = "Driver Base Station, Visakhapatnam"
    driver_profile.save()
    print(f"   [PASS] Driver '{driver_uname}' created and profile saved in MySQL.")

    # 2. Create Ambulance and assign driver
    print("\n[Step 2] Creating and assigning ambulance in MySQL...")
    ambulance = Ambulance.objects.create(
        vehicle_number=veh_num,
        vehicle_type="Advanced Life Support",
        vehicle_model="Force Traveller",
        driver=driver_profile,
        latitude=Decimal("17.6868000"),
        longitude=Decimal("83.2185000"),
        location_accuracy_meters=Decimal("5.00"),
        availability_status=Ambulance.Availability.AVAILABLE,
        patient_status=Ambulance.PatientStatus.OFF,
    )
    GPSLocation.objects.create(
        ambulance=ambulance,
        latitude=Decimal("17.6868000"),
        longitude=Decimal("83.2185000"),
        accuracy_meters=Decimal("5.00"),
    )
    print(f"   [PASS] Ambulance '{veh_num}' created and linked to driver in MySQL.")

    # 3. Create emergency booking
    print("\n[Step 3] Creating emergency booking...")
    patient_user = User.objects.create_user(
        username=f"pt_{uid}",
        email=f"pt_{uid}@test.com",
        password=driver_pwd,
        role=User.Role.PATIENT,
        is_active=True,
        approval_status=User.ApprovalStatus.APPROVED,
    )
    patient = Patient.objects.create(
        user=patient_user,
        name="Emergency Patient",
        contact_number="+919876543210",
        address="Beach Road, Visakhapatnam",
        age=45,
        gender="Male",
    )
    booking = Booking.objects.create(
        patient=patient,
        emergency_type="Chest Pain",
        location_address="Beach Road, Visakhapatnam",
        latitude=Decimal("17.6869000"),
        longitude=Decimal("83.2186000"),
        location_confirmed=True,
        created_by=patient_user,
    )
    BookingStatusHistory.objects.create(
        booking=booking,
        old_status="",
        new_status=booking.status,
        changed_by=patient_user,
    )
    print(f"   [PASS] Booking {booking.pk} created in MySQL.")

    # 4. Assign ambulance to booking
    print("\n[Step 4] Assigning ambulance to booking...")
    booking.assigned_ambulance = ambulance
    booking.status = Booking.Status.ASSIGNED
    booking.save(update_fields=["assigned_ambulance", "status"])
    ambulance.availability_status = Ambulance.Availability.UNAVAILABLE
    ambulance.save(update_fields=["availability_status"])
    assignment = AmbulanceAssignment.objects.create(
        booking=booking,
        ambulance=ambulance,
        assigned_by=driver_user,
    )
    BookingStatusHistory.objects.create(
        booking=booking,
        old_status=Booking.Status.PENDING,
        new_status=Booking.Status.ASSIGNED,
        changed_by=driver_user,
        note="Assigned to ambulance",
    )
    print(f"   [PASS] Ambulance {ambulance.vehicle_number} assigned to booking {booking.pk}.")

    # 5. Driver logs in and views assigned booking
    print("\n[Step 5] Driver logs in and views dashboard...")
    driver_client = Client()
    login_resp = driver_client.post(reverse("drivers:login"), data={"username": driver_uname, "password": driver_pwd}, follow=True)
    assert login_resp.status_code == 200
    assert driver_client.session.get("_auth_user_id") is not None
    
    dash_resp = driver_client.get(reverse("drivers:dashboard"))
    assert dash_resp.status_code == 200
    assert str(booking.pk) in dash_resp.content.decode()
    print("   [PASS] Driver dashboard displays assigned booking from MySQL.")

    # 6. Driver updates booking status sequence
    print("\n[Step 6] Driver advances booking status in MySQL...")
    booking_url = reverse("drivers:booking", args=[booking.pk])
    
    # Accept
    resp = driver_client.post(booking_url, data={"status": Booking.Status.ACCEPTED}, follow=True)
    assert resp.status_code == 200
    booking.refresh_from_db()
    assert booking.status == Booking.Status.ACCEPTED

    # En Route
    resp = driver_client.post(booking_url, data={"status": Booking.Status.EN_ROUTE}, follow=True)
    assert resp.status_code == 200
    booking.refresh_from_db()
    assert booking.status == Booking.Status.EN_ROUTE

    # Arrived
    resp = driver_client.post(booking_url, data={"status": Booking.Status.ARRIVED}, follow=True)
    assert resp.status_code == 200
    booking.refresh_from_db()
    assert booking.status == Booking.Status.ARRIVED

    # Patient Picked Up
    resp = driver_client.post(booking_url, data={"status": Booking.Status.PATIENT_PICKED_UP}, follow=True)
    assert resp.status_code == 200
    booking.refresh_from_db()
    assert booking.status == Booking.Status.PATIENT_PICKED_UP
    ambulance.refresh_from_db()
    assert ambulance.patient_status == Ambulance.PatientStatus.ON

    # Completed
    resp = driver_client.post(booking_url, data={"status": Booking.Status.COMPLETED}, follow=True)
    assert resp.status_code == 200
    booking.refresh_from_db()
    assert booking.status == Booking.Status.COMPLETED
    ambulance.refresh_from_db()
    assert ambulance.patient_status == Ambulance.PatientStatus.OFF
    assert ambulance.availability_status == Ambulance.Availability.AVAILABLE
    print("   [PASS] Status transition workflow (Accepted -> En Route -> Arrived -> Patient Picked Up -> Completed) verified in MySQL.")

    # Cleanup
    print("\nCleaning up test records from MySQL...")
    AmbulanceAssignment.objects.filter(ambulance=ambulance).delete()
    BookingStatusHistory.objects.filter(booking=booking).delete()
    booking.delete()
    GPSLocation.objects.filter(ambulance=ambulance).delete()
    ambulance.delete()
    driver_profile.delete()
    patient.delete()
    driver_user.delete()
    patient_user.delete()
    print("   [PASS] Test records cleaned up successfully.")

    print("\n" + "=" * 60)
    print("FLEET & DRIVER DISPATCH TEST PASSED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    run_fleet_test()
