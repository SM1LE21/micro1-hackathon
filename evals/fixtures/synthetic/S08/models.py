"""Data models for civicbeam.

One class per table. The schema is created from these definitions by db.py.
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from db import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False)
    full_name = Column(String(255))
    phone = Column(String(255))
    created_at = Column(DateTime)
    documents = relationship("Document", cascade="all, delete")


class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True)
    title = Column(String(255))
    body = Column(Text)
    user_id = Column(Integer, ForeignKey("users.id"))
