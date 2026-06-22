import os
from datetime import datetime

import requests
from flask import Flask, jsonify, request
from sqlalchemy import text

from database import configure_database, db, init_db_with_retry

app = Flask(__name__)
configure_database(app)

USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://user-service:5001")
FOOD_SERVICE_URL = os.getenv("FOOD_SERVICE_URL", os.getenv("PRODUCT_SERVICE_URL", "http://product-service:5002"))


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


SAMPLE_ORDERS_STATUS = ["delivered", "delivered", "confirmed", "preparing", "pending", "shipping", "delivered", "cancelled", "confirmed", "pending"]


def fetch_food(food_id):
    response = requests.get(f"{FOOD_SERVICE_URL}/foods/{food_id}", timeout=5)
    if response.status_code == 200:
        return response.json()

    legacy = requests.get(f"{FOOD_SERVICE_URL}/products/{food_id}", timeout=5)
    if legacy.status_code == 200:
        return legacy.json()
    return None


def fetch_user(user_id):
    if user_id is None:
        return None, None, None
    response = requests.get(f"{USER_SERVICE_URL}/users/{user_id}", timeout=5)
    if response.status_code != 200:
        return None, jsonify({"error": "User not found"}), 404
    return response.json(), None, None


def normalize_items(data):
    items = data.get("items")
    if isinstance(items, list) and items:
        normalized = []
        for item in items:
            if not isinstance(item, dict):
                return None, jsonify({"error": "Each item must be an object"}), 400
            food_id = item.get("food_id", item.get("product_id"))
            quantity = item.get("quantity", 1)
            try:
                food_id = int(food_id)
                quantity = int(quantity)
            except (TypeError, ValueError):
                return None, jsonify({"error": "food_id/product_id and quantity must be numbers"}), 400
            if quantity <= 0:
                return None, jsonify({"error": "quantity must be greater than 0"}), 400
            normalized.append({"food_id": food_id, "quantity": quantity})
        return normalized, None, None

    food_id = data.get("food_id", data.get("product_id"))
    quantity = data.get("quantity", 1)
    if not food_id:
        return None, jsonify({"error": "items or food_id/product_id is required"}), 400
    try:
        food_id = int(food_id)
        quantity = int(quantity)
    except (TypeError, ValueError):
        return None, jsonify({"error": "food_id/product_id and quantity must be numbers"}), 400
    if quantity <= 0:
        return None, jsonify({"error": "quantity must be greater than 0"}), 400
    return [{"food_id": food_id, "quantity": quantity}], None, None


def calculate_items_and_total(normalized_items):
    item_rows = []
    for item in normalized_items:
        food = fetch_food(item["food_id"])
        if not food:
            return None, None, jsonify({"error": f"Food {item['food_id']} not found"}), 404
        item_rows.append(
            {
                "food_id": food["id"],
                "food_name": food["name"],
                "price": float(food["price"]),
                "quantity": item["quantity"],
                "line_total": float(food["price"]) * item["quantity"],
            }
        )
    total_price = sum(row["line_total"] for row in item_rows)
    return item_rows, total_price, None, None


def create_order_in_db(user_id, items, total_price, delivery_address=None, note=None, status="pending"):
    order = Order(
        user_id=user_id,
        total_price=total_price,
        status=status,
        delivery_address=delivery_address,
        note=note,
    )
    if status == "cancelled":
        order.cancelled_at = datetime.utcnow()
    if status == "delivered":
        order.delivered_at = datetime.utcnow()

    db.session.add(order)
    db.session.flush()
    for item in items:
        db.session.add(OrderItem(order_id=order.id, product_id=item["food_id"], quantity=item["quantity"]))
    db.session.commit()
    return order


def build_order_response(order):
    user = None
    if order.user_id:
        user, _, _ = fetch_user(order.user_id)

    order_items = []
    for item in order.items:
        food = fetch_food(item.product_id)
        if not food:
            food = {"id": item.product_id, "name": f"Food {item.product_id}", "price": 0, "image_url": "/static/images/foods/default.jpg"}
        line_total = float(food.get("price", 0)) * item.quantity
        order_items.append(
            {
                "food_id": food["id"],
                "product_id": food["id"],
                "food_name": food["name"],
                "product_name": food["name"],
                "price": float(food.get("price", 0)),
                "quantity": item.quantity,
                "line_total": line_total,
                "image_url": food.get("image_url", "/static/images/foods/default.jpg"),
            }
        )

    response = {
        "id": order.id,
        "user_id": order.user_id,
        "user": user,
        "items": order_items,
        "total_price": order.total_price,
        "status": order.status,
        "delivery_address": order.delivery_address,
        "note": order.note,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "cancelled_at": order.cancelled_at.isoformat() if order.cancelled_at else None,
        "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
    }

    if len(order_items) == 1:
        first_item = order_items[0]
        response["product"] = {"id": first_item["food_id"], "name": first_item["food_name"], "price": first_item["price"]}
        response["quantity"] = first_item["quantity"]

    return response


