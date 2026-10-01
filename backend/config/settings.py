"""VHS settings, configured through environment variables (see .env.example)."""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BASE_DIR.parent


def load_dotenv(path: Path) -> None:
    """Load a minimal .env file (KEY=VALUE) without overriding the existing environment."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


load_dotenv(Path(os.environ.get("VHS_ENV_FILE", PROJECT_DIR / ".env")))


def env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    return int(value) if value else default


def env_path(name: str, default: Path) -> Path:
    """Relative paths are resolved against the project root, not the working directory."""
    value = os.environ.get(name)
    path = Path(value).expanduser() if value else default
    return path if path.is_absolute() else (PROJECT_DIR / path).resolve()


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)

SECRET_KEY = env("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY is required when DJANGO_DEBUG=false.")
    SECRET_KEY = "insecure-dev-only-key"

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_q",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # Picks the language from Accept-Language (sent by the SPA) among LANGUAGES.
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", "vhs"),
        "USER": env("POSTGRES_USER", "vhs"),
        "PASSWORD": env("POSTGRES_PASSWORD", "vhs"),
        "HOST": env("POSTGRES_HOST", "localhost"),
        "PORT": env("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": env_int("POSTGRES_CONN_MAX_AGE", 60),
        "CONN_HEALTH_CHECKS": True,
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Source texts are English. To add a language: an entry in LANGUAGES and its catalog in
# backend/locale (makemessages / compilemessages, docs/development.md).
LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English")]
LOCALE_PATHS = [BASE_DIR / "locale"]
# Times are stored in UTC (USE_TZ); this is only the zone used to display them.
TIME_ZONE = env("VHS_TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = env_path("DJANGO_STATIC_ROOT", PROJECT_DIR / "staticfiles")

# Video library: a local folder, a Docker volume or a host folder (docs/storage-decisions.md).
VHS_MEDIA_ROOT = env_path("VHS_MEDIA_ROOT", PROJECT_DIR / "video-library")
VHS_NAMING_TEMPLATE = env("VHS_NAMING_TEMPLATE", "standard")
# Nginx internal location that maps to VHS_MEDIA_ROOT (X-Accel-Redirect).
VHS_MEDIA_ACCEL_PREFIX = env("VHS_MEDIA_ACCEL_PREFIX", "/media-internal/")

# Downloads
VHS_MIN_FREE_BYTES = env_int("VHS_MIN_FREE_BYTES", 1024**3)
VHS_DOWNLOAD_STALL_SECONDS = env_int("VHS_DOWNLOAD_STALL_SECONDS", 300)
VHS_HEARTBEAT_INTERVAL_SECONDS = env_int("VHS_HEARTBEAT_INTERVAL_SECONDS", 30)
VHS_HEARTBEAT_TIMEOUT_SECONDS = env_int("VHS_HEARTBEAT_TIMEOUT_SECONDS", 300)
VHS_PROGRESS_THROTTLE_SECONDS = float(env("VHS_PROGRESS_THROTTLE_SECONDS", "2"))

# Browser copies (§18): automatic remux, transcode only on request.
VHS_TRANSCODE_PRESET = env("VHS_TRANSCODE_PRESET", "veryfast")
VHS_TRANSCODE_CRF = env_int("VHS_TRANSCODE_CRF", 21)
VHS_TRANSCODE_AUDIO_BITRATE = env("VHS_TRANSCODE_AUDIO_BITRATE", "160k")
VHS_FFMPEG_THREADS = env_int("VHS_FFMPEG_THREADS", 0)
VHS_MEDIA_TOOL_TIMEOUT = env_int("VHS_MEDIA_TOOL_TIMEOUT", 6 * 60 * 60)

# Session and CSRF: single-user admin access from the SPA.
# Cookie security is a per-installation choice, independent of DEBUG: Secure by default
# (HTTPS). A plain-HTTP LAN install must opt out explicitly with DJANGO_SECURE_COOKIES=false,
# and then the login and the session cookie travel unencrypted.
VHS_SECURE_COOKIES = env_bool("DJANGO_SECURE_COOKIES", True)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = VHS_SECURE_COOKIES
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = VHS_SECURE_COOKIES
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = env_bool("DJANGO_USE_X_FORWARDED_HOST", False)
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# API request size limit (§43); cookie uploads will get a dedicated limit.
DATA_UPLOAD_MAX_MEMORY_SIZE = env_int("VHS_MAX_REQUEST_BYTES", 2 * 1024 * 1024)

# django-q2 with the PostgreSQL (ORM) broker, no Redis.
# retry must exceed timeout so a task is never redelivered while still running.
Q_CLUSTER = {
    "name": "vhs",
    "orm": "default",
    "workers": env_int("VHS_WORKERS", 2),
    "timeout": env_int("VHS_TASK_TIMEOUT", 6 * 60 * 60),
    "retry": env_int("VHS_TASK_RETRY", 6 * 60 * 60 + 15 * 60),
    "max_attempts": 1,
    "ack_failures": True,
    "catch_up": False,
    "save_limit": 500,
    "label": "Task",
}

LOG_LEVEL = env("VHS_LOG_LEVEL", "INFO").upper()

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "default"},
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "vhs": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django_q": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}
