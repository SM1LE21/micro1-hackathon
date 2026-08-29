"""Data models for tidepool.

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
    newsletter = Column(Boolean)
    created_at = Column(DateTime)
    orders = relationship("Order", cascade="all, delete")
    tickets = relationship("Ticket")


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    total_cents = Column(Integer)
    shipping_address = Column(String(255))
    user_id = Column(Integer, ForeignKey("users.id"))


class Ticket(Base):
    __tablename__ = "tickets"
    id = Column(Integer, primary_key=True)
    body = Column(Text)  # customer messages; may contain phone numbers
    opened_at = Column(DateTime)
    user_id = Column(Integer, ForeignKey("users.id"))
