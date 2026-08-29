"""HTTP routes for the profile area.

One function per route. The application object in app.py imports this module
and registers each of them.
"""

from models import User, Invoice


def get_profile(session, user_id):
    user = session.get(User, user_id)
    return {"email": user.email, "full_name": user.full_name}


def list_invoices(session, user_id):
    invoice = session.query(Invoice).filter(Invoice.user_id == user_id).first()
    return {"billing_name": invoice.billing_name, "reference": invoice.reference}
