import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent

load_dotenv(PROJECT_ROOT / ".env")

DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"

# Secret key must be provided via .env. Only DEBUG gets a throwaway dev fallback.
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-insecure-only-do-not-use-in-production"
    else:
        raise RuntimeError("DJANGO_SECRET_KEY must be set when DEBUG is off.")

ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

# Hardening applied automatically once DEBUG is off (production).
if not DEBUG:
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    CSRF_COOKIE_HTTPONLY = True
    X_FRAME_OPTIONS = "DENY"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "apps.monitoring",
    "apps.github",
    "apps.render",
    "apps.google_cloud",
    "apps.sendgrid",
    "apps.notifications",
    "apps.assistant",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "dashboard.urls"
FRONTEND_DIR = PROJECT_ROOT / "frontend"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [FRONTEND_DIR / "templates"],
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

WSGI_APPLICATION = "dashboard.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
# ponytail: PostgreSQL later via DATABASE_URL, dj-database-url when needed.

AUTH_PASSWORD_VALIDATORS = []
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [FRONTEND_DIR / "static"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CORS_ALLOWED_ORIGINS = ["http://127.0.0.1:8000", "http://localhost:8000"]

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
}

# Integration credentials (mock data served when absent).
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_USER = os.getenv("GITHUB_USER", "")
RENDER_API_KEY = os.getenv("RENDER_API_KEY", "")
GCP_API_KEY = os.getenv("GCP_API_KEY", "")
GCP_PROJECT = os.getenv("GCP_PROJECT", "")
GCP_SERVICE_ACCOUNT_FILE = os.getenv("GCP_SERVICE_ACCOUNT_FILE", "")
GCP_BILLING_PROJECT_ID = os.getenv("GCP_BILLING_PROJECT_ID", "")
GCP_BILLING_DATASET = os.getenv("GCP_BILLING_DATASET", "")
GCP_BILLING_TABLE = os.getenv("GCP_BILLING_TABLE", "")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")  # fallback / default channel

# Per-channel webhooks for the Orbit server. Any blank one falls back to
# DISCORD_WEBHOOK_URL. Create one webhook per channel in Discord:
# Server Settings -> Integrations -> Webhooks.
DISCORD_CHANNELS = {
    "alerts": os.getenv("DISCORD_WEBHOOK_ALERTS", ""),
    "security": os.getenv("DISCORD_WEBHOOK_SECURITY", ""),
    "billing": os.getenv("DISCORD_WEBHOOK_BILLING", ""),
    "deployments": os.getenv("DISCORD_WEBHOOK_DEPLOYMENTS", ""),
    "logs": os.getenv("DISCORD_WEBHOOK_LOGS", ""),
    "general": os.getenv("DISCORD_WEBHOOK_GENERAL", ""),
}
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
TOKEN_ENCRYPTION_KEY = os.getenv("TOKEN_ENCRYPTION_KEY", "")

RENDER_COST_THRESHOLD = float(os.getenv("RENDER_COST_THRESHOLD", "1.62"))
SCHEDULER_INTERVAL = int(os.getenv("SCHEDULER_INTERVAL", "300"))
