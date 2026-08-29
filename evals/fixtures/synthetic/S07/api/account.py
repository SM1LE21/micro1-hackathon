"""HTTP routes for the account area.

One function per route. The application object in app.py imports this module
and registers each of them.
"""

from models import User
from privacy import anonymize_user


def close_account(session, user_id):
    """Close the account and anonymise the profile."""
    user = session.get(User, user_id)
    anonymize_user(user)
    session.commit()
