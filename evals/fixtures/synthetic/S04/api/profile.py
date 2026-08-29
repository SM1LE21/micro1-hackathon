"""HTTP routes for the profile area.

One function per route. The application object in app.py imports this module
and registers each of them.
"""

from models import User
from storage import upload_avatar


def set_avatar(session, user_id, data):
    user = session.get(User, user_id)
    upload_avatar(user.id, data)
    return {"id": user.id}


def get_profile(session, user_id):
    user = session.get(User, user_id)
    return {"email": user.email, "full_name": user.full_name}
