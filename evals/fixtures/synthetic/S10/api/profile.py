"""HTTP routes for the profile area.

One function per route. The application object in app.py imports this module
and registers each of them.
"""

from billing import create_customer
from models import User
from storage import upload_avatar


def signup(session, user_id):
    user = session.get(User, user_id)
    create_customer(user)
    return {"email": user.email, "full_name": user.full_name}


def set_avatar(session, user_id, data, original_filename):
    user = session.get(User, user_id)
    upload_avatar(user.id, data, original_filename)
    return {"id": user.id}
