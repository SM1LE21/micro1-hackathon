"""Data models for harbourdesk.

One class per table. The schema is created from these definitions by db.py.
"""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from db import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False)
    full_name = Column(String(255))
    phone = Column(String(255))
    is_active = Column(Boolean)
    deleted_at = Column(DateTime)
    tickets = relationship("SupportTicket")


class SupportTicket(Base):
    __tablename__ = "tickets"
    id = Column(Integer, primary_key=True)
    subject = Column(String(255))
    body = Column(Text)
    opened_at = Column(DateTime)
    user_id = Column(Integer, ForeignKey("users.id"))
