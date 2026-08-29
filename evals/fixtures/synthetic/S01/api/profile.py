"""HTTP routes for the profile area.

One function per route. The application object in app.py imports this module
and registers each of them.
"""

from models import User, Order


def get_profile(session, user_id):
    user = session.get(User, user_id)
    return {"email": user.email, "full_name": user.full_name}


def list_orders(session, user_id):
    order = session.query(Order).filter(Order.user_id == user_id).first()
    return {"shipping_address": order.shipping_address, "amount_cents": order.amount_cents}
