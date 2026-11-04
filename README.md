# Ambulance Management and Dispatch

A Django academic/demo application for call takers, a single dispatcher, and ambulance drivers. It supports emergency intake, ambulance assignment, driver status updates, GPS location updates, and assignment/status history.

> This is not a replacement for a functioning emergency helpline. Do not rely on it for real emergency response without substantial operational, security, availability, and safety engineering.

## Local setup

Requires Python 3.10+ and pip.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open `http://127.0.0.1:8000/`. SQLite is used by default. Change the development-only values in `.env` before deployment.

On Windows with Python 3.15, Autobahn may attempt to compile an optional C extension without a local C++ toolchain. If dependency installation fails there, disable that optional extension for the install:

```powershell
$env:AUTOBAHN_USE_NVX = "0"
python -m pip install -r requirements.txt
Remove-Item Env:AUTOBAHN_USE_NVX
```

## Roles and initial accounts

- Public registration creates **call-taker** accounts only.
- Create driver accounts in Django admin (`/admin/`) and assign them the `Ambulance driver` role.
- Change the initial superuser's role to `Dispatcher` in admin. A conditional database constraint ensures there can be only one dispatcher account.
- The dispatcher can register ambulances against active driver accounts.

## MySQL (optional)

Install a compatible MySQL server and Python client (`python -m pip install mysqlclient`), create a UTF-8 database, then set the following values in `.env`:

```dotenv
DB_ENGINE=django.db.backends.mysql
DB_NAME=ambulance_db
DB_USER=your_database_user
DB_PASSWORD=your_database_password
DB_HOST=localhost
DB_PORT=3306
```

Then run `python manage.py migrate`. Keep credentials out of source control.

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
