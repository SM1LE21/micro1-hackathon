"""HTTP routes for the account area.

One function per route. The application object in app.py imports this module
and registers each of them.
"""

from datetime import datetime, timezone

from models import User


def close_account(session, user_id):
    """Close the account. The user can no longer sign in."""
    user = session.get(User, user_id)
    user.deleted_at = datetime.now(timezone.utc)
    user.is_active = False
    session.commit()
