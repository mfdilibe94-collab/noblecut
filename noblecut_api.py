"""
noblecut_api.py
===============
FastAPI routes for NobleCut order management.
Add these routes to your existing main.py on GitHub.
"""

import os
import random
import string
import requests
from datetime import datetime
from fastapi import APIRouter, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
STRIPE_SECRET_KEY  = os.getenv("STRIPE_SECRET_KEY", "")

router = APIRouter(prefix="/noblecut", tags=["NobleCut"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class OrderCreate(BaseModel):
    customer_name:   str
    customer_email:  str
    customer_phone:  str
    address_line1:   str
    address_line2:   Optional[str] = ""
    city:            str
    postcode:        str
    country:         str = "United Kingdom"
    product_name:    str
    product_fabric:  str
    product_size:    str
    product_color:   Optional[str] = ""
    quantity:        int = 1
    customer_price:  float
    customer_notes:  Optional[str] = ""
    payment_method:  str = "stripe"
    stripe_token:    Optional[str] = ""


class OrderUpdate(BaseModel):
    status:              Optional[str] = None
    payment_status:      Optional[str] = None
    supplier_cost:       Optional[float] = None
    aliexpress_url:      Optional[str] = None
    aliexpress_order_id: Optional[str] = None
    tracking_number:     Optional[str] = None
    admin_notes:         Optional[str] = None


class EnquiryCreate(BaseModel):
    name:       str
    email:      str
    phone:      str
    occasion:   str
    message:    str


# ── Helpers ───────────────────────────────────────────────────────────────────

def gen_order_number():
    chars = string.ascii_uppercase + string.digits
    return "NC-" + "".join(random.choices(chars, k=8))


def send_telegram(msg: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
            timeout=10
        )
    except Exception as e:
        print("Telegram error: " + str(e))


def charge_stripe(token: str, amount_pence: int, description: str) -> dict:
    """Charge a card via Stripe."""
    if not STRIPE_SECRET_KEY:
        return {"success": False, "error": "Stripe not configured"}
    try:
        r = requests.post(
            "https://api.stripe.com/v1/charges",
            auth=(STRIPE_SECRET_KEY, ""),
            data={
                "amount":      amount_pence,
                "currency":    "gbp",
                "source":      token,
                "description": description,
            },
            timeout=15
        )
        data = r.json()
        if r.status_code == 200 and data.get("paid"):
            return {"success": True, "charge_id": data["id"]}
        else:
            return {"success": False, "error": data.get("error", {}).get("message", "Payment failed")}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/orders")
def create_order(order: OrderCreate):
    """
    Place a new NobleCut order.
    Charges Stripe, saves to DB, sends Telegram alert.
    """
    from database import SessionLocal
    from noblecut_models import NoblecutOrder

    db = SessionLocal()
    try:
        # 1. Charge Stripe if token provided
        stripe_id = ""
        if order.payment_method == "stripe" and order.stripe_token:
            result = charge_stripe(
                order.stripe_token,
                int(order.customer_price * 100),
                f"NobleCut — {order.product_name}"
            )
            if not result["success"]:
                raise HTTPException(status_code=400, detail=result["error"])
            stripe_id = result.get("charge_id", "")

        # 2. Save order to database
        order_number = gen_order_number()
        db_order = NoblecutOrder(
            order_number   = order_number,
            status         = "new",
            customer_name  = order.customer_name,
            customer_email = order.customer_email,
            customer_phone = order.customer_phone,
            address_line1  = order.address_line1,
            address_line2  = order.address_line2 or "",
            city           = order.city,
            postcode       = order.postcode,
            country        = order.country,
            product_name   = order.product_name,
            product_fabric = order.product_fabric,
            product_size   = order.product_size,
            product_color  = order.product_color or "",
            quantity       = order.quantity,
            customer_price = order.customer_price,
            payment_status = "paid" if stripe_id else "pending",
            payment_method = order.payment_method,
            stripe_id      = stripe_id,
            customer_notes = order.customer_notes or "",
        )
        db.add(db_order)
        db.commit()
        db.refresh(db_order)

        # 3. Send Telegram alert
        send_telegram(
            "NEW NOBLECUT ORDER\n"
            "Order: " + order_number + "\n"
            "Customer: " + order.customer_name + "\n"
            "Email: " + order.customer_email + "\n"
            "Phone: " + order.customer_phone + "\n"
            "Product: " + order.product_name + "\n"
            "Fabric: " + order.product_fabric + "\n"
            "Size: " + order.product_size + "\n"
            "Price: £" + str(order.customer_price) + "\n"
            "Payment: " + ("PAID via Stripe" if stripe_id else "PENDING") + "\n"
            "Address: " + order.address_line1 + ", " + order.city + ", " + order.postcode + "\n"
            "Notes: " + (order.customer_notes or "none") + "\n"
            "ACTION: Order from AliExpress and update tracking"
        )

        return {
            "success":      True,
            "order_number": order_number,
            "message":      "Order placed successfully! You will receive a confirmation email shortly."
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print("Order error: " + str(e))
        raise HTTPException(status_code=500, detail="Order failed: " + str(e))
    finally:
        db.close()


@router.get("/orders")
def get_orders(status: Optional[str] = None, limit: int = 50):
    """Get all NobleCut orders. Filter by status."""
    from database import SessionLocal
    from noblecut_models import NoblecutOrder

    db = SessionLocal()
    try:
        q = db.query(NoblecutOrder)
        if status:
            q = q.filter(NoblecutOrder.status == status)
        orders = q.order_by(NoblecutOrder.created_at.desc()).limit(limit).all()
        return [
            {
                "id":             o.id,
                "order_number":   o.order_number,
                "status":         o.status,
                "customer_name":  o.customer_name,
                "customer_email": o.customer_email,
                "customer_phone": o.customer_phone,
                "product_name":   o.product_name,
                "product_size":   o.product_size,
                "customer_price": o.customer_price,
                "supplier_cost":  o.supplier_cost,
                "profit":         round((o.customer_price or 0) - (o.supplier_cost or 0), 2),
                "payment_status": o.payment_status,
                "tracking":       o.tracking_number,
                "aliexpress_url": o.aliexpress_url,
                "address":        f"{o.address_line1}, {o.city}, {o.postcode}",
                "notes":          o.customer_notes,
                "created_at":     str(o.created_at),
            }
            for o in orders
        ]
    finally:
        db.close()


@router.patch("/orders/{order_id}")
def update_order(order_id: int, update: OrderUpdate):
    """Update order — add tracking, supplier cost, AliExpress details."""
    from database import SessionLocal
    from noblecut_models import NoblecutOrder

    db = SessionLocal()
    try:
        order = db.query(NoblecutOrder).filter(NoblecutOrder.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        if update.status:              order.status              = update.status
        if update.payment_status:      order.payment_status      = update.payment_status
        if update.supplier_cost:
            order.supplier_cost = update.supplier_cost
            order.profit        = (order.customer_price or 0) - update.supplier_cost
        if update.aliexpress_url:      order.aliexpress_url      = update.aliexpress_url
        if update.aliexpress_order_id: order.aliexpress_order_id = update.aliexpress_order_id
        if update.admin_notes:         order.admin_notes         = update.admin_notes

        if update.tracking_number:
            order.tracking_number = update.tracking_number
            order.status          = "shipped"
            order.shipped_at      = datetime.utcnow()
            # Notify customer via Telegram
            send_telegram(
                "ORDER SHIPPED\n"
                "Order: " + order.order_number + "\n"
                "Customer: " + order.customer_name + "\n"
                "Tracking: " + update.tracking_number + "\n"
                "Send tracking to: " + order.customer_email
            )

        order.updated_at = datetime.utcnow()
        db.commit()
        return {"success": True, "message": "Order updated"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.get("/orders/stats")
def get_stats():
    """Revenue and profit dashboard stats."""
    from database import SessionLocal
    from noblecut_models import NoblecutOrder
    from sqlalchemy import func

    db = SessionLocal()
    try:
        total_orders   = db.query(NoblecutOrder).count()
        total_revenue  = db.query(func.sum(NoblecutOrder.customer_price)).scalar() or 0
        total_cost     = db.query(func.sum(NoblecutOrder.supplier_cost)).scalar() or 0
        total_profit   = total_revenue - total_cost
        new_orders     = db.query(NoblecutOrder).filter(NoblecutOrder.status == "new").count()
        shipped        = db.query(NoblecutOrder).filter(NoblecutOrder.status == "shipped").count()
        return {
            "total_orders":  total_orders,
            "new_orders":    new_orders,
            "shipped":       shipped,
            "total_revenue": round(total_revenue, 2),
            "total_cost":    round(total_cost, 2),
            "total_profit":  round(total_profit, 2),
        }
    finally:
        db.close()


@router.post("/enquiries")
def submit_enquiry(enquiry: EnquiryCreate):
    """Handle bespoke consultation enquiries."""
    send_telegram(
        "BESPOKE ENQUIRY\n"
        "Name: " + enquiry.name + "\n"
        "Email: " + enquiry.email + "\n"
        "Phone: " + enquiry.phone + "\n"
        "Occasion: " + enquiry.occasion + "\n"
        "Message: " + enquiry.message
    )
    return {"success": True, "message": "Enquiry received! We'll be in touch within 24 hours."}