def seed_data():
    if db.session.execute(db.select(Order.id)).first():
        return

    sample_items = [{"food_id": 1, "quantity": 1}, {"food_id": 2, "quantity": 1}, {"food_id": 3, "quantity": 2}, {"food_id": 4, "quantity": 1}]
    for idx, status in enumerate(SAMPLE_ORDERS_STATUS):
        chosen = sample_items[idx % len(sample_items)]
        food = fetch_food(chosen["food_id"])
        if not food:
            continue
        total_price = float(food["price"]) * chosen["quantity"]
        create_order_in_db(
            user_id=1 if idx % 2 == 0 else 2,
            items=[chosen],
            total_price=total_price,
            delivery_address="TP.HCM",
            note="Đơn hàng mẫu",
            status=status,
        )


@app.post("/orders")
def create_order():
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400

    _, error_response, error_code = fetch_user(int(user_id))
    if error_response:
        return error_response, error_code

    normalized_items, error_response, error_code = normalize_items(data)
    if error_response:
        return error_response, error_code

    _, total_price, error_response, error_code = calculate_items_and_total(normalized_items)
    if error_response:
        return error_response, error_code

    order = create_order_in_db(
        user_id=int(user_id),
        items=normalized_items,
        total_price=total_price,
        delivery_address=data.get("delivery_address"),
        note=data.get("note"),
        status="pending",
    )
    return jsonify({"message": "Order created", "order": build_order_response(order)}), 201


@app.post("/cart/checkout")
def checkout_cart():
    data = request.get_json(silent=True) or {}
    items = data.get("items")
    user_id = data.get("user_id")
    if not isinstance(items, list) or not items:
        return jsonify({"error": "items is required"}), 400

    normalized_items, error_response, error_code = normalize_items({"items": items})
    if error_response:
        return error_response, error_code

    if user_id is not None:
        _, error_response, error_code = fetch_user(int(user_id))
        if error_response:
            return error_response, error_code

    item_rows, total_price, error_response, error_code = calculate_items_and_total(normalized_items)
    if error_response:
        return error_response, error_code

    order = create_order_in_db(
        user_id=int(user_id) if user_id is not None else None,
        items=normalized_items,
        total_price=total_price,
        delivery_address=data.get("delivery_address"),
        note=data.get("note"),
        status="pending",
    )
    return jsonify({"message": "Checkout successful", "order_id": order.id, "items": item_rows, "total_price": total_price}), 201


@app.get("/orders/<int:order_id>")
def get_order(order_id: int):
    order = db.session.get(Order, order_id)
    if not order:
        return jsonify({"error": "Order not found"}), 404
    return jsonify(build_order_response(order))


@app.get("/orders")
def list_orders():
    user_id = request.args.get("user_id", type=int)
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)

    query = db.select(Order)
    if user_id is not None:
        query = query.where(Order.user_id == user_id)
    query = query.order_by(Order.created_at.desc())

    pagination = db.paginate(query, page=page, per_page=per_page, error_out=False)
    return jsonify(
        {
            "orders": [build_order_response(order) for order in pagination.items],
            "total": pagination.total,
            "pages": pagination.pages,
            "current_page": page,
        }
    )


@app.put("/orders/<int:order_id>/cancel")
def cancel_order(order_id: int):
    order = db.session.get(Order, order_id)
    if not order:
        return jsonify({"error": "Order not found"}), 404
    if order.status != "pending":
        return jsonify({"error": "Only pending orders can be cancelled"}), 400

    order.status = "cancelled"
    order.cancelled_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"message": "Order cancelled", "order": build_order_response(order)})


@app.put("/orders/<int:order_id>/status")
def update_status(order_id: int):
    order = db.session.get(Order, order_id)
    if not order:
        return jsonify({"error": "Order not found"}), 404

    data = request.get_json(silent=True) or {}
    status = str(data.get("status", "")).strip()
    allowed = {"pending", "confirmed", "preparing", "shipping", "delivered", "cancelled"}
    if status not in allowed:
        return jsonify({"error": "Invalid status"}), 400

    order.status = status
    if status == "cancelled":
        order.cancelled_at = datetime.utcnow()
    if status == "delivered":
        order.delivered_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"message": "Status updated", "order": build_order_response(order)})


@app.get("/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as exc:  # pragma: no cover
        db_status = str(exc)

    status = "ok" if db_status == "ok" else "degraded"
    code = 200 if status == "ok" else 503
    return jsonify({"status": status, "service": "order-service", "database": db_status, "timestamp": datetime.utcnow().isoformat()}), code


if __name__ == "__main__":
    init_db_with_retry(app)
    with app.app_context():
        seed_data()
    app.run(host="0.0.0.0", port=5003, debug=False)
