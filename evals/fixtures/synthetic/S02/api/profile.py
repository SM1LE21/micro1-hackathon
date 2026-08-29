"""HTTP routes for the profile area.

One function per route. The application object in app.py imports this module
and registers each of them.
"""

from models import User, SupportTicket


def get_profile(session, user_id):
    user = session.get(User, user_id)
    return {"email": user.email, "phone": user.phone}


def list_tickets(session, user_id):
    support_ticket = session.query(SupportTicket).filter(SupportTicket.user_id == user_id).first()
    return {"subject": support_ticket.subject}
