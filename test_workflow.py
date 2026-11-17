import os
import sys
import uuid
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ambulance_system.settings")
django.setup()

from django.test import Client
from django.db import connection
from django.urls import reverse
from accounts.models import User
from patients.models import Patient
from ambulances.models import Ambulance
from drivers.models import Driver
from bookings.models import Booking, BookingStatusHistory
from hospitals.models import Hospital

def run_workflow_test():
    print("=" * 60)
    print("STARTING FULL END-TO-END WORKFLOW TEST (MYSQL)")
    print("=" * 60)

    client = Client()
    import random
    uid = uuid.uuid4().hex[:6]
    test_username = f"patient_user_{uid}"
    test_email = f"patient_{uid}@testdomain.com"
    test_phone = f"+9198{random.randint(10000000, 99999999)}"
    test_password = "MySecretX9#Special!"
    full_name = f"Test Patient {uid}"

    # Step 1: Open Application
    print("\n[Step 1] Opening application home page...")
    resp = client.get(reverse("home"))
    assert resp.status_code == 200, f"Home page failed with {resp.status_code}"
    print("   [PASS] Home page loaded successfully (HTTP 200).")

    # Step 2: Register a new patient
    print("\n[Step 2] Registering a new patient via registration form...")
    register_url = reverse("accounts:patient_register")
    reg_data = {
        "full_name": full_name,
        "email": test_email,
        "phone_number": test_phone,
        "username": test_username,
        "age": 28,
        "gender": "Female",
        "address": "45 Beach Road, Visakhapatnam",
        "emergency_contact": "+919876543210",
        "password1": test_password,
        "password2": test_password,
    }
    resp = client.post(register_url, data=reg_data)
    assert resp.status_code == 200, f"Registration failed with {resp.status_code}: {resp.content.decode()[:300]}"
    if not ("Patient account created" in resp.content.decode() or "registration_success" in getattr(resp, "template_name", []) or "Registration successful" in resp.content.decode()):
        if hasattr(resp, "context") and resp.context and "form" in resp.context:
            print("Form errors:", resp.context["form"].errors)
        raise AssertionError(f"Registration failed: {resp.content.decode()[:300]}")
    print("   [PASS] Registration form submitted and succeeded.")

    # Step 3: Verify the user and patient record in MySQL
    print("\n[Step 3] Verifying user and patient records in MySQL database...")
    with connection.cursor() as cursor:
        cursor.execute("SELECT user_id, username, email, phone_number, password, role FROM users WHERE username = %s", [test_username])
        user_row = cursor.fetchone()
        assert user_row is not None, "User record not found in MySQL 'users' table!"
        user_id, uname, uemail, uphone, upassword, urole = user_row
        assert upassword != test_password, "Plain-text password found! Must be hashed."
        assert upassword.startswith("pbkdf2_sha256$") or "$" in upassword, "Password is not using standard hash format."
        assert urole == "PATIENT", f"Unexpected role {urole}"

        cursor.execute("SELECT patient_id, patient_name, contact_number, email, address, age, gender FROM patients WHERE user_id = %s", [user_id])
        patient_row = cursor.fetchone()
        assert patient_row is not None, "Patient record not found in MySQL 'patients' table!"
        pid, pname, pcontact, pemail, paddress, page, pgender = patient_row
        assert pname == full_name
        assert pemail == test_email
        assert page == 28
        assert pgender == "Female"
    print(f"   [PASS] Verified user '{test_username}' (ID: {user_id}) and patient '{pname}' in MySQL.")

    # Step 4: Log out
    print("\n[Step 4] Logging out...")
    resp = client.post(reverse("accounts:logout"))
    assert resp.status_code in (200, 302), f"Logout returned unexpected code {resp.status_code}"
    print("   [PASS] Logged out successfully.")

    # Step 5: Log in with registered credentials
    print("\n[Step 5] Logging in with the registered credentials...")
    login_url = reverse("accounts:patient_login")
    login_data = {
        "username": test_username,
        "password": test_password,
    }
    resp = client.post(login_url, data=login_data, follow=True)
    assert resp.status_code == 200, f"Login failed with status {resp.status_code}"
    assert resp.wsgi_request.user.is_authenticated, "User is not authenticated after login!"
    assert resp.wsgi_request.user.username == test_username, "Authenticated user mismatch!"
    
    # Verify session in MySQL django_session table
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM django_session")
        session_count = cursor.fetchone()[0]
        assert session_count > 0, "No active sessions found in MySQL 'django_session' table!"
    print(f"   [PASS] User '{test_username}' logged in; secure session verified in MySQL django_session.")

    # Step 6: Open the patient dashboard
    print("\n[Step 6] Opening patient dashboard...")
    dashboard_url = reverse("patients:dashboard")
    resp = client.get(dashboard_url)
    assert resp.status_code == 200, f"Patient dashboard returned {resp.status_code}"
    content = resp.content.decode()
    assert full_name in content, f"Patient full name '{full_name}' not found on dashboard!"
    print("   [PASS] Patient dashboard loaded with real MySQL data.")

    # Step 7: Update patient information
    print("\n[Step 7] Updating patient profile...")
    profile_url = reverse("patients:profile")
    updated_name = f"Updated {full_name}"
    updated_address = "99 VIP Road, Visakhapatnam, AP"
    profile_data = {
        "name": updated_name,
        "email": test_email,
        "contact_number": test_phone,
        "age": 29,
        "gender": "Female",
        "address": updated_address,
        "emergency_contact": "+919988776655",
    }
    resp = client.post(profile_url, data=profile_data, follow=True)
    assert resp.status_code == 200, f"Profile update failed with status {resp.status_code}"
    
    # Verify in MySQL
    with connection.cursor() as cursor:
        cursor.execute("SELECT patient_name, address, age FROM patients WHERE user_id = %s", [user_id])
        updated_row = cursor.fetchone()
        assert updated_row[0] == updated_name, f"Expected name '{updated_name}', got '{updated_row[0]}'"
        assert updated_row[1] == updated_address, f"Expected address '{updated_address}', got '{updated_row[1]}'"
        assert updated_row[2] == 29, f"Expected age 29, got '{updated_row[2]}'"
    print(f"   [PASS] Patient profile updated in MySQL (Name: '{updated_name}', Address: '{updated_address}').")

    # Step 8: Create an emergency ambulance booking
    print("\n[Step 8] Creating emergency ambulance booking...")
    booking_token = uuid.uuid4()
    booking_data = {
        "emergency_type": "Respiratory Distress",
        "location_address": "45 Beach Road, Visakhapatnam",
        "number_of_patients": 1,
        "submission_token": str(booking_token),
    }
    resp = client.post(reverse("patients:create"), data=booking_data, follow=True)
    assert resp.status_code == 200, f"Booking request failed with status {resp.status_code}"
    
    # Step 9: Verify the booking record in MySQL
    print("\n[Step 9] Verifying booking record in MySQL 'bookings' and 'bookings_bookingstatushistory'...")
    with connection.cursor() as cursor:
        cursor.execute("SELECT booking_id, emergency_type, pickup_address, booking_status FROM bookings WHERE submission_token = %s", [booking_token.hex])
        booking_row = cursor.fetchone()
        assert booking_row is not None, "Booking record not found in MySQL 'bookings' table!"
        bk_id, em_type, addr, bk_status = booking_row
        assert em_type == "Respiratory Distress"

        cursor.execute("SELECT COUNT(*) FROM bookings_bookingstatushistory WHERE booking_id = %s", [bk_id])
        history_count = cursor.fetchone()[0]
        assert history_count >= 1, "Status history not recorded in MySQL 'bookings_bookingstatushistory' table!"
    print(f"   [PASS] Booking {bk_id} verified in MySQL with status '{bk_status}' and {history_count} history entries.")

    # Step 10: Log in as admin and view the records
    print("\n[Step 10] Logging in as Admin to view records in Django Admin...")
    admin_username = f"admin_{uid}"
    admin_password = "AdminPassword123!"
    admin_user = User.objects.create_superuser(
        username=admin_username,
        email=f"admin_{uid}@testdomain.com",
        password=admin_password,
    )
    admin_client = Client()
    admin_login_resp = admin_client.post(reverse("admin:login"), data={"username": admin_username, "password": admin_password}, follow=True)
    assert admin_login_resp.status_code == 200, "Admin login failed!"
    
    # Check admin models
    admin_users_resp = admin_client.get(reverse("admin:accounts_user_changelist"))
    assert admin_users_resp.status_code == 200
    assert test_username in admin_users_resp.content.decode()

    admin_patients_resp = admin_client.get(reverse("admin:patients_patient_changelist"))
    assert admin_patients_resp.status_code == 200
    assert updated_name in admin_patients_resp.content.decode()

    admin_bookings_resp = admin_client.get(reverse("admin:bookings_booking_changelist"))
    assert admin_bookings_resp.status_code == 200
    formatted_bk_id = str(uuid.UUID(hex=bk_id)) if len(str(bk_id)) == 32 else str(bk_id)
    assert formatted_bk_id in admin_bookings_resp.content.decode() or str(bk_id) in admin_bookings_resp.content.decode()
    print("   [PASS] Admin authenticated and verified User, Patient, and Booking records in Django Admin.")

    # Step 11: Verify persistence after restarting connection / Django
    print("\n[Step 11] Simulating Django restart and checking persistence in MySQL...")
    connection.close() # Close and reset database connection
    
    with connection.cursor() as cursor:
        cursor.execute("SELECT username FROM users WHERE username = %s", [test_username])
        assert cursor.fetchone() is not None, "User lost after connection reset!"
        cursor.execute("SELECT patient_name FROM patients WHERE patient_name = %s", [updated_name])
        assert cursor.fetchone() is not None, "Patient lost after connection reset!"
        cursor.execute("SELECT booking_id FROM bookings WHERE booking_id = %s", [bk_id])
        assert cursor.fetchone() is not None, "Booking lost after connection reset!"
    print("   [PASS] All user, patient, and booking records permanently preserved in MySQL.")

    # Clean up test user & booking
    print("\nCleaning up test data from MySQL...")
    BookingStatusHistory.objects.filter(booking_id=bk_id).delete()
    Booking.objects.filter(booking_id=bk_id).delete()
    Patient.objects.filter(user_id=user_id).delete()
    User.objects.filter(pk=user_id).delete()
    admin_user.delete()
    print("   [PASS] Test data cleaned up successfully.")

    print("\n" + "=" * 60)
    print("ALL 11 END-TO-END WORKFLOW STEPS PASSED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    run_workflow_test()
