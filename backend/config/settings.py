"""Django settings for ScrapeSearch.

Every secret and every per-environment value comes from environment variables (.env locally,
the systemd unit's EnvironmentFile in production). Nothing sensitive is hardcoded here.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent  # .../backend
REPO_ROOT = BASE_DIR.parent

# Real environment variables win over .env, so production can inject its own.
load_dotenv(REPO_ROOT / ".env")

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]  # KeyError at startup beats running with a missing key
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost").split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "catalog",  # MySQL models (Book, Quote), book detail + LIKE search endpoints
    "search",   # Elasticsearch: mapping, sync_es command, search + suggest endpoints
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

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.environ["MYSQL_DATABASE"],
        "USER": os.environ["MYSQL_USER"],
        "PASSWORD": os.environ["MYSQL_PASSWORD"],
        "HOST": os.environ.get("MYSQL_HOST", "127.0.0.1"),
        "PORT": os.environ.get("MYSQL_PORT", "3306"),
        "OPTIONS": {"charset": "utf8mb4"},
        "CONN_MAX_AGE": 60,  # reuse a connection for up to 60s instead of reconnecting on every request
    }
}

# Elasticsearch: the index name the app reads and writes is an ALIAS (see search/indexing.py).
ES_URL = os.environ.get("ES_URL", "http://localhost:9200")
ES_BOOKS_ALIAS = "books"
# Local docker-compose runs ES without security. On the server ES 8 keeps its default security on:
# HTTPS with its own CA certificate + a password. Leave these empty locally.
ES_USERNAME = os.environ.get("ES_USERNAME", "elastic")
ES_PASSWORD = os.environ.get("ES_PASSWORD", "")
ES_CA_CERTS = os.environ.get("ES_CA_CERTS", "")  # path to http_ca.crt

# --- Behind nginx in production ---
# nginx terminates HTTPS and talks plain HTTP to gunicorn. This header (set in deploy/nginx.conf) tells
# Django the original request was HTTPS, so it builds https:// URLs and trusts secure cookies.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# Set DJANGO_HTTPS=1 once certbot is set up: cookies are then only ever sent over HTTPS.
HTTPS = os.environ.get("DJANGO_HTTPS", "0") == "1"
SESSION_COOKIE_SECURE = HTTPS
CSRF_COOKIE_SECURE = HTTPS
# HSTS: browsers remember "HTTPS only" for this many seconds, and you can't take it back early.
# Start small (3600) once HTTPS works, raise it (31536000 = 1 year) when you're sure. 0 = off.
SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "0"))
# nginx redirects http -> https (certbot sets that up), so Django doesn't also need SECURE_SSL_REDIRECT.
SILENCED_SYSTEM_CHECKS = ["security.W008"]
# The admin login form (POST) checks the Origin header against this list, e.g. "https://example.com".
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True  # store UTC in the DB. MySQL is also pinned to UTC in docker-compose.yml.

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"  # `collectstatic` copies admin/DRF assets here, nginx serves them

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    # The clickable "browsable API" is handy while developing. Production returns JSON only.
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"]
    + (["rest_framework.renderers.BrowsableAPIRenderer"] if DEBUG else []),
    "UNAUTHENTICATED_USER": None,  # the API is public and read-only, so skip the auth machinery
    # Return prices as JSON numbers (10.97), same as the ES endpoints, instead of DRF's default "10.97".
    "COERCE_DECIMAL_TO_STRING": False,
}

# Logs go to stdout/stderr. Under systemd, journald captures them (`journalctl -u gunicorn`).
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "%(asctime)s [%(name)s] %(levelname)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "catalog": {"level": "INFO"},
        "search": {"level": "INFO"},
        "django.request": {"level": "WARNING"},  # 4xx/5xx with tracebacks
        "elastic_transport": {"level": "WARNING"},  # the ES client logs every request at INFO, too noisy
    },
}
