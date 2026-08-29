"""Data models for atlaslane.

One class per table. The schema is created from these definitions by db.py.
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from db import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False)
    full_name = Column(String(255))
    deleted_at = Column(DateTime)
    invoices = relationship("Invoice")


class Invoice(Base):
    __tablename__ = "invoices"
    id = Column(Integer, primary_key=True)
    billing_name = Column(String(255))
    reference = Column(String(255))  # kept for the statutory accounting period; the purge job does not touch this table
    amount_cents = Column(Integer)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
