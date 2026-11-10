# Docker setup (Windows 11)

## Project configuration and data safety

This project currently selects SQLite through `DB_ENGINE=sqlite3` in `.env`, and its existing database is `db.sqlite3`. The Compose setup therefore runs Django only and bind-mounts the project directory into the container. The database, uploaded media, and source files remain on the Windows host and survive container rebuilds and restarts. No MySQL container or MySQL-to-SQLite conversion is performed.

The project also supports MySQL through its existing `DB_ENGINE` setting, but changing this setup to MySQL requires an intentional database migration and data transfer. Do not switch `DB_ENGINE` or point it at another database until you have a verified backup and have planned that transfer.

Migrations are not run automatically during startup. Apply them manually only after the web container is running and SQLite is available.

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

Keep `.env` private and out of source control. The supplied example is configured for the current SQLite database; set a unique `DJANGO_SECRET_KEY` for your local environment. For local development, `DJANGO_DEBUG=True` is expected.

## Build and start

```powershell
docker compose build
docker compose up -d
docker compose ps
docker compose logs -f
```

Open <http://127.0.0.1:8000/>. Django Admin is at <http://127.0.0.1:8000/admin/>.

The `web` service uses the Python 3.12 image, installs `requirements.txt`, and runs Django's development server on port 8000. `docker-compose.yml` mounts the current project at `/app`, so the existing `db.sqlite3` is the database used inside the container. `restart: unless-stopped` restarts the app container after a Docker daemon restart unless it was explicitly stopped.

There is no MySQL service or named MySQL volume because the active project configuration uses SQLite. The host bind mount is the persistence mechanism for this setup. Do not run multiple app instances against this SQLite file.

## Common operations

Run these commands from the VS Code PowerShell terminal at the project root:

```powershell
# Apply existing migrations; this does not create new migration files.
docker compose exec web python manage.py migrate

# Create an administrative user.
docker compose exec web python manage.py createsuperuser

# Stop and remove the app container (the host database is not removed).
docker compose down

# Restart the app container.
docker compose restart
```

Enter the container or inspect recent logs:

```powershell
docker compose exec web sh
docker compose logs --tail 100 web
```

The database is SQLite inside the application container, not a MySQL server. To inspect the Django database configuration, run:

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

## Back up and restore SQLite data

Stop the app before copying the SQLite database so that the backup is consistent. These commands store backups under your Windows profile rather than in the repository:

```powershell
docker compose stop web
$backupDir = Join-Path $env:USERPROFILE "AmbulenceBooking-backups"
New-Item -ItemType Directory -Force $backupDir | Out-Null
$backupFile = Join-Path $backupDir ("db-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".sqlite3")
Copy-Item .\db.sqlite3 $backupFile
docker compose start web
```

To restore, stop the app, select the intended backup, and first preserve the current database. The example uses a specific backup filename; replace it with the file you intend to restore:

```powershell
docker compose stop web
$backupFile = Join-Path $env:USERPROFILE "AmbulenceBooking-backups\db-YYYYMMDD-HHMMSS.sqlite3"
Copy-Item .\db.sqlite3 (Join-Path $env:USERPROFILE "AmbulenceBooking-backups\db-before-restore.sqlite3")
Copy-Item $backupFile .\db.sqlite3 -Force
docker compose start web
```

Never delete or replace `db.sqlite3` unless you have verified the backup and explicitly intend to restore it. `docker compose down` does not delete this host file.

## Troubleshooting

- **`docker` is not recognized:** Start/install Docker Desktop, wait for the engine, then open a new VS Code terminal. Verify with `docker --version`.
- **Docker daemon is unavailable:** Start Docker Desktop and check its status. If using WSL 2, verify WSL integration is enabled for the selected distribution.
- **`.env` is missing:** Run the environment preparation command above. Do not copy the example over an existing `.env`.
- **Port 8000 is in use:** Stop the other process or change the host side of the `ports` mapping in `docker-compose.yml`, then open the corresponding port in the browser.
- **Database errors:** Confirm `.env` has `DB_ENGINE=sqlite3` and `DB_NAME=db.sqlite3`, and that `db.sqlite3` exists at the project root. Do not point the app at a different database or remove the file as a troubleshooting shortcut.
- **Static files look stale:** Ensure `DJANGO_DEBUG=True` for development and restart the app after changing settings.
- **See detailed application output:** Run `docker compose logs -f web`.
