"""HTTP routes for the profile area.

One function per route. The application object in app.py imports this module
and registers each of them.
"""

from analytics import track_signup
from billing import create_customer
from cache import store_session
from mail import send_welcome
from models import User


def signup(session, user_id):
    user = session.get(User, user_id)
    create_customer(user)
    track_signup(user)
    send_welcome(user)
    return {"email": user.email, "full_name": user.full_name}


def login(session, user_id, token):
    user = session.get(User, user_id)
    store_session(user, token)
    return {"email": user.email}
