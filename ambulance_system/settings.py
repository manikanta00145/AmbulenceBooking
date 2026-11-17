import os
import math
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-development-key-replace-before-deployment",
)
DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() in {"1", "true", "yes"}
REGISTRATION_OTP_DELIVERY_BACKEND = os.environ.get(
    "REGISTRATION_OTP_DELIVERY_BACKEND",
    "accounts.otp_delivery.console_otp_delivery" if DEBUG else "",
)
NOMINATIM_USER_AGENT = os.environ.get(
    "NOMINATIM_USER_AGENT",
    "AmbulenceBooking/1.0 (Django emergency dispatch application)",
)
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
    if host.strip()
]


def _positive_float_setting(name, default):
    try:
        value = float(os.environ.get(name, str(default)))
    except ValueError as error:
        raise ImproperlyConfigured(f"{name} must be a positive number.") from error
    if not math.isfinite(value) or value <= 0:
        raise ImproperlyConfigured(f"{name} must be a positive number.")
    return value


DRIVER_GPS_MIN_INTERVAL_SECONDS = _positive_float_setting(
    "DRIVER_GPS_MIN_INTERVAL_SECONDS", 5
)
DRIVER_GPS_MIN_MOVEMENT_METERS = _positive_float_setting(
    "DRIVER_GPS_MIN_MOVEMENT_METERS", 15
)
DRIVER_GPS_HEARTBEAT_SECONDS = _positive_float_setting(
    "DRIVER_GPS_HEARTBEAT_SECONDS", 60
)
DRIVER_ARRIVAL_RADIUS_METERS = _positive_float_setting(
    "DRIVER_ARRIVAL_RADIUS_METERS", 150
)
DRIVER_ARRIVAL_MAX_ACCURACY_METERS = _positive_float_setting(
    "DRIVER_ARRIVAL_MAX_ACCURACY_METERS", 50
)

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",
    "accounts",
    "patients",
    "bookings",
    "ambulances",
    "dispatcher",
    "drivers",
    "hospitals",
    "notifications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = os.environ.get(
    "SESSION_COOKIE_SECURE", str(not DEBUG)
).strip().lower() in {"1", "true", "yes"}
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = os.environ.get(
    "CSRF_COOKIE_SECURE", str(not DEBUG)
).strip().lower() in {"1", "true", "yes"}

ROOT_URLCONF = "ambulance_system.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "ambulance_system.wsgi.application"
ASGI_APPLICATION = "ambulance_system.asgi.application"
if os.environ.get("REDIS_URL"):
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [os.environ["REDIS_URL"]]},
        }
    }
else:
    CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    }

db_engine = os.environ.get("DB_ENGINE", "mysql").strip().lower()
if db_engine not in {"mysql", "django.db.backends.mysql"}:
    raise ImproperlyConfigured(
        "This application requires MySQL; DB_ENGINE must be set to 'mysql'."
    )
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.environ.get("DB_NAME", "ambulance_db"),
        "USER": os.environ.get("DB_USER", "root"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "3306"),
        "OPTIONS": {"charset": "utf8mb4"},
        "CONN_MAX_AGE": 60,
    }
}

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:dashboard"
LOGOUT_REDIRECT_URL = "home"
