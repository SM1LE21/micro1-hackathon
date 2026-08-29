"""HTTP routes for the account area.

One function per route. The application object in app.py imports this module
and registers each of them.
"""

from models import User
from storage import delete_avatar


def delete_account(session, user_id):
    """Delete the account, then remove the avatar from object storage."""
    user = session.get(User, user_id)
    delete_avatar(user.id)
    session.delete(user)
    session.commit()
