import argparse
import os
import re
import sys
from pathlib import Path

import MySQLdb
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ambulance_system.settings")

import django
from django.core.management.base import CommandError
from django.db.utils import DatabaseError


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Create and initialize the MySQL database."
    )
    parser.add_argument(
        "--seed-demo-data",
        action="store_true",
        help="Add fictional linked records after migrations.",
    )
    args = parser.parse_args(argv)

    db_engine = os.environ.get("DB_ENGINE", "mysql").strip().lower()
    if db_engine not in {"mysql", "django.db.backends.mysql"}:
        print("ERROR: DB_ENGINE must be set to 'mysql'.", file=sys.stderr)
        return 1

    database_name = os.environ.get("DB_NAME", "ambulance_db")
    if not re.fullmatch(r"[A-Za-z0-9_]+", database_name):
        print(
            "ERROR: DB_NAME may contain only letters, numbers, and underscores.",
            file=sys.stderr,
        )
        return 1

    user = os.environ.get("DB_USER", "root")
    password = os.environ.get("DB_PASSWORD", "")
    host = os.environ.get("DB_HOST", "localhost")
    try:
        port = int(os.environ.get("DB_PORT", "3306"))
    except ValueError:
        print("ERROR: DB_PORT must be a valid port number.", file=sys.stderr)
        return 1

    if not password:
        print("ERROR: Set DB_PASSWORD in the private .env file.", file=sys.stderr)
        return 1

    try:
        server_connection = MySQLdb.connect(
            host=host,
            port=port,
            user=user,
            passwd=password,
            connect_timeout=10,
            charset="utf8mb4",
        )
        try:
            with server_connection.cursor() as cursor:
                cursor.execute("SELECT VERSION()")
                server_version = cursor.fetchone()[0]
                if not server_version.startswith("8.0."):
                    print(
                        f"ERROR: MySQL 8.0 is required; found {server_version}.",
                        file=sys.stderr,
                    )
                    return 1
                cursor.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{database_name}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            server_connection.commit()
        finally:
            server_connection.close()
        print(f"MySQL server is reachable at {host}:{port}.")
        print(f"Database '{database_name}' is ready.")

        django.setup()

        from django.apps import apps
        from django.core.management import call_command
        from django.db import connections

        connection = connections["default"]
        connection.ensure_connection()
        print(f"Django connected to MySQL {server_version}.")

        call_command("migrate", database="default", interactive=False)
        call_command("check", database=["default"])

        expected_tables = {
            model._meta.db_table
            for model in apps.get_models(include_auto_created=True)
            if model._meta.managed and not model._meta.proxy
        }
        actual_tables = set(connection.introspection.table_names())
        missing_tables = sorted(expected_tables - actual_tables)
        if missing_tables:
            print(
                "ERROR: Missing Django model tables: " + ", ".join(missing_tables),
                file=sys.stderr,
            )
            return 1

        if args.seed_demo_data:
            call_command("seed_demo_data")

        print(
            f"Success: verified all {len(expected_tables)} Django model tables "
            f"in '{database_name}'."
        )
        return 0
    except MySQLdb.Error as error:
        print(f"ERROR: MySQL operation failed: {error}", file=sys.stderr)
        return 1
    except DatabaseError as error:
        print(f"ERROR: Django database operation failed: {error}", file=sys.stderr)
        return 1
    except CommandError as error:
        print(f"ERROR: Django setup failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
