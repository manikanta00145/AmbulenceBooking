# Ambulance Management and Dispatch

A Django academic/demo application for call takers, a single dispatcher, and ambulance drivers. It supports emergency intake, ambulance assignment, driver status updates, GPS location updates, and assignment/status history.

> This is not a replacement for a functioning emergency helpline. Do not rely on it for real emergency response without substantial operational, security, availability, and safety engineering.

For Docker Desktop setup on Windows 11, see [DOCKER_SETUP.md](./DOCKER_SETUP.md).
For local MySQL Server setup, see [MYSQL_SETUP.md](./MYSQL_SETUP.md).

## Local setup

Requires Python 3.10+, pip, and MySQL 8.0. Django is configured to use MySQL only.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Set the local MySQL credentials in .env before setup.
python setup_mysql.py
python manage.py createsuperuser
python manage.py runserver
```

Run commands with `python` after activating `.venv`, or use `.\.venv\Scripts\python.exe manage.py ...` explicitly. Do not use `py manage.py ...`: the Windows `py` launcher may select a global interpreter without the project's dependencies.

Open `http://127.0.0.1:8000/`. The project reads its database settings from `.env`; never commit that file.

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

## MySQL database

MySQL 8.0 is the default database. For a local MySQL Server, set `DB_USER=root`, `DB_PASSWORD`, `DB_HOST=localhost`, and `DB_PORT=3306` in `.env`, then run `python setup_mysql.py`. For Docker Compose, set unique `MYSQL_APP_PASSWORD` and `MYSQL_ROOT_PASSWORD` values; the container uses a dedicated `ambulance_app` account and Docker-managed schema/data.

```powershell
# Local MySQL Server:
python setup_mysql.py

# Or start Docker Compose and migrate from inside the app container:
docker compose up -d
docker compose exec web python manage.py migrate
```

Session data is stored server-side in MySQL (`django_session`); the browser cookie
contains only the session key. Run migrations to create the session table. Session
cookies are HttpOnly and SameSite=Lax; Secure is enabled by default when
`DJANGO_DEBUG` is false and can be overridden with `SESSION_COOKIE_SECURE`.
`CSRF_COOKIE_SECURE` follows the same default.

Run automated tests against the configured MySQL server. The MySQL account needs privileges to create and drop Django's test database:

```powershell
python manage.py test
```

Keep database credentials out of source control. The local MySQL account needs database creation/drop privileges only if you intend to run Django's tests against MySQL's separate test database.

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

1. A call taker records caller/patient details and searches the pickup address using the OpenStreetMap Nominatim search service. The returned point is only a suggestion: the call taker must review it, adjust the draggable/clickable Leaflet pin if needed, and explicitly confirm the location before saving.
2. The dispatcher reviews confirmed patient markers and assigns an available ambulance with a fresh GPS fix (five minutes or newer). Requests without confirmed coordinates cannot be assigned. The nearest eligible vehicle is highlighted using straight-line Haversine distance.
3. The driver accepts the assignment, then opens the booking's live navigation page. GPS sharing starts only after the driver selects **Start Navigation** and grants browser location permission. The page shows the ambulance, confirmed patient destination, OSRM road route, GPS accuracy/freshness, and remaining route estimate. Drivers can pause, resume, or stop GPS sharing.
4. GPS fixes are sent to `POST /drivers/location/` with CSRF protection, accuracy, and the browser fix timestamp. The server rejects invalid/stale fixes, rate-limits history writes, updates the ambulance's latest location, records `GPSLocation` history, and broadcasts updates to authenticated dispatchers through Channels. Dispatcher polling every five seconds remains as a fallback.
5. The driver starts the journey, marks arrival, records pickup, and completes the booking. Arrival is checked on the server against the active assignment, confirmed destination, fresh GPS, measured accuracy, and configured distance threshold. Status transitions remain in `BookingStatusHistory`.

Assignments and status transitions are recorded. Assignment operations use database transactions and row locks; production concurrency behavior depends on a database with effective row locking (such as MySQL or PostgreSQL), not SQLite.

## Patient address lookup

The call-taker portal makes one Nominatim search request only after the operator selects **Find location**; it does not autocomplete or send each keystroke. Successful addresses are cached in the application database for 30 days, and a shared MySQL row lock spaces uncached requests by at least one second across workers. Requests use a five-second timeout and an application-identifying `NOMINATIM_USER_AGENT`.

The default user agent is `AmbulenceBooking/1.0 (Django emergency dispatch application)`. For a public deployment, set `NOMINATIM_USER_AGENT` in `.env` to include a maintained contact address or application URL. Respect the [Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/); this free public service is capacity-limited and is not suitable for bulk or high-volume geocoding. If lookup fails or finds no result, operators can still set a manual map pin; no request can be saved or dispatched until coordinates are explicitly confirmed.

The existing `bookings` table already stores coordinates in `patient_latitude` and `patient_longitude`. New migrations add the confirmation/idempotency metadata and geocoding cache/rate-limit tables without removing booking or patient records. Existing bookings keep their coordinate values, but are unconfirmed by default and cannot be dispatched until their location has been verified.

For a manual end-to-end check, enter `PM Palem, Last Bus Stop, Visakhapatnam, Andhra Pradesh, India` in the call-taker portal, choose **Find location**, inspect and adjust the pin, check the confirmation box, and submit. Confirm the saved values in MySQL and the emergency marker/popup in the dispatcher dashboard. The assigned driver can open live navigation from the booking page; only a confirmed destination is used, and a stale ambulance position is never displayed as live. Start GPS sharing explicitly to move the ambulance marker and update the dispatcher's map. OSRM route requests are limited to significant movement or a time interval; the displayed estimate is not traffic-aware. If OSRM fails, the driver page labels its straight-line fallback clearly and does not show a fallback ETA.

The local default channel layer is in-memory and works for a single development process. Configure `REDIS_URL` to use Redis with `channels_redis` in a multi-worker deployment.

## GPS and deployment notes

Browser geolocation requires user permission and a secure context (HTTPS in production; localhost is allowed for development). Maps use Esri World Street Map tiles with service attribution; the public tile endpoint does not require an API key, but it does require internet access and is subject to Esri's terms and availability. Leaflet is loaded from a third-party CDN. Protect patient data, configure HTTPS and secure cookies, rotate `DJANGO_SECRET_KEY`, configure allowed hosts, backups, monitoring, and operational procedures before any real deployment.

Driver GPS write limits and arrival validation can be adjusted with `DRIVER_GPS_MIN_INTERVAL_SECONDS`, `DRIVER_GPS_MIN_MOVEMENT_METERS`, `DRIVER_GPS_HEARTBEAT_SECONDS`, `DRIVER_ARRIVAL_RADIUS_METERS`, and `DRIVER_ARRIVAL_MAX_ACCURACY_METERS` in `.env`. The additive `ambulances.0004` migration adds nullable GPS accuracy fields without deleting location or booking data. Back up the target MySQL database and review migration state before applying it.

## Checks

```powershell
python manage.py check
python manage.py test
```
