"""Catalogue tables. No personal data is held here."""

from sqlalchemy import Column, Integer, String

from db import Base


class Plan(Base):
    __tablename__ = "plans"
    id = Column(Integer, primary_key=True)
    code = Column(String(255))
    monthly_cents = Column(Integer)
