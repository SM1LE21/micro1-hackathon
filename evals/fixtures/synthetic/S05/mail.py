"""Transactional mail."""

import sendgrid

from config import SENDGRID_API_KEY

sg = sendgrid.SendGridAPIClient(SENDGRID_API_KEY)


def send_welcome(user):
    body = f"Welcome, {user.full_name}."
    sg.send(to=user.email, subject="Welcome", body=body)
