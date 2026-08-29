"""Request logging middleware."""

import logging

logger = logging.getLogger("request_log")


def log_request(request):
    ip_address = request.client.host
    path = request.url.path
    logger.info("%s %s", ip_address, path)
