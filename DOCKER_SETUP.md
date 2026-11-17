# Docker setup (Windows 11)

## Project configuration and data safety

Docker Compose runs Django and MySQL 8.0. MySQL persists in the named `mysql_data` volume; the project schema is created by Django migrations, not by a checked-in SQL file. The database is published on `127.0.0.1:3307` for local tools; the web container connects privately to `db:3306`.

This setup initializes a MySQL database; it does not import historical data.
The former SQLite source and its external backup were deleted before import,
so no SQLite records are present in MySQL or available in this checkout.

## Prerequisites

1. Install Docker Desktop for Windows 11 from <https://www.docker.com/products/docker-desktop/>.
2. In the Docker Desktop installer, enable the WSL 2 backend and the WSL integration for the Linux distribution you use, if applicable.
3. If WSL is not installed, open PowerShell as Administrator and run:

   ```powershell
   wsl --install
   ```

   Restart Windows if requested, then open Docker Desktop and wait for its engine to report that it is running.
4. In VS Code, open this project folder and use **Terminal > New Terminal** with PowerShell.
5. Confirm Docker is available:

   ```powershell
   docker --version
   docker compose version
   ```

## Prepare environment

From the project root in the VS Code PowerShell terminal, create a local environment file only if you do not already have one:

```powershell
if (-not (Test-Path .\.env)) { Copy-Item .\.env.example .\.env }
```

Keep `.env` private and out of source control. Set unique values for `DJANGO_SECRET_KEY`, `MYSQL_APP_PASSWORD`, and `MYSQL_ROOT_PASSWORD`; do not use the example passwords as real credentials. `DJANGO_DEBUG=True` is for local development. Docker Compose uses its dedicated `MYSQL_APP_USER`/`MYSQL_APP_PASSWORD` account and does not use the local-server `DB_USER`/`DB_PASSWORD` values.

## Build and start

```powershell
docker compose build
docker compose up -d
docker compose ps
docker compose logs --tail 100 db web
```

Wait for `db` to report healthy, then apply migrations:

```powershell
docker compose exec web python manage.py migrate
```

Open <http://127.0.0.1:8000/>. Django Admin is at <http://127.0.0.1:8000/admin/>. The `web` service bind-mounts the project at `/app`; the MySQL data itself is stored in the Docker-managed `mysql_data` volume and survives container rebuilds/restarts.

## Common operations

Run these commands from the VS Code PowerShell terminal at the project root:

```powershell
# Apply migrations to the MySQL database.
docker compose exec web python manage.py migrate

# Create an administrative user.
docker compose exec web python manage.py createsuperuser

# Stop and remove containers (the MySQL volume remains).
docker compose down

# Restart the app container.
docker compose restart
```

Enter the container or inspect recent logs:

```powershell
docker compose exec web sh
docker compose logs --tail 100 web
```

To inspect the Django database configuration, run:

```powershell
docker compose exec web python manage.py check --database default
docker compose exec web python manage.py showmigrations
```

## Static files, media, and production

The existing settings keep `STATIC_URL`, `STATIC_ROOT`, `MEDIA_URL`, and `MEDIA_ROOT`. The development server serves development static files while `DJANGO_DEBUG=True`; the bind mount keeps generated static/media files on the host. This project does not configure a production static/media server.

For an ASGI server rather than Django's development server, the image can be run with an overridden command:

```powershell
docker compose run --rm --service-ports web daphne -b 0.0.0.0 -p 8000 ambulance_system.asgi:application
```

Before any production deployment, set `DJANGO_DEBUG=False`, configure `DJANGO_ALLOWED_HOSTS` and a production-only secret in `.env`, and arrange HTTPS plus production static/media hosting. Do not expose the development server to the public internet.

## Existing data status

The former SQLite database and backup were removed before migration. No
records were imported, and no SQLite import procedure is available in this
MySQL-only configuration. Recovering those records requires restoring another
copy of the source database before planning a migration. Do not treat
`migrate` as a data import; it creates the schema only.

Do not use `docker compose down -v` unless you explicitly intend to destroy the MySQL database volume.

## Troubleshooting

- **`docker` is not recognized:** Start/install Docker Desktop, wait for the engine, then open a new VS Code terminal. Verify with `docker --version`.
- **Docker daemon is unavailable:** Start Docker Desktop and check its status. If using WSL 2, verify WSL integration is enabled for the selected distribution.
- **`.env` is missing:** Run the environment preparation command above. Do not copy the example over an existing `.env`.
- **Port 8000 is in use:** Stop the other process or change the host side of the `ports` mapping in `docker-compose.yml`, then open the corresponding port in the browser.
- **Database connection errors:** Check that `db` is healthy, `MYSQL_APP_PASSWORD` and `MYSQL_ROOT_PASSWORD` were set before the MySQL volume was first created, and that port 3307 is available. If credentials are changed after the volume is initialized, update the MySQL users inside that database; changing `.env` alone does not reset credentials stored in the volume.
- **Static files look stale:** Ensure `DJANGO_DEBUG=True` for development and restart the app after changing settings.
- **See detailed application output:** Run `docker compose logs -f web`.
