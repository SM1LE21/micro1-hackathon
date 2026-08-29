"""Session cache."""

import redis

from config import REDIS_URL

SESSION_TTL_SECONDS = 86400
cache = redis.Redis.from_url(REDIS_URL)


def store_session(user, token):
    cache.setex(f"sessions:{user.email}", SESSION_TTL_SECONDS, token)


def purge_session(user):
    cache.delete(f"sessions:{user.email}")
