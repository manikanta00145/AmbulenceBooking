# MySQL database files

This project uses MySQL 8.0 and Django migrations. The migration files in
`accounts/migrations/`, `patients/migrations/`, `bookings/migrations/`,
`ambulances/migrations/`, and `drivers/migrations/` define the application's
tables and schema changes. `mysql_schema.sql` intentionally contains no
duplicate `CREATE TABLE` statements.

## Automatic setup

1. Install the Python packages with `python -m pip install -r requirements.txt`.
2. Copy `.env.example` to `.env` only if `.env` does not already exist. Set the
   local MySQL `DB_USER`, `DB_PASSWORD`, `DB_HOST`, and `DB_PORT` in `.env`.
3. Run `python setup_mysql.py` from the project root.

The script checks the MySQL server connection, creates `ambulance_db` if it is
missing, applies Django migrations, runs Django's database checks, and verifies
that every managed Django model table exists. It never drops or flushes a
database. Pending migrations can make the data transformations recorded in the
project migration history; back up and review those migrations before running
the script against a database containing important records.

To add fictional linked data for the account, patient, ambulance, booking,
driver, GPS, and geocoding workflows, opt in explicitly:

```powershell
python setup_mysql.py --seed-demo-data
```

The command creates users with unusable passwords and never changes existing
records. To sign in as a demo user in a development database, set its password
with `python manage.py changepassword demo_call_taker` (or the matching
dispatcher/driver username). Demo seeding is optional and should not be run in
production.

`mysql_setup.sql` is an optional manual alternative for creating the empty
database. Run it with a MySQL account that can create databases, then run
`python manage.py migrate`. Do not execute hand-written model table DDL; the
Django migrations remain authoritative.

See [MYSQL_SETUP.md](../MYSQL_SETUP.md) for MySQL installation, environment
configuration, and troubleshooting.
