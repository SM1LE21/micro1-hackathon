"""Configuration for pulsedeck."""

import os

DATABASE_URL = "sqlite:///./pulsedeck.db"
PAGE_SIZE = 50
SESSION_COOKIE_NAME = "pulsedeck_session"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
AWS_REGION = "eu-central-1"
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "")
MIXPANEL_TOKEN = os.environ.get("MIXPANEL_TOKEN", "")
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "")
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
