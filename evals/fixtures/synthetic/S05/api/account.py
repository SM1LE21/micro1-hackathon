"""HTTP routes for the account area.

One function per route. The application object in app.py imports this module
and registers each of them.
"""

from models import User


def delete_account(session, user_id):
    """Delete the account row."""
    user = session.get(User, user_id)
    session.delete(user)
    session.commit()
