"""Data models for snapledger.

One class per table. The schema is created from these definitions by db.py.
"""

from sqlalchemy import Column, DateTime, Integer, String

from db import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False)
    full_name = Column(String(255))
    created_at = Column(DateTime)
