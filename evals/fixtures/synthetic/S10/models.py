"""Data models for tidewharf.

One class per table. The schema is created from these definitions by db.py.
"""

from sqlalchemy import Column, DateTime, Integer, String

from db import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False)
    full_name = Column(String(255))
    signup_ip = Column(String(255))
    last_seen_at = Column(DateTime)
    deleted_at = Column(DateTime)
