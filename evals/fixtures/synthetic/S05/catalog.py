"""Catalogue tables. No personal data is held here."""

from sqlalchemy import Column, Integer, String

from db import Base


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    sku = Column(String(255))
    title = Column(String(255))
