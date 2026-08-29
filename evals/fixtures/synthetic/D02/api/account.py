"""HTTP routes for the account area.

One function per route. The application object in app.py imports this module
and registers each of them.
"""

from cache import purge_session
from models import User


def close_account(session, user_id):
    """Close the account and delete everything we hold about the customer."""
    user = session.get(User, user_id)
    purge_session(email)
    session.delete(user)
    session.commit()
