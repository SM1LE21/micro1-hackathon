"""Data models for pulsedeck.

One class per table. The schema is created from these definitions by db.py.
"""

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from db import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False)
    full_name = Column(String(255))
    marketing_opt_in = Column(Boolean)
    created_at = Column(DateTime)
