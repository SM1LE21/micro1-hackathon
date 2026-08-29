"""Profile anonymisation."""

import hashlib

ANONYMISED_NAME = "removed"


def anonymize_user(user):
    user.email = hashlib.sha256(user.email.encode()).hexdigest()
    user.full_name = ANONYMISED_NAME
