"""Application object for quillrest."""

from api import account, profile
from middleware import log_request

ROUTES = [account, profile]
MIDDLEWARE = [log_request]
