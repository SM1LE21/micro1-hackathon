"""Data models for quillrest.

One class per table. The schema is created from these definitions by db.py.
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from db import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False)
    full_name = Column(String(255))
    metadata_json = Column(JSON)  # arbitrary key/value set by the client; support pastes contact details in here
    deleted_at = Column(DateTime)
    tickets = relationship("SupportTicket")


class SupportTicket(Base):
    __tablename__ = "tickets"
    id = Column(Integer, primary_key=True)
    subject = Column(String(255))
    notes = Column(Text)  # free text; may contain phone numbers
    opened_at = Column(DateTime)
    user_id = Column(Integer, ForeignKey("users.id"))
