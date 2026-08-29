"""Django settings for harbourlight."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
DEBUG = False
ALLOWED_HOSTS = []
SECURE_SSL_REDIRECT = True

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "members",
    "shop",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "harbourlight.sqlite3",
    }
}

ROOT_URLCONF = "harbourlight.urls"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
