"""Application object for pulsedeck."""

import sentry_sdk

from api import account, profile
from config import SENTRY_DSN

SENTRY_DEFAULT_FIELDS = [
    "url",
    "query_string",
    "request_body",
    "local_variables",
]
ROUTES = [account, profile]


def init_observability():
    sentry_sdk.init(dsn=SENTRY_DSN)


init_observability()
