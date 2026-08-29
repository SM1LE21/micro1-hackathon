"""HTTP routes for the account area.

One function per route. The application object in app.py imports this module
and registers each of them.
"""

from models import User, Document
from queue import publish_document_created
from search import index_document
from storage import upload_document


def create_document(session, user_id, data):
    user = session.get(User, user_id)
    document = session.query(Document).filter(Document.user_id == user_id).first()
    upload_document(user.id, document.id, data)
    index_document(user, document)
    publish_document_created(user)
    return {"email": user.email, "title": document.title}


def get_profile(session, user_id):
    user = session.get(User, user_id)
    return {"email": user.email, "phone": user.phone}
