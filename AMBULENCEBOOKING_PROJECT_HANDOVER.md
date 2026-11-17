# AmbulenceBooking Project Handover

> **Purpose of this document:** a source-grounded transfer guide for the next developer or GitHub Copilot account. This document was updated after the live GPS implementation; treat checked-in source and actual migration state as authoritative when this document and runtime configuration differ.
>
> **Operational warning:** this is an academic/demo application, not a validated emergency dispatch service. Do not rely on it for real emergency response without substantial safety, availability, privacy, security, and operational work.

## 1. PROJECT INTRODUCTION

### Purpose and problem

AmbulenceBooking is a Django web application for recording ambulance requests, assigning ambulances, and coordinating drivers. It brings call takers, dispatchers, and drivers into one application and one configured relational database. It addresses the administrative problem of passing patient/request information and vehicle locations between separate operational roles.

The repository describes a workflow inspired by India's 108 ambulance service. It does **not** establish affiliation with, integration into, or operational readiness for an official 108 service.

### Implemented workflow

1. A staff member registers for a role-specific portal, verifies a phone number using a session-bound OTP, and waits for administrator approval.
2. An approved call taker records a patient and emergency request. The call-taker request currently uses the generic emergency type `"Emergency"`.
3. Before saving, the call taker looks up the address through Nominatim or places a pin manually, reviews/adjusts the Leaflet pin, and explicitly confirms the coordinates.
4. A dispatcher sees active emergencies and ambulance locations. Pending bookings can be assigned to an available ambulance with a recent GPS location. The suggestion is based on straight-line distance, not traffic.
5. The assigned driver accepts the booking, opens live navigation for the active assignment, and explicitly starts GPS sharing. The driver map uses the confirmed patient point and a fresh ambulance GPS fix, displays a road route/estimate when available, and exposes journey status history.
6. Completing or cancelling a booking releases the active assignment and returns the ambulance to available/no-patient state.

### Not implemented as a complete field-operations workflow

