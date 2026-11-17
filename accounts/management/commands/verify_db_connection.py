import uuid
from decimal import Decimal
from django.conf import settings
from django.contrib.auth import authenticate
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, connections
from django.utils import timezone

from accounts.models import User
from ambulances.models import Ambulance
from bookings.models import AmbulanceAssignment, Booking, BookingStatusHistory, Payment
from drivers.models import Driver
from hospitals.models import Hospital
from notifications.models import Notification
from patients.models import Patient


class Command(BaseCommand):
    help = "Verify MySQL server connection, database existence, tables, and Django ORM operations."

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("=== MYSQL DATABASE INTEGRATION VERIFICATION ==="))

        # 1. MySQL Server Connection
        self.stdout.write("\n1. Testing MySQL server connection...")
        try:
            conn = connections["default"]
            conn.ensure_connection()
            with conn.cursor() as cursor:
                cursor.execute("SELECT VERSION()")
                db_version = cursor.fetchone()[0]
            self.stdout.write(
                self.style.SUCCESS(
                    f"   [OK] Connected to MySQL {db_version} at "
                    f"{conn.settings_dict.get('HOST')}:{conn.settings_dict.get('PORT')}"
                )
            )
        except Exception as exc:
            raise CommandError(f"   [FAIL] MySQL connection failed: {exc}")

        # 2. Database Existence
        self.stdout.write("\n2. Testing database existence...")
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT DATABASE()")
                active_db = cursor.fetchone()[0]
            expected_db = conn.settings_dict.get("NAME")
            if active_db != expected_db:
                raise CommandError(
                    f"   [FAIL] Connected database '{active_db}' does not match expected '{expected_db}'"
                )
            self.stdout.write(
                self.style.SUCCESS(f"   [OK] Database '{active_db}' exists and is currently selected.")
            )
        except Exception as exc:
            raise CommandError(f"   [FAIL] Database existence check failed: {exc}")

        # 3. Table Creation Check
        self.stdout.write("\n3. Testing table creation...")
        try:
            actual_tables = set(conn.introspection.table_names())
            from django.apps import apps
            expected_tables = {
                model._meta.db_table
                for model in apps.get_models(include_auto_created=True)
                if model._meta.managed and not model._meta.proxy
            }
            missing_tables = expected_tables - actual_tables
            if missing_tables:
                raise CommandError(f"   [FAIL] Missing tables: {', '.join(sorted(missing_tables))}")
            self.stdout.write(
                self.style.SUCCESS(
                    f"   [OK] All {len(expected_tables)} model tables exist in MySQL:"
                )
            )
            for tbl in sorted(expected_tables):
                self.stdout.write(f"        - {tbl}")
        except Exception as exc:
            raise CommandError(f"   [FAIL] Table verification failed: {exc}")

        # 4. User Insertion Check
        self.stdout.write("\n4. Testing User insertion (Django ORM)...")
        test_uid = uuid.uuid4().hex[:8]
        test_username = f"verify_patient_{test_uid}"
        test_email = f"patient_{test_uid}@example.com"
        test_phone = "+919876543210"
        test_raw_password = f"P@ssw0rd_{test_uid}"

        try:
            user = User.objects.create_user(
                username=test_username,
                email=test_email,
                password=test_raw_password,
                first_name="Verify",
                last_name="Patient",
                phone_number=test_phone,
                role=User.Role.PATIENT,
                is_active=True,
                approval_status=User.ApprovalStatus.APPROVED,
            )
            # Verify password hash
            if user.password == test_raw_password:
                raise CommandError("Password stored in plain text! Must be hashed.")
            if not user.password.startswith("pbkdf2_sha256$") and not user.password.startswith("argon2"):
                self.stdout.write(f"   [NOTE] Password hash format: {user.password.split('$')[0]}")
            self.stdout.write(
                self.style.SUCCESS(
                    f"   [OK] User inserted with ID {user.pk}, password correctly hashed."
                )
            )
        except Exception as exc:
            raise CommandError(f"   [FAIL] User insertion failed: {exc}")

        # 5. User Retrieval Check
        self.stdout.write("\n5. Testing User retrieval from MySQL...")
        try:
            retrieved_user = User.objects.get(username=test_username)
            assert retrieved_user.email == test_email
            assert retrieved_user.phone_number == test_phone
            self.stdout.write(
                self.style.SUCCESS(
                    f"   [OK] Retrieved user '{retrieved_user.username}' (ID: {retrieved_user.pk}) from MySQL."
                )
            )
        except Exception as exc:
            raise CommandError(f"   [FAIL] User retrieval failed: {exc}")

        # 6. User Authentication Check
        self.stdout.write("\n6. Testing User authentication against MySQL...")
        try:
            auth_user = authenticate(username=test_username, password=test_raw_password)
            if not auth_user:
                raise CommandError("Authentication failed with inserted credentials.")
            self.stdout.write(
                self.style.SUCCESS(
                    f"   [OK] User '{auth_user.username}' authenticated successfully using Django authentication."
                )
            )
        except Exception as exc:
            raise CommandError(f"   [FAIL] User authentication failed: {exc}")

        # 7. Booking Insertion Check
        self.stdout.write("\n7. Testing Booking insertion (Django ORM)...")
        try:
            patient = Patient.objects.create(
                user=user,
                name="Verify Patient Name",
                contact_number=test_phone,
                email=test_email,
                address="123 Test Hospital Road, Visakhapatnam",
                gender="Other",
                age=30,
            )
            booking = Booking.objects.create(
                patient=patient,
                number_of_patients=1,
                emergency_type="Cardiac Emergency",
                location_address="123 Test Hospital Road, Visakhapatnam",
                latitude=Decimal("17.6868000"),
                longitude=Decimal("83.2185000"),
                location_confirmed=True,
                created_by=user,
            )
            status_history = BookingStatusHistory.objects.create(
                booking=booking,
                old_status="",
                new_status=booking.status,
                changed_by=user,
                note="Initial verification booking",
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"   [OK] Booking created with ID {booking.pk} for Patient '{patient.name}'."
                )
            )
        except Exception as exc:
            raise CommandError(f"   [FAIL] Booking insertion failed: {exc}")

        # 8. Foreign-Key Relationships Check
        self.stdout.write("\n8. Testing Foreign-key relationships in MySQL...")
        try:
            # Query back with select_related and prefetch_related
            reloaded_booking = (
                Booking.objects.select_related("patient", "created_by")
                .prefetch_related("status_history")
                .get(pk=booking.pk)
            )
            assert reloaded_booking.patient.pk == patient.pk
            assert reloaded_booking.patient.user.pk == user.pk
            assert reloaded_booking.created_by.pk == user.pk
            assert reloaded_booking.status_history.count() >= 1

            # Test notification FK
            notif = Notification.objects.create(
                recipient=user,
                booking=booking,
                title="Test Verification",
                message="Testing FK relationship",
            )
            assert notif.recipient_id == user.pk
            assert notif.booking_id == booking.pk

            # Test payment FK
            payment = Payment.objects.create(
                booking=booking,
                amount=Decimal("500.00"),
                status=Payment.Status.PENDING,
                recorded_by=user,
            )
            assert payment.booking_id == booking.pk

            self.stdout.write(
                self.style.SUCCESS(
                    "   [OK] All Foreign-key relationships (Patient -> User, Booking -> Patient, "
                    "Booking -> User, StatusHistory -> Booking, Notification -> Booking, "
                    "Payment -> Booking) verified in MySQL."
                )
            )
        except Exception as exc:
            raise CommandError(f"   [FAIL] Foreign-key verification failed: {exc}")
        finally:
            # Cleanup test records
            self.stdout.write("\nCleaning up test records from MySQL...")
            try:
                Payment.objects.filter(booking=booking).delete()
                Notification.objects.filter(recipient=user).delete()
                BookingStatusHistory.objects.filter(booking=booking).delete()
                Booking.objects.filter(pk=booking.pk).delete()
                Patient.objects.filter(pk=patient.pk).delete()
                User.objects.filter(pk=user.pk).delete()
                self.stdout.write(self.style.SUCCESS("   [OK] Test records cleaned up cleanly."))
            except Exception as clean_err:
                self.stdout.write(self.style.WARNING(f"   [WARN] Cleanup notice: {clean_err}"))

        self.stdout.write(self.style.MIGRATE_LABEL("\n=== ALL DATABASE TESTS PASSED SUCCESSFULLY ==="))
