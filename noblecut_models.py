"""
noblecut_models.py
==================
Database models for NobleCut order management system.
Add to your existing models.py on GitHub.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class NoblecutOrder(Base):
    __tablename__ = "noblecut_orders"

    id              = Column(Integer, primary_key=True, index=True)
    order_number    = Column(String, unique=True, index=True)
    status          = Column(String, default="pending")

    # Customer
    customer_name   = Column(String)
    customer_email  = Column(String)
    customer_phone  = Column(String)

    # Shipping
    address_line1   = Column(String)
    address_line2   = Column(String)
    city            = Column(String)
    postcode        = Column(String)
    country         = Column(String, default="United Kingdom")

    # Product
    product_name    = Column(String)
    product_fabric  = Column(String)
    product_size    = Column(String)
    product_color   = Column(String)
    quantity        = Column(Integer, default=1)

    # Pricing
    customer_price  = Column(Float)
    supplier_cost   = Column(Float, default=0)
    profit          = Column(Float, default=0)

    # Payment
    payment_status  = Column(String, default="unpaid")
    payment_method  = Column(String)
    stripe_id       = Column(String)

    # Supplier
    aliexpress_url  = Column(String)
    aliexpress_order_id = Column(String)
    tracking_number = Column(String)
    supplier_notes  = Column(Text)

    # Notes
    customer_notes  = Column(Text)
    admin_notes     = Column(Text)

    # Timestamps
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    shipped_at      = Column(DateTime)
    delivered_at    = Column(DateTime)
