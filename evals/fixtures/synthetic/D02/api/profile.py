"""HTTP routes for the profile area.

One function per route. The application object in app.py imports this module
and registers each of them.
"""

from analytics import track_signup
from cache import store_session
from models import User
from search import index_user


def signup(session, user_id):
    user = session.get(User, user_id)
    index_user(user)
    track_signup(user)
    return {"email": user.email, "full_name": user.full_name}


def login(session, user_id, token):
    user = session.get(User, user_id)
    store_session(user, token)
    return {"email": user.email}
