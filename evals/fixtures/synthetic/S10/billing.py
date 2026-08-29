"""Payment integration."""

import stripe

from config import STRIPE_API_KEY

stripe.api_key = STRIPE_API_KEY


def create_customer(user):
    return stripe.Customer.create(
        email=user.email,
        name=user.full_name,
    )
