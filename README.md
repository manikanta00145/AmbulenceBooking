# Ambulance Management and Dispatch

A Django academic/demo application for call takers, a single dispatcher, and ambulance drivers. It supports emergency intake, ambulance assignment, driver status updates, GPS location updates, and assignment/status history.

> This is not a replacement for a functioning emergency helpline. Do not rely on it for real emergency response without substantial operational, security, availability, and safety engineering.

## Local setup

Requires Python 3.10+, pip, and MySQL 8.0.16+.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Run commands with `python` after activating `.venv`, or use `.\.venv\Scripts\python.exe manage.py ...` explicitly. Do not use `py manage.py ...`: the Windows `py` launcher may select a global interpreter without the project's dependencies.

Open `http://127.0.0.1:8000/`. The project reads its MySQL connection settings from `.env`; never commit that file.

On Windows with Python 3.15, Autobahn may attempt to compile an optional C extension without a local C++ toolchain. If dependency installation fails there, disable that optional extension for the install:

```powershell
$env:AUTOBAHN_USE_NVX = "0"
python -m pip install -r requirements.txt
Remove-Item Env:AUTOBAHN_USE_NVX
```

## Roles, registration, and account approval

- Call takers, drivers, and dispatchers have separate registration forms. Every form requires phone OTP verification; driver registrations also collect an AP ambulance registration and driving licence, call takers provide their office/station and assigned emergency centre, and dispatchers provide their dispatch centre and designation.
- In local development, set `DJANGO_DEBUG=true` in `.env` to use the development OTP backend. Click **Send OTP** and retrieve the code in the Django terminal. OTPs expire after five minutes, allow five attempts, and have a 60-second resend cooldown. The OTP is session-bound and stored as a password hash; it is never returned by the endpoint or printed unless `DEBUG` is enabled.
- Production must set `REGISTRATION_OTP_DELIVERY_BACKEND` to a trusted SMS delivery backend implementing `send_registration_otp(phone_number, otp)`. The included console backend refuses to print codes when `DEBUG` is false.
- The existing `users` table stores Employee IDs and call-taker/dispatcher details. Driver registrations use the existing `drivers` and `ambulances` tables for licence and ambulance number; no separate registration or OTP table is created.
- Registrations are created inactive with a pending approval status and cannot sign in until an authorized administrator approves them. Authorized staff with the `accounts.view_user` and `accounts.change_user` permissions can use the central approval dashboard at `/accounts/admin/approvals/`; it separates drivers, call takers, and dispatchers, records reviewer/timestamps and optional rejection reasons, and disables rejected accounts. Django stores passwords using its configured password hashers.
- Existing active accounts are preserved as approved when the approval migration runs. Existing inactive accounts are marked pending. Staff who register through a portal are never granted `is_staff` or superuser privileges.
- The database enforces at most one dispatcher account. If a dispatcher account already exists, another dispatcher registration is rejected; manage the existing account in admin.
- Driver profiles are created for driver-role accounts. Once approved, the dispatcher can register ambulances against active driver accounts.

## MySQL

Install MySQL and the Python dependencies. Create the database and an application account in MySQL:

```sql
CREATE DATABASE ambulance_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'ambulance_app'@'localhost' IDENTIFIED BY 'use-a-unique-password';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES
  ON ambulance_db.* TO 'ambulance_app'@'localhost';
```

Set the connection values in `.env` (the template is `.env.example`), then apply migrations. In particular, account migration `0004_user_employee_id` must be applied before registration queries `users.employee_id`; the approval fields are added by `0007_user_approval_status_and_audit`.

```powershell
python manage.py migrate
python manage.py check --database default
```

The MySQL account needs database creation/drop privileges only if you intend to run Django's tests using MySQL's separate test database; use a distinct developer/test account for that. Keep credentials out of source control.

To confirm the configured connection and tables:

```powershell
python manage.py showmigrations
python manage.py dbshell
```

In `dbshell`, list the project's tables with:

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'ambulance_db'
ORDER BY table_name;
```

In MySQL Workbench, connect to the local server, refresh **Schemas**, expand `ambulance_db` → **Tables**, and refresh the table list.

## Database relationships

- Each `Driver` has one Django `User`; each `Ambulance` is assigned to one driver profile.
- Each `Booking` references its patient and call-taker. Patient records are protected from deletion while bookings refer to them.
- `AmbulanceAssignment` records the booking, ambulance, and dispatcher; nullable unique active keys ensure a booking and ambulance cannot each have multiple active assignments on MySQL.
- `GPSLocation` records belong to an ambulance and are deleted with it. Booking status history is retained with its booking.
- Dispatcher role uniqueness is enforced by a unique database slot and a check constraint; the application's role checks protect call-taker, dispatcher, and driver views/actions.

## Workflow

1. A call taker records caller/patient details and the pickup address; coordinates are optional.
2. The dispatcher reviews pending requests and assigns an available ambulance with a fresh GPS fix (five minutes or newer). The nearest eligible vehicle is highlighted using straight-line Haversine distance.
3. The assigned driver accepts, travels, arrives, records pickup, and completes the booking.
4. While the driver dashboard is open and GPS permission is granted, browser coordinates are sent to the server and broadcast to dispatcher dashboards over Django Channels. A 30-second HTTP refresh is retained as a fallback.

Assignments and status transitions are recorded. Assignment operations use database transactions and row locks; production concurrency behavior depends on a database with effective row locking (such as MySQL or PostgreSQL), not SQLite.

The local default channel layer is in-memory and works for a single development process. Configure `REDIS_URL` to use Redis with `channels_redis` in a multi-worker deployment.

## GPS and deployment notes

Browser geolocation requires user permission and a secure context (HTTPS in production; localhost is allowed for development). Map tiles and Leaflet are loaded from third-party services. Protect patient data, configure HTTPS and secure cookies, rotate `DJANGO_SECRET_KEY`, configure allowed hosts, backups, monitoring, and operational procedures before any real deployment.

## Checks

```powershell
python manage.py check
python manage.py test
```
