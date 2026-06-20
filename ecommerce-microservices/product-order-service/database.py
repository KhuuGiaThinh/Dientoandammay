import os
import time
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

db = SQLAlchemy()


def configure_database(app):
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://order_food:pass@product-order-db:5432/orderfooddb",
    )
    # Automatically convert postgres:// to postgresql+psycopg2:// for Railway/SQLAlchemy compatibility
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif db_url.startswith("postgresql://") and not db_url.startswith("postgresql+psycopg2://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)


def init_db_with_retry(app, max_attempts=20, delay_seconds=2):
    last_error = None
    for _ in range(max_attempts):
        try:
            with app.app_context():
                db.session.execute(text("SELECT 1"))
                db.create_all()
            return
        except OperationalError as exc:
            last_error = exc
            time.sleep(delay_seconds)
    if last_error:
        raise last_error


class FoodItem(db.Model):
    __tablename__ = "food_items"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(100))
    restaurant = db.Column(db.String(200))
    image_filename = db.Column(db.String(200), default="default.jpg")
    is_available = db.Column(db.Boolean, default=True)
    rating = db.Column(db.Float, default=4.0)
    prep_time = db.Column(db.Integer, default=20)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "price": self.price,
            "category": self.category,
            "restaurant": self.restaurant,
            "image_filename": self.image_filename,
            "image_url": f"/static/images/foods/{self.image_filename or 'default.jpg'}",
            "is_available": self.is_available,
            "rating": self.rating,
            "prep_time": self.prep_time,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=True)
    total_price = db.Column(db.Float, nullable=False, default=0)
    status = db.Column(db.String(50), default="pending")
    delivery_address = db.Column(db.Text)
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    cancelled_at = db.Column(db.DateTime)
    delivered_at = db.Column(db.DateTime)
    items = db.relationship("OrderItem", backref="order", cascade="all, delete-orphan", lazy=True)


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    product_id = db.Column(db.Integer, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