Live driver-side GPS tracking, OSRM road routing, and server-validated arrival are implemented in source. Real-device/browser behavior and external routing availability still require field-style testing. Hospital discovery/selection, government-hospital filtering, hospital navigation, a driver reject action, traffic-aware ambulance ranking, and a native/mobile driver application are not implemented. See [Current Development Status](#10-current-development-status).

## 2. TECHNOLOGY STACK

### Versions observed

| Component | Repository/runtime evidence |
|---|---|
| Python | Project documentation says Python 3.10+; the inspected local interpreter is Python 3.15.0. Docker image uses Python 3.12. |
| Django | Requirement `Django>=5.2,<6.0`; installed local version 5.2.19. |
| Database | MySQL 8.4 is the Docker target and the only supported Django backend. The SQLite source and external backup were deleted before import; no data migration was performed. |
| MySQL driver | `mysqlclient>=2.2.7,<3.0`; installed local version 2.3.0. |
| Django Channels | `channels[daphne]>=4.2,<5.0`; installed `channels==4.3.2`. |
| Redis channel layer | `channels-redis>=4.2,<5.0`; installed `channels-redis==4.3.0`. Optional; in-memory channel layer is the default when `REDIS_URL` is unset. |
| HTTP client | `requests>=2.32,<3.0`; installed local version 2.34.2. Used by the server-side Nominatim integration. |
| Environment loading | `python-dotenv>=1.0,<2.0`; installed local version 1.2.4. |
| Frontend | Django templates, HTML, CSS, and vanilla JavaScript. No frontend build system or package manifest was found. |
| Maps | Leaflet 1.9.4, loaded from unpkg CDN on call-taker and dispatcher map pages. |
| Map tiles | Esri World Street Map raster tiles with the service's source attribution in the map UI; no API key is required. |
| Geocoding | OpenStreetMap Nominatim `/search`, invoked server-side; no API key or paid service configured. |
| Route display | Dispatcher browser calls the public OSRM route service (`router.project-osrm.org`) for a selected assigned case. |

The versions above are the versions observed in this development environment, not a lockfile or deployment guarantee. `requirements.txt` contains compatible ranges, not exact pins.

## 3. COMPLETE PROJECT STRUCTURE

The following inventory excludes `.venv`, Python bytecode/cache directories, and the private `.env` file. Migration files are listed separately. Root `.env` was not read or copied into this document.

```text
AmbulenceBooking/
├── manage.py
├── requirements.txt
├── README.md
├── DOCKER_SETUP.md
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── .gitignore
├── .dockerignore
├── ambulance_system/
│   ├── settings.py
│   ├── urls.py
│   ├── views.py
│   ├── asgi.py
│   └── wsgi.py
├── accounts/
│   ├── models.py
│   ├── admin.py
│   ├── approval_views.py
│   ├── decorators.py
│   ├── forms.py
│   ├── otp.py
│   ├── otp_delivery.py
│   ├── otp_views.py
│   ├── urls.py
│   ├── views.py
│   ├── tests.py
│   ├── test_approval_workflow.py
│   ├── test_portal_auth.py
│   └── migrations/
├── patients/
│   ├── models.py
│   ├── forms.py
│   ├── geocoding.py
│   ├── urls.py
│   ├── views.py
│   ├── tests.py
│   └── migrations/
├── bookings/
│   ├── models.py
│   ├── services.py
│   ├── urls.py
│   ├── views.py
│   ├── admin.py
│   ├── tests.py
│   └── migrations/
├── ambulances/
│   ├── models.py
│   ├── forms.py
│   ├── services.py
│   ├── urls.py
│   ├── views.py
│   ├── admin.py
│   ├── tests.py
│   └── migrations/
├── drivers/
│   ├── models.py
│   ├── forms.py
│   ├── services.py
│   ├── signals.py
│   ├── urls.py
│   ├── views.py
│   ├── tests.py
│   └── migrations/
├── dispatcher/
│   ├── forms.py
│   ├── views.py
│   ├── consumers.py
│   ├── routing.py
│   ├── urls.py
│   ├── tests.py
│   └── test_consumers.py
├── templates/
│   ├── base.html
│   ├── home.html
│   ├── accounts/
│   ├── bookings/
│   ├── dispatcher/
│   ├── drivers/
│   └── patients/
└── static/
    ├── css/
    ├── images/
    └── js/
```

### Django app responsibilities

- **`accounts`** — custom `User`, roles, portal login/registration, OTP verification, and administrator approval/audit.
- **`patients`** — patient records, call-taker emergency form, Nominatim geocoding service and cache.
- **`bookings`** — emergency booking, status history, ambulance assignment records, detail page, and transactional assignment/status services.
- **`ambulances`** — ambulance fleet and GPS sample models, fleet forms, distance calculation, eligibility, validated/rate-limited location updates, and broadcast.
- **GPS interval/movement/heartbeat and arrival radius/accuracy settings** are configured through the environment and validated at startup.
- **`drivers`** — driver profile, dashboard, vehicle GPS/availability endpoints, and constrained booking status workflow.
- **`dispatcher`** — dispatcher pages, assignment UI, live location JSON endpoint, and authenticated Channels WebSocket consumer.

### Important frontend files

- **Templates:** `templates/home.html`; account portal/auth/approval templates; call taker `templates/patients/call_taker_dashboard.html`; dispatcher `templates/dispatcher/dashboard.html`, `booking_list.html`, `ambulance_list.html`; driver `templates/drivers/driver_dashboard.html`, `assigned_booking.html`, `no_ambulance.html`; booking details `templates/bookings/booking_details.html`.
- **JavaScript:** `static/js/call-taker-dashboard.js` handles the call-taker map and intake UX; `static/js/dispatcher.js` renders map markers, queue, route, and refreshes; `static/js/gps_tracking.js` reads browser geolocation and sends driver updates; `static/js/portal-auth.js` handles OTP/password UI; `static/js/booking.js` adjusts single-patient fields; `main.js` and `registration-success.js` support general UI.
- **CSS:** `static/css/dispatcher-dashboard.css`, `call-taker-dashboard.css`, `portal-auth.css`, `admin-approvals.css`, `dashboard.css`, `forms.css`, `home.css`, `registration-success.css`, and `style.css`.
- **Images:** `static/images/ambulence-homepage.png` and `call-taker-hero-ambulance.png`.

### Migration files present

- `accounts`: `0001_initial` through `0008_alter_user_role`
- `ambulances`: `0001_initial` through `0004_ambulance_location_accuracy_meters_and_more`
- `bookings`: `0001_initial` through `0004_booking_destination_hospital_payment`
- `drivers`: `0001_initial`, `0002_driver_address`
- `hospitals`: `0001_initial`
- `notifications`: `0001_initial`
- `patients`: `0001_initial` through `0005_patient_address_patient_email_and_more`

The earlier inspection found `bookings.0003` and `patients.0004` pending. On 2026-11-17, `ambulances.0004` was applied to the configured local MySQL database after a call-taker submission exposed its missing GPS accuracy column. Current `showmigrations` output confirms `ambulances.0004`, `bookings.0003`, `patients.0004`, and `patients.0005` are applied. Verify migration state separately in every other environment.

## 4. SYSTEM ARCHITECTURE

```text
Call taker browser
  ├─ HTML form + Leaflet pin
  └─ POST /patients/geocode/ (server calls Nominatim when cache misses)
             │
             ▼
       Django patients app ─────────────── Nominatim search service
             │                                  (rate-limited/cache)
             │ confirmed POST /patients/new/
             ▼
          MySQL (configured local runtime)
       users / patients / bookings / status history
             │
             ├── Dispatcher HTML + GET /dispatcher/locations/ (5-second polling)
             │        ├─ Leaflet patient and ambulance markers
             │        └─ OSRM request for a selected case route
             │
             ├── Channels group event for ambulance GPS/status changes
             │        └─ authenticated dispatcher WebSocket /ws/locations/
             │
             └── Driver HTML dashboard queries active assignments
                      ├─ explicit browser GPS watch → POST /drivers/location/
                      │     └─ ambulance + gps_locations + Channels broadcast
                      └─ journey status form → bookings/status history
```

All three portals share Django authentication and database models. The driver receives assignments by reading bookings joined to its ambulance; there is no separate mobile-app service or driver-specific JSON task-feed API.

`ambulance_system.asgi` routes HTTP to Django and WebSockets through `AuthMiddlewareStack`. `ambulance_system.wsgi` provides the conventional WSGI entry point. The WebSocket consumer only accepts a dispatcher-role user. Ambulance updates are group-broadcast; emergency and case-list changes are obtained from the HTTP polling endpoint rather than a booking WebSocket event.

## 5. DATABASE DOCUMENTATION

### Custom model tables and fields

Field types are Django model types. Names in parentheses are explicit database column names when they differ from the Python field name.

#### `users` — `accounts.User`

Custom user model inheriting Django `AbstractUser`.

- Primary key: `id` (`BigAutoField`, column `user_id`).
- Inherited: `username`, `password` hash, `first_name`, `last_name`, `email`, `is_staff`, `is_active`, `is_superuser`, `last_login`, `date_joined` (overridden to column `created_at`), and many-to-many `groups`/`user_permissions`.
- Custom: `phone_number`; nullable unique `phone_number_key`; nullable unique `employee_id`; `call_taker_office`; `assigned_emergency_centre`; `dispatch_centre`; `designation`; `role`; `dispatcher_slot`; `approval_status`; nullable `approved_by` and `rejected_by` self-FKs; `approved_at`; `rejected_at`; `rejection_reason`.
- `save()` normalizes a phone-number uniqueness key and maintains the unique dispatcher slot. A check constraint ensures the slot agrees with the role; at most one dispatcher can use the unique slot.

#### `patients` — `patients.Patient`

- Primary key: Python `id` (`BigAutoField`, column `patient_id`).
- `name` (`patient_name`, max 120), `contact_number` (max 30), `relationship` (`relationship_with_patient`, max 60, blank), `gender` (max 20, blank), nullable `age` (`PositiveSmallIntegerField`), `created_at`.
- Patient coordinates are not stored in this model; confirmed location is stored on the related booking.

#### `bookings` — `bookings.Booking`

- Primary key: `booking_id` (`UUIDField`, generated UUID).
- `patient` FK to `patients.Patient` (`PROTECT`); `created_by` FK to `accounts.User` (`PROTECT`, column `call_taker_id`); nullable `assigned_ambulance` FK to `ambulances.Ambulance` (`SET_NULL`).
- `number_of_patients` (`PositiveIntegerField`); `emergency_type` (max 80); `location_address` (max 250, column `pickup_address`).
- `latitude` and `longitude` are nullable `DecimalField(max_digits=10, decimal_places=7)` columns `patient_latitude` and `patient_longitude`.
- `location_confirmed` (`BooleanField`, default false); nullable unique `submission_token` (`UUIDField`) for idempotent call-taker submissions.
- `requested_at` (`DateTimeField`, indexed, column `booking_time`); indexed `status` (max 24, column `booking_status`).
- Status values: Pending, Assigned, Accepted, En Route, Arrived, Patient Picked Up, Completed, Cancelled.
- Model `clean()` validates patient count and requires age/gender for a one-patient booking. Form/service layers enforce location confirmation and dispatch eligibility.

#### `bookings_bookingstatushistory` — `bookings.BookingStatusHistory`

Django default table name; no explicit `db_table`.

- Auto primary key; `booking` FK (`CASCADE`); `old_status`; `new_status`; nullable `changed_by` FK to user (`SET_NULL`); `changed_at`; `note`.
- Records booking status transitions. It does not itself enforce the transition graph.

#### `ambulance_assignments` — `bookings.AmbulanceAssignment`

- Primary key: `id` (`BigAutoField`, column `assignment_id`).
- `booking` FK (`PROTECT`); `ambulance` FK (`PROTECT`); `assigned_by` FK to user (`PROTECT`, column `dispatcher_id`).
- `assigned_at`; nullable `released_at`; `assignment_status`; nullable unique `active_booking_key` UUID; nullable unique `active_ambulance_key` positive bigint.
- `save()` derives active/released status and nullable keys from `released_at`; the nullable unique keys enforce at most one active booking per ambulance and one active assignment per booking on supporting databases.

#### `drivers` — `drivers.Driver`

- Primary key: `id` (`BigAutoField`, column `driver_id`).
- `user` OneToOne FK to user (`CASCADE`); `driver_name`; `phone_number`; nullable unique `license_number`; `created_at`.
- `drivers.signals.ensure_driver_profile` creates a Driver profile after a driver-role User is saved.

#### `ambulances` — `ambulances.Ambulance`

- Primary key: `id` (`BigAutoField`, column `ambulance_id`).
- Unique `vehicle_number`; `driver` OneToOne FK to `Driver` (`PROTECT`).
- Nullable `latitude` and `longitude` decimal fields with world-range validators; nullable `location_accuracy_meters`; `location_updated_at` (column `last_location_update`); `patient_status` (`ON`/`OFF`); indexed `availability_status` (`Available`/`Unavailable`).

#### `gps_locations` — `ambulances.GPSLocation`

- Primary key: `id` (`BigAutoField`, column `location_id`).
- `ambulance` FK (`CASCADE`); required latitude/longitude decimal values with world-range validation; nullable `accuracy_meters`; indexed `recorded_at`.
- Historical location samples are retained by the model; no cleanup/retention job was found.

#### `patients_geocodingcache` — `patients.GeocodingCache`

Django default table name; model fields: auto primary key, unique SHA-256 `address_key`, original `address`, latitude/longitude decimals, `display_name`, indexed `expires_at`. Successful lookup entries are used for 30 days. This table was not present in the inspected live database because its migration was pending.

#### `patients_nominatimrequeststate` — `patients.NominatimRequestState`

Django default table name; primary key `id` (positive small integer, default 1), nullable `last_request_at`. Migration seeds row 1. Used with a process lock and `select_for_update()` for Nominatim spacing. This table was not present in the inspected live database because its migration was pending.

### Relationships

```text
User 1 ── 0..1 Driver 1 ── 0..1 Ambulance
User 1 ── many Booking (created_by)
Patient 1 ── many Booking
Ambulance 1 ── many Booking (assigned_ambulance, nullable)
Booking 1 ── many BookingStatusHistory
Booking 1 ── many AmbulanceAssignment
Ambulance 1 ── many AmbulanceAssignment
Ambulance 1 ── many GPSLocation
User 1 ── many BookingStatusHistory (changed_by, nullable)
User 1 ── many AmbulanceAssignment (assigned_by)
User 1 ── many User (approved_by/rejected_by audit self-relations)
```

The explicit delete policies are listed with each FK above. In particular, patient and call-taker records cannot be deleted while referenced by bookings; GPS history cascades with ambulance deletion.

### Other Django-managed tables

The inspected active MySQL schema also contains framework tables `auth_group`, `auth_group_permissions`, `auth_permission`, `django_admin_log`, `django_content_type`, `django_migrations`, `django_session`, `users_groups`, and `users_user_permissions`.

### Active database versus code schema

The earlier inspection found `bookings.0003` and `patients.0004` pending on the then-configured local MySQL database. After a call-taker POST failed because `ambulances.location_accuracy_meters` was absent, `ambulances.0004` was applied to local `ambulance_db` on 2026-11-17. It adds two nullable accuracy columns and does not rewrite existing rows. Current `showmigrations` confirms the listed migrations are applied locally; check the confirmed target and back it up before applying migrations in any other environment.

No patient/booking data rows, connection values, credentials, or `.env` contents are included here.

## 6. BACKEND IMPLEMENTATION

### Models and services

- Models and relationships are described in [Database Documentation](#5-database-documentation).
- `ambulances.services` validates coordinate ranges, accuracy, and the browser fix timestamp; verifies the driver's own ambulance and optional active booking assignment; applies configurable time/movement/heartbeat throttles; saves latest coordinates and `GPSLocation` accuracy history; and broadcasts authorized dispatcher updates on transaction commit. It also calculates Haversine distance and filters eligible ambulances by availability, patient state, active driver, coordinates, and five-minute GPS freshness.
- `bookings.services.assign_ambulance` uses an atomic transaction and row locks, checks dispatcher role, booking state, confirmed patient coordinates, ambulance availability/GPS/driver eligibility, then changes booking/ambulance state and creates assignment/history records.
- `bookings.services.record_status_change` saves status history and releases the active assignment on completion/cancellation.
- `drivers.services` validates that the acting driver owns an active assignment and that the requested transition is allowed. Arrival requires a confirmed destination, fresh GPS, sufficient GPS accuracy, and server-side proximity within the configured radius. Status changes remain in the existing booking-history model.
- `patients.geocoding` calls Nominatim with `requests.get`, JSON response, `limit=1`, five-second timeout, and configured User-Agent. It validates ranges and caches successful matches; service errors/no match return actionable error JSON. The call taker must still confirm the pin.
- There are no Django REST Framework serializers or serializer classes in this project. HTML forms, Django `Form`/`ModelForm`, and `JsonResponse` are used.

### Authentication and authorization

- `AUTH_USER_MODEL = "accounts.User"`; password hashing/authentication is provided by Django.
- Portal login forms require the portal's role and approved status. Call-taker, dispatcher, and driver registration requires phone OTP.
- New portal accounts are inactive and pending approval. Staff approval/rejection actions require Django staff access and `accounts.view_user`/`accounts.change_user` permissions as appropriate.
- `accounts.decorators.role_required` checks login, active state, approval status, and role (superusers bypass the role check).
- HTML POST forms use CSRF middleware. Geocoding, OTP, GPS, status, availability, and assignment mutations are POSTs.
- OTP challenges are session-bound, hashed, six digits, expire after five minutes, allow five attempts, and use a 60-second resend cooldown. The built-in console delivery backend is development-only; no SMS provider is included.

### Database configuration

`ambulance_system/settings.py` loads `.env` using `python-dotenv`. MySQL is the only supported backend; non-MySQL `DB_ENGINE` values raise a configuration error. MySQL uses environment variables for database name/user/password/host/port, UTF-8 MB4, and connection age 60 seconds. `channels` uses Redis when `REDIS_URL` is set and otherwise in-memory channels.

Docker Compose provides MySQL 8.4 with a persistent named volume and a Django web service. The previous SQLite source and external backup are no longer available in this checkout, and no application records were loaded into MySQL.

## 7. FRONTEND IMPLEMENTATION

- `templates/base.html` provides the shared site shell for most pages. The call-taker dashboard is a standalone dashboard document with its own CSS/JS links.
- Call-taker form accepts name, contact, patient count, address, hidden latitude/longitude, location-confirmation checkbox, and submission UUID. It displays the geocoding result and map pin. Input address edits clear the pin/coordinates/confirmation; clicking/dragging the Leaflet pin updates the coordinates and clears confirmation.
- Dispatcher dashboard includes statistics, a Leaflet map, a live queue, selected-case details, map legend, status fields, and a pending-bookings link. JavaScript uses `Map` instances keyed by ambulance ID and booking ID to update existing markers and avoid duplicates.
- Dispatcher JS polls `/dispatcher/locations/` every five seconds, updates existing markers from authenticated WebSocket events, and displays driver/vehicle/booking identity, journey status, GPS accuracy/freshness, and a remaining-route estimate when OSRM is available.
- Driver dashboard lists active assignments and availability controls. GPS sharing is started only by the driver's explicit action; the status panel separates browser permission, device GPS, accuracy, network, server sync, freshness, tracking, and navigation state.
- Live driver navigation is available at `/drivers/navigation/<booking_uuid>/`. It requires the driver's active assignment and a confirmed destination. The page uses `watchPosition` only after driver action, sends CSRF-protected fixes with accuracy and observed time, moves the ambulance marker, and requests OSRM routes only initially or after significant movement/time. A straight-line fallback is labeled and has no ETA.
- Existing `BookingStatusHistory`, `AmbulanceAssignment`, and `GPSLocation` models provide journey/status/assignment history; no duplicate journey table was introduced.
- Account portal UI includes role-specific login/registration links, OTP countdown and verification, password visibility toggle, and approval status messages.
- Existing UI styling is under `static/css/`. No application-wide redesign or frontend framework is present.

## 8. MAP AND GPS IMPLEMENTATION

### Leaflet maps and tiles

- Dispatcher map initializes at `[17.6868, 83.2185]`, zoom 11, and renders Esri World Street Map tiles with the service's required source attribution.
- Call-taker pin map initializes around Visakhapatnam at `[17.6868, 83.2185]`, zoom 12. It places a draggable marker from Nominatim results or a click; adjusting the marker changes the submitted coordinates.
- Dispatcher uses separate ambulance and patient Leaflet markers. Ambulances use vehicle/staleness styling; patient markers use a red pin. Marker identity is retained by ID and marker location/popup is updated on polling.
- Selecting an emergency focuses on the confirmed patient point (or ambulance point if there is no confirmed patient point). Popup includes patient name, case ID, emergency type, address, and contact number.

### Driver GPS path

1. The driver explicitly starts sharing on the navigation page (or driver dashboard); `static/js/gps_tracking.js` then calls `navigator.geolocation.watchPosition` with high accuracy.
2. The browser sends coordinates, accuracy, booking ID (on navigation), and fix timestamp to `POST /drivers/location/` with CSRF protection. It stops or pauses the watcher on driver action/page exit, queues updates during network loss, and enforces client-side interval/movement/heartbeat limits.
3. `ambulances.services.update_driver_location` validates ranges and fix freshness, row-locks the driver's ambulance, verifies any booking ownership/active assignment, applies server-side write limits, updates latest coordinates/accuracy/time, inserts `GPSLocation`, and publishes a Channels event on commit.
4. `DispatcherLocationConsumer` accepts only active dispatcher-role users and sends fleet updates with booking identity/status, GPS accuracy, and freshness. The dispatcher also polls fleet/case data every five seconds.

GPS requires browser permission and a secure context in deployment (localhost is allowed by browsers). If page is closed or permission denied, GPS does not update.

The in-app driver navigation page uses Leaflet to show the latest fresh ambulance point and confirmed patient destination, a moving ambulance marker, OSRM road geometry, remaining distance, and a non-traffic ETA when available. Missing/stale coordinates are not rendered as live; an unconfirmed destination blocks navigation. If OSRM fails, the page labels the direct line as a straight-line fallback and omits ETA.

### Patient location and geocoding

- Patient coordinates are on `Booking`, not `Patient`, and existing database columns are `patient_latitude`/`patient_longitude`.
- Nominatim query is initiated by the server at `https://nominatim.openstreetmap.org/search`; address lookup is not per-keystroke autocomplete.
- Positive results are cached for 30 days. Code serializes requests within a process and uses the `NominatimRequestState` row/DB lock to coordinate requests across MySQL workers, spacing uncached Nominatim queries by one second. Whether this works as intended on SQLite or a multi-process deployment without effective row locks is **NEEDS VERIFICATION**.
- User-Agent comes from `NOMINATIM_USER_AGENT`, with a development fallback. Public deployments should set an identifying value with contact/URL and respect [Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/).
- Geocoding is approximate and can return a locality or nearby feature. Dispatch requires explicit call-taker confirmation; unconfirmed coordinates are hidden from the dispatcher feed and driver navigation and assignment service refuses dispatch.

### Routing and limits

- Dispatcher uses OSRM's public route endpoint for a selected assigned case. Route response provides geometry/distance/duration when available. It is not a traffic-aware ambulance-ranking algorithm, and no live-traffic feed is configured.
- The dispatcher dashboard explicitly notes that verified district boundaries and hospital locations are not stored.
- Finding nearby government hospitals, selecting a destination, and hospital navigation are not implemented.

## 9. COMPLETED FEATURES

The following are supported by current source and/or automated tests:

- Custom role-aware accounts for call taker, dispatcher, and driver.
- Separate portal login/registration forms and OTP verification.
- Administrator account approval/rejection with reviewer and timestamp audit.
- One-dispatcher constraint, unique Employee ID, and phone-number uniqueness key.
- Driver profile creation and vehicle registration relationship.
- Patient/emergency intake and unique UUID booking IDs.
- Patient coordinates stored on Booking, call-taker map confirmation, geocoding failure/manual pin UX, positive lookup caching, and duplicate POST protection by submission token (code/migrations present; deployment schema pending).
- Dispatcher queue, availability filtering, nearest-by-Haversine suggestion, transactional assignment, status history, and eligibility checks including fresh GPS.
- Driver status workflow: Assigned → Accepted → En Route → Arrived → Patient Picked Up → Completed.
- Driver availability management outside active assignment.
- Browser GPS updates and GPS-location history rows.
- Explicit driver GPS start/pause/resume/stop controls, GPS permission/accuracy/network/sync/freshness status, rate-limited location history, and stale-fix rejection.
- Driver Leaflet live movement, confirmed-destination OSRM road route, distance/ETA display, and server-validated arrival by fresh/accurate GPS and configured radius.
- Dispatcher map for fleet and confirmed patient locations, periodic JSON refresh fallback, authenticated ambulance update WebSocket, booking/status correlation, and remaining-route display.
- Existing booking status/assignment history used for journey timeline; no duplicate journey model.
- Booking detail visibility checks for dispatcher, creating call taker, and assigned driver.
- MySQL-only configuration in Django settings.

## 10. CURRENT DEVELOPMENT STATUS

### Fully implemented (source-level)

- Account roles, OTP verification, staff approval workflow.
- Emergency/booking model, status-history model, assignment model, ambulance/driver models.
- Dispatcher and driver pages, assignment/status services, GPS post endpoint, dispatcher JSON endpoint and WebSocket.
- Geocoding and confirmation code path with cache/rate limiter.

### Partially implemented / needs environment verification

- **Patient geocoding deployment:** migrations for confirmation/idempotency and cache state were pending during the earlier inspection and are now applied in the configured local MySQL database. Verify them separately in any other deployment.
- **Call-taker live workflow:** source/tests exist, but actual Nominatim availability and exact result for the sample address were not verified against the live public API.
- **MySQL deployment support:** code/configuration exists; server version, production configuration, backup/restore, and concurrent transaction behavior are **UNKNOWN**.
- **Dispatcher real-time view:** ambulance GPS and assigned journey status are pushed by WebSocket; full emergency queue/patient data refreshes by five-second HTTP polling. Emergency data is not a separate WebSocket stream.
- **OSRM route:** route is requested only for a selected active assignment with both locations. Availability/accuracy of the external routing endpoint is not guaranteed.
- **Driver navigation:** live controls, GPS reporting, OSRM routing, status timeline, and server-side arrival checks are implemented in source and covered by focused backend tests. Real device permissions, public OSRM/tiles availability, and two-browser end-to-end tracking still need manual verification.

### Not implemented / unsupported

- Driver reject/decline action or reassignment-on-reject.
- Nearby government-hospital search, hospital table/data source, hospital selection, hospital routing, or completion-at-hospital workflow.
- Traffic-aware ambulance scoring, traffic conditions, or guaranteed arrival accuracy.
- Native Android/iOS driver application; the driver interface is a Django-rendered web dashboard.
- Dedicated REST serializers/API and versioned API.
- Automated external end-to-end tests for Nominatim, Esri map tiles, OSRM, or real browser/device GPS; use separate dispatcher/driver browser sessions for a manual movement test.
- Production SMS OTP provider, production monitoring, task queue, or automatic data retention for GPS records.

### Known limitations and risks

- The application describes itself as a demo and is not suitable for real emergency operations without extensive operational/safety assurance.
- Docker Compose and `.env.example` use MySQL. The SQLite source and external backup were deleted before import, so no legacy data is available in this checkout and no import was completed.
- `ambulances.0004` adds nullable location accuracy to ambulance and GPS history. It was applied to the configured local database on 2026-11-17 after the missing-column error; existing rows were not rewritten.
- DB-level one-second geocoding coordination depends on an effective row lock; SQLite does not provide MySQL-equivalent row locking.
- Call-taker path labels all cases `"Emergency"`; the general dispatcher-created emergency form supports an emergency type but no geocoding UX.
- A “nearest” vehicle is selected using straight-line distance, not OSRM travel duration or traffic.
- Driver status transitions are forward-only; there is no reject path.
- Government hospital location data is explicitly absent.
- Static assets and mapping/routing services use external CDNs/services and require network access.
- Git history/branch cleanliness is **UNKNOWN** in this inspection because `git.exe` was unavailable.

## 11. RECENT CHANGES

### What source evidence establishes

- Current source includes a Nominatim geocoding service, cache and request-state models, call-taker map confirmation, dispatcher patient markers, and driver coordinate exposure.
- This task added explicit live GPS controls, accurate/stale GPS validation, route progress, dispatcher event correlation, and arrival geofence checks. It generated `ambulances.0004_ambulance_location_accuracy_meters_and_more`; that migration was applied to the configured local MySQL database on 2026-11-17 after a missing-column error.
- Migrations `bookings.0003_booking_location_confirmed_booking_submission_token` and `patients.0004_geocodingcache_nominatimrequeststate` add confirmation/idempotency metadata and geocoding cache/rate-limit tables. They were applied in the configured local database, as confirmed by `showmigrations` on 2026-11-17.
- Relevant current implementation files are `patients/geocoding.py`, `patients/models.py`, `patients/forms.py`, `patients/views.py`, `patients/urls.py`, `templates/patients/call_taker_dashboard.html`, `static/js/call-taker-dashboard.js`, `static/css/call-taker-dashboard.css`, `dispatcher/views.py`, `static/js/dispatcher.js`, `bookings/services.py`, `templates/drivers/driver_dashboard.html`, and `templates/drivers/assigned_booking.html`. Tests cover those paths in the corresponding `patients`, `dispatcher`, `bookings`, and `drivers` test modules.

### What cannot be established

The repository's `.git` directory exists, but `git.exe` was not found on PATH or in the standard Windows Git installation directories. Therefore commit hashes, authors, branch, exact historical diffs, and whether the working tree is clean are **UNKNOWN**. The above is a description of current code and migration metadata, not a verified commit history.

## 12. PENDING DEVELOPMENT TASKS

| Priority | Task | Dependencies / notes |
|---|---|---|
| P0 | Back up each deployment target and verify its migration/schema state. | `ambulances.0004` is applied in the configured local database; other environments may differ. |
| P0 | Run two-browser call-taker → dispatcher → driver verification with simulated/device GPS, denied permission, offline/reconnect, stale fix, pause/resume, and assignment cancellation. | Requires a non-production DB with reviewed migrations, approved test accounts, HTTPS or localhost, and network access to map/OSRM. |
| P1 | Test MySQL concurrency/idempotency and geocoding rate-limit behavior across multiple workers. | Depends on an available MySQL test database; verify the DB row lock and 1-second minimum under concurrent uncached requests. |
| P1 | Decide and implement a driver reject/decline business workflow if the requirement still stands. | Requires policy for assignment release/reassignment and dispatcher notifications; do not infer reject semantics. |
| P1 | Decide whether real-time emergency queue changes are required rather than five-second polling. | Current socket pushes ambulance/booking status updates; full queue refresh still uses HTTP polling. |
| P2 | Define government hospital source, validation, data model/API, search radius, and routing policy. | Product/data-source decisions required; no existing hospital data/model exists. |
| P2 | Determine whether ambulance ranking should include road time/traffic and select an appropriate supported provider. | Existing nearest-vehicle logic is Haversine; public OSRM ETA is used only for a displayed route and is not traffic-backed. |
| P2 | Add production-ready OTP provider, operational logging/monitoring, retention/backups, and deployment hardening. | Configure provider, privacy/retention requirements, hosting, HTTPS, and secrets management. |

## 13. API DOCUMENTATION

No DRF routers, serializers, or versioned API are present. The following JSON endpoints are Django views. HTML endpoints may return redirects/messages rather than JSON.

| Endpoint | Method | Authentication | Request | Response / behavior |
|---|---|---|---|---|
| `/patients/geocode/` | POST | Approved CALL_TAKER role; session + CSRF | Form-encoded `address` (1–250 chars) | Success: `{"ok": true, "latitude": "...", "longitude": "...", "display_name": "...", "cached": bool}`. Lookup/no-result/provider errors return `{"ok": false, "error": "..."}`; invalid address is HTTP 400. `Cache-Control: private, no-store`. |
| `/dispatcher/locations/` | GET | Approved DISPATCHER role; session | None | `{"locations":[...],"emergencies":[...],"stats":{...}}`. Coordinate values are numbers or null. Patient coordinates are null unless confirmed. Response is private/no-store. |
| `/drivers/location/` | POST | Approved DRIVER role; session + CSRF | Form-encoded `latitude`, `longitude`, `accuracy_meters`, `observed_at` (browser fix epoch milliseconds); `booking_id` on navigation page | Success returns `updated`, vehicle, accepted/stored coordinates, accuracy, and server `updated_at`. Invalid/stale coordinates or fix, unauthorized booking, or missing ambulance returns `{"error":"..."}` HTTP 400. Rate-limited samples are not written to GPS history. Accepted samples update the ambulance, create `GPSLocation`, and publish a dispatcher event. |
| `/accounts/{call-taker,dispatcher,driver}/register/send-otp/` | POST | Session-bound; CSRF; no authenticated account required | Form-encoded `phone_number` | Success: `ok`, message, `expires_in` (300), `retry_after` (60). Invalid input HTTP 400, resend cooldown HTTP 429, unconfigured/unavailable delivery HTTP 503. |
| `/accounts/{call-taker,dispatcher,driver}/register/verify-otp/` | POST | Same session that requested OTP; CSRF | Form-encoded `phone_number`, `otp` | Success: `{"ok":true,"verified":true,"message":"Phone number verified."}`. Invalid/mismatched/expired challenge is HTTP 400; attempts/cooldown limits use HTTP 429. |
| `/drivers/register/send-otp/` | POST | Session-bound; CSRF | `phone_number` | Driver registration OTP equivalent. |
| `/drivers/register/verify-otp/` | POST | Session-bound; CSRF | `phone_number`, `otp` | Driver registration OTP equivalent. |

`/dispatcher/locations/` location entries contain `id`, vehicle/driver identity, `latitude`, `longitude`, `accuracy_meters`, availability, patient status, `updated_at`, `gps_stale`, `active_booking_id`, and `booking_status`. Emergency entries contain case id, patient/name/contact, emergency type, address, number of patients, confirmed patient coordinates, confirmation flag, requested time/status, assignment/driver/ambulance coordinates, GPS accuracy/freshness, and optional nearest eligible ambulance. Stats contain ambulance totals/availability/busy, active emergencies, and completed today.

### Server-rendered form routes and WebSocket

| Endpoint | Method | Authentication | Behavior |
|---|---|---|---|
| `/patients/new/` | GET/POST | Approved call taker or dispatcher | Call takers use dashboard intake; dispatcher sees general emergency form. Call taker must submit paired coordinates and confirmation. Duplicate submission token redirects to existing case. |
| `/dispatcher/bookings/` | GET | Approved dispatcher | Shows pending bookings and an eligible ambulance choice/suggestion. |
| `/dispatcher/bookings/<uuid>/assign/` | POST | Approved dispatcher + CSRF | Reads `ambulance` form selection; successful assignment redirects to queue. |
| `/drivers/bookings/<uuid>/` | GET/POST | Approved assigned driver | POST includes next `status` from the form's allowed transition list. |
| `/drivers/navigation/<uuid>/` | GET/POST | Approved driver with active booking assignment | Shows the confirmed destination, live GPS/route controls, GPS status panel, and status history. POST advances only to the next allowed status; arrival requires fresh, sufficiently accurate GPS within the configured radius. |
| `/drivers/availability/` | POST | Approved driver + CSRF | Form-encoded `availability_status`; changes blocked during active assignment or while patient onboard if setting available. |
| `/ws/locations/` | WebSocket | Active authenticated dispatcher role | Receives fleet location and journey status events; other users are closed with code 4403. Events contain ambulance identity, coordinates/accuracy/freshness, active booking ID/status, availability, and patient status. |

Other useful pages: `/`, `/accounts/call-taker/login/`, `/accounts/dispatcher/login/`, `/drivers/login/`, `/dispatcher/`, `/dispatcher/ambulances/`, `/bookings/<uuid>/`, and `/accounts/admin/approvals/`.

## 14. HOW TO RUN THE PROJECT

The commands below are PowerShell examples from the project root. Always use the interpreter inside the project's `.venv`.

### Local virtual environment

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
if (-not (Test-Path .\.env)) { Copy-Item .\.env.example .\.env }
```

The local README specifies Python 3.10+; Python 3.15.0 was active during inspection. Docker uses Python 3.12. Python/Django compatibility outside observed tests is **NEEDS VERIFICATION**.

### Configure MySQL

MySQL 8.0.16+ is described as supported in `README.md`. Create a database and least-privilege app account using your own unique password; do not paste credentials into source control:

```sql
CREATE DATABASE ambulance_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'ambulance_app'@'localhost' IDENTIFIED BY '<use-a-unique-secret>';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES
  ON ambulance_db.* TO 'ambulance_app'@'localhost';
```

In private `.env`, configure:

```dotenv
DB_ENGINE=mysql
DB_NAME=ambulance_db
DB_USER=ambulance_app
DB_PASSWORD=<your-local-secret>
DB_HOST=127.0.0.1
DB_PORT=3307
DJANGO_SECRET_KEY=<long-random-secret>
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
NOMINATIM_USER_AGENT=AmbulenceBooking/1.0 (maintainer contact or application URL)
```

No actual local values are recorded in this handover. Use a distinct test account if running Django tests against MySQL; its privileges may need to create/drop a test database. No SQLite fixture is available to transfer in this checkout.

### Migrate, create admin, start server

```powershell
python manage.py check
python manage.py showmigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Apply migrations to the selected MySQL database after checking the target environment. Migrations create the schema but do not import historical SQLite records. Do not run these commands against production without the project's normal release/backup review.

Open `http://127.0.0.1:8000/`. Admin is `/admin/`. Staff self-register through the corresponding role portal; accounts require administrator approval before login.

### Dashboard access

- Call taker login: `/accounts/call-taker/login/`; registration: `/accounts/call-taker/register/`; dashboard/intake: `/patients/new/`.
- Dispatcher login: `/accounts/dispatcher/login/`; registration: `/accounts/dispatcher/register/`; dashboard: `/dispatcher/`; pending queue: `/dispatcher/bookings/`; fleet: `/dispatcher/ambulances/`.
- Driver login: `/drivers/login/`; registration: `/drivers/register/`; dashboard: `/drivers/`.
- Staff approvals: `/accounts/admin/approvals/` (requires staff plus relevant account permissions).

Local OTP delivery is console-based only when `DEBUG=True`. A production OTP backend must be configured separately.

### Docker

`docker-compose.yml` runs Django and MySQL 8.4, binds the project into the web container, and persists MySQL data in the `mysql_data` volume. The web service connects to MySQL by the Compose hostname `db`.

## 15. ENVIRONMENT CONFIGURATION

| Setting | Purpose / default | Secret? |
|---|---|---|
| `DJANGO_SECRET_KEY` | Django signing/session secret; source has an insecure development fallback. Set a unique secret outside source. | **Yes** |
| `DJANGO_DEBUG` | Debug mode; defaults false in settings. Development OTP defaults to console backend only when true. | No |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated host list; default `127.0.0.1,localhost`. | No |
| `DB_ENGINE` | Must be `mysql` (default); other backends are rejected. | No |
| `DB_NAME` | Database name; MySQL default `ambulance_db`. | May identify infrastructure |
| `DB_USER` | MySQL username. | Sensitive operational info |
| `DB_PASSWORD` | MySQL password. | **Yes** |
| `DB_HOST` | MySQL host; local default `127.0.0.1`, Compose uses `db`. | May identify infrastructure |
| `DB_PORT` | MySQL port; local Docker mapping uses `3307`, Compose uses `3306`. | No |
| `NOMINATIM_USER_AGENT` | Identifies this app to Nominatim. Default is a generic app identifier; production should include a maintainer contact/URL. | No |
| `REGISTRATION_OTP_DELIVERY_BACKEND` | Python dotted path to OTP delivery callable. Defaults to console backend only in DEBUG; blank otherwise. | No (provider may require separate secrets) |
| `REDIS_URL` | Optional Channels Redis URL; unset uses in-memory channel layer. | Can contain credentials; **treat as secret** |
| `DRIVER_GPS_MIN_INTERVAL_SECONDS` | Minimum seconds between accepted GPS writes; default 5. | No |
| `DRIVER_GPS_MIN_MOVEMENT_METERS` | Minimum movement before storing a new sample; default 15 m. | No |
| `DRIVER_GPS_HEARTBEAT_SECONDS` | Maximum stationary interval before storing a heartbeat; default 60 s. | No |
| `DRIVER_ARRIVAL_RADIUS_METERS` | Maximum GPS-error-adjusted distance from confirmed destination for driver arrival; default 150 m. | No |
| `DRIVER_ARRIVAL_MAX_ACCURACY_METERS` | Maximum measured GPS accuracy accepted for arrival; default 50 m. | No |

`.env` is private and must not be copied into handovers, logs, screenshots, or commits. The actual contents were intentionally not inspected/documented. `.env.example` is an example, not a statement of the live database selection.

## 16. TESTING

### Existing automated tests

Test modules are located at:

- `accounts/tests.py`, `accounts/test_approval_workflow.py`, `accounts/test_portal_auth.py`
- `patients/tests.py`
- `bookings/tests.py`
- `ambulances/tests.py`
- `dispatcher/tests.py`, `dispatcher/test_consumers.py`
- `drivers/tests.py`

They cover role and portal authorization, OTP session/expiry/attempt/cooldown behavior, registration validation/approval, booking creation and duplicate token handling, geocoding success/cache/no-result/timeout (with a mocked HTTP response), location confirmation requirements, dispatcher JSON and WebSocket access, assignment eligibility, Haversine nearest ambulance selection, driver status transitions, GPS updates, and page rendering.

### Result observed

The latest full test run for this GPS implementation reported **90 tests passed** with no failures. Django system checks passed and `makemigrations --check --dry-run` reported no model/migration drift. Focused driver/dispatcher tests cover GPS input freshness, throttling, assignment ownership/cancellation, arrival accuracy/radius/freshness, WebSocket authorization, and a service-to-WebSocket update. Updated JavaScript assets were syntax-checked in a browser. The sample address test uses a mock Nominatim response; it does not prove a live result exists for that exact address. Browser/device GPS and external OSRM were not exercised end-to-end.

Run:

```powershell
python manage.py test
python manage.py check
python manage.py makemigrations --check --dry-run
```

### Manual workflow checklist

1. On a non-production DB with migrations applied, approve or create test call-taker, dispatcher, and driver accounts; register an ambulance to the driver.
2. Start a call-taker session and enter `PM Palem, Last Bus Stop, Visakhapatnam, Andhra Pradesh, India`.
3. Test Find location and inspect the returned label/pin. Adjust the pin and verify confirmation resets after any adjustment.
4. Test no match/network error and manually click a location. Confirm that saving without paired coordinates or confirmation is rejected.
5. Submit a confirmed request; verify one booking, one patient, UUID case ID, paired coordinate columns, `location_confirmed=true`, and an initial status-history row.
6. Resubmit the same token; verify no duplicate patient or booking.
7. As dispatcher, verify the confirmed patient marker and popup, select the queue case and check map focus; assign an eligible ambulance with a recent GPS fix.
8. As driver, accept the assignment and open `/drivers/navigation/<booking_uuid>/`. Confirm that Start Navigation is explicit, browser permission is requested, and GPS status/accuracy/freshness are visible.
9. Simulate or allow movement; confirm the driver marker moves and the dispatcher marker/status update through WebSocket, with five-second polling as fallback. Verify pause/resume, offline/reconnect, stale GPS, and denied permission.
10. Test OSRM success and failure; verify route recalculation is throttled and fallback is clearly labeled without ETA. Advance through statuses and verify out-of-radius, stale, and inaccurate arrival attempts are rejected.
11. Verify status/assignment history, pickup patient state, completion release, and denial of another driver's booking/location.
12. Back up the confirmed MySQL target, review and apply the pending accuracy migration, inspect table state, and run the complete suite against the intended test environment.

## 17. IMPORTANT DEVELOPMENT RULES

- Read this handover and the relevant source before making a change; source and current migrations outrank assumptions.
- Keep one Django backend and the configured single database. Do not create duplicate patient, emergency, or dispatcher models/apps.
- Keep emergency address and coordinates on existing `Booking`; patient demographics remain on `Patient`.
- Reuse existing Django forms, `JsonResponse` views, URL namespaces, service functions, role decorators, templates, Channels group, and Leaflet map.
- Do not replace the dispatcher Leaflet map or ambulance GPS pipeline to add patient-location behavior.
- Do not use a geocoded point as confirmed truth. Require call-taker confirmation/manual adjustment; preserve assignment-service checks.
- Respect Nominatim's public service usage policy. Avoid autocomplete/per-keystroke lookups, use cache and rate limits, valid User-Agent, and explicit timeout/error handling.
- Add data-preserving migrations for schema changes. Back up databases before migrations; never delete existing data or rewrite relationships as a shortcut.
- Keep transactions and row locks for assignment/status changes; preserve active-assignment uniqueness constraints and assignment history.
- Maintain role/approval authorization, CSRF, safe error responses, phone/credential privacy, and secure environment configuration.
- Keep driver GPS updates and Channels semantics intact. Distinguish ambulance GPS, patient pickup coordinates, and hospital coordinates.
- Do not claim traffic-based dispatch, hospital discovery, turn-by-turn navigation, or live Nominatim accuracy unless actually implemented and verified.
- Update focused tests and this document when system behavior, model fields, URLs, or status workflows change.

## 18. NEXT DEVELOPMENT TASK

The next task is a **database-safe rollout and two-browser GPS workflow verification**:

1. Back up the intended deployment MySQL database and inspect its migration state. The configured local `ambulance_db` has `ambulances.0004` applied.
2. Review and apply any migrations that remain pending on the intended target.
3. Use separate dispatcher and driver sessions to test assignment, explicit GPS start/pause/resume, simulated movement, WebSocket and polling updates, network loss/reconnect, stale/denied GPS, route-service failure, arrival validation, and assignment cancellation.
4. Record the test environment and results without exposing credentials or patient data.

Do not treat public OSM/OSRM routing or browser geolocation as production-grade emergency navigation. Production readiness still requires policy, hosting, security, monitoring, retention, backup/restore, and operational safety work.

## INSTRUCTIONS FOR THE NEXT GITHUB COPILOT

- Read this entire handover document before modifying anything.
- Inspect the current source code before making changes.
- Understand the existing architecture first.
- Never recreate already implemented features.
- Never replace existing working functionality unnecessarily.
- Maintain the three interconnected interfaces.
- Maintain one Django backend and one MySQL database.
- Reuse existing models, APIs and components.
- Do not delete existing data.
- Do not modify unrelated UI components.
- Explain the implementation plan before major changes.
- Update this handover document after significant development changes.
- Always verify changes and report errors honestly.
