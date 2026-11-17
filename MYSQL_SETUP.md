# MySQL 8.0 setup

The Django project uses MySQL as its only database backend. Django migrations
are the source of truth for all Django-managed tables; the SQL files in
`database/` do not duplicate model definitions.

## 1. Install MySQL on Windows

Install MySQL Server 8.0 and start the `MySQL80` service. In PowerShell, check
that it is running and listening on the requested port:

```powershell
Get-Service MySQL80
Get-NetTCPConnection -State Listen -LocalPort 3306
```

The Python package `mysqlclient` is declared in `requirements.txt`. From the
project root, install project dependencies if needed:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 2. Configure credentials

The existing `.env` is private and is not overwritten by these instructions.
If you do not already have one, create it from the example:

```powershell
if (-not (Test-Path .\.env)) { Copy-Item .\.env.example .\.env }
```

For a locally installed MySQL server, configure the following values in `.env`.
Enter your real password only in that ignored local file; never commit it:

```dotenv
DB_ENGINE=mysql
DB_NAME=ambulance_db
DB_USER=root
DB_PASSWORD=your-local-MySQL-root-password
DB_HOST=localhost
DB_PORT=3306
```

Do not use a production root account for the application. In production, use a
dedicated database account scoped to `ambulance_db`, provide credentials via
the deployment's secret manager/environment, and set `DJANGO_DEBUG=False`.
`python-dotenv` loads `.env` for local development; environment variables
provided by a deployment take precedence.

## 3. Create the database and apply migrations

Run the setup script from the project root:

```powershell
.\.venv\Scripts\python.exe setup_mysql.py
```

It checks MySQL connectivity, creates `ambulance_db` if absent, runs
`manage.py migrate`, checks the database, and verifies all managed Django
model tables. It does not drop the database or flush tables. Pending
migrations may transform existing records as described in this project's
migration history; back up and review those migrations before running setup
against a database containing important data.

For optional fictional sample records linked across the project models, run:

```powershell
.\.venv\Scripts\python.exe setup_mysql.py --seed-demo-data
```

This is opt-in, does not overwrite existing records, and should only be used
for development/demo databases. Seeded accounts have unusable passwords; set
one explicitly with `python manage.py changepassword demo_call_taker` if you
want to sign in as that demo account.

You can run these diagnostic commands separately:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py check --database default
.\.venv\Scripts\python.exe manage.py showmigrations --database default
```

For manual database creation, a MySQL administrator can run:

```powershell
Get-Content .\database\mysql_setup.sql | mysql -u root -p -h localhost -P 3306
```

Then apply the Django schema:

```powershell
.\.venv\Scripts\python.exe manage.py migrate --database default
```

`database/mysql_schema.sql` documents why a separate table schema is not
maintained: Django migrations define and evolve model tables.

## 4. Run checks and tests

Run the existing test suite against the configured MySQL server:

```powershell
.\.venv\Scripts\python.exe manage.py test
```

Django's MySQL test runner creates a separate test database. The configured
MySQL account needs permission to create and drop that test database. Do not
manually create or reuse an important database with Django's test database
name.

To confirm table names without reading application rows:

```powershell
.\.venv\Scripts\python.exe manage.py dbshell
```

Then run:

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'ambulance_db'
ORDER BY table_name;
```

Create a Django administrator with `python manage.py createsuperuser`, then
start the application with `python manage.py runserver`. Existing account,
registration, booking, ambulance, and driver workflows remain application
features; this database setup does not create sample records or import data.

## Docker alternative

The existing Docker Compose configuration uses MySQL 8.0 and stores its data
in the named `mysql_data` volume. It uses the separate `MYSQL_APP_USER` and
`MYSQL_APP_PASSWORD` settings plus `MYSQL_ROOT_PASSWORD`; these are distinct
from the local-server `DB_USER` and `DB_PASSWORD` values in `.env.example`.
Set unique values before starting the container:

```powershell
docker compose up -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py check --database default
```

The database service is exposed on `127.0.0.1:3307` for external tools, while
the web container connects to `db:3306`. Do not use `docker compose down -v`
unless you intentionally want to delete the MySQL volume.

## Troubleshooting and data safety

- **Connection refused:** Confirm `MySQL80` is running and `.env` has the
  correct host and port. The local-server defaults are `localhost:3306`.
- **Access denied:** Check the username and password in `.env`. The setup
  script does not display or store the password.
- **Database already exists:** `CREATE DATABASE IF NOT EXISTS` leaves it in
  place. Inspect and back up existing data before applying pending migrations.
- **Docker port conflict:** Docker maps host port 3307 to container port 3306;
  the MySQL service inside the container still listens on 3306.
- **Missing historical data:** The former SQLite source database and its
  external backup were removed before any import. No SQLite records were
  transferred; restore a separate copy before planning data recovery.
