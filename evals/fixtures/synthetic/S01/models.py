"""Data models for orderly.

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
    created_at = Column(DateTime)
    orders = relationship("Order", cascade="all, delete")


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    shipping_address = Column(String(255))
    amount_cents = Column(Integer)
    placed_at = Column(DateTime)
    user_id = Column(Integer, ForeignKey("users.id"))
