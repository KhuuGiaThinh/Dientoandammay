import os
import re
import unicodedata
from datetime import datetime

import requests
from flask import Flask, jsonify, request
from sqlalchemy import text

from database import configure_database, db, init_db_with_retry

app = Flask(__name__)
configure_database(app)

USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://user-service:5001")


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


def slugify(text_value: str):
    normalized = unicodedata.normalize("NFD", text_value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_text = ascii_text.lower().strip()
    ascii_text = re.sub(r"[^a-z0-9]+", "-", ascii_text)
    ascii_text = re.sub(r"-+", "-", ascii_text).strip("-")
    return ascii_text or "default"


SAMPLE_FOODS = [
    {"name": "Cơm tấm sườn bì chả", "price": 55000, "category": "Cơm", "restaurant": "Cơm Tấm Thuận Kiều", "prep_time": 15, "rating": 4.8, "description": "Cơm tấm thơm dẻo với sườn nướng mật ong, bì heo, chả trứng, kèm nước mắm chua ngọt đặc trưng."},
    {"name": "Cơm gà xối mỡ", "price": 60000, "category": "Cơm", "restaurant": "Cơm Gà Bà Năm", "prep_time": 20, "rating": 4.6, "description": "Gà ta xối mỡ giòn da, ăn kèm cơm trắng và nước chấm gừng thơm."},
    {"name": "Cơm chiên dương châu", "price": 50000, "category": "Cơm", "restaurant": "Nhà Hàng Phương Nam", "prep_time": 10, "rating": 4.3, "description": "Cơm chiên với tôm, thịt, trứng, hành lá, đậu xanh kiểu Dương Châu."},
    {"name": "Phở bò tái chín", "price": 70000, "category": "Phở", "restaurant": "Phở Hùng", "prep_time": 10, "rating": 4.9, "description": "Nước dùng hầm xương 12 tiếng, thịt bò tươi tái và chín mềm, bánh phở dai."},
    {"name": "Bún bò Huế", "price": 65000, "category": "Bún", "restaurant": "Quán Bún Bà Hiền", "prep_time": 12, "rating": 4.7, "description": "Nước lèo sả ớt cay nồng đặc trưng Huế, với chả heo, giò heo mềm."},
    {"name": "Bún riêu cua", "price": 60000, "category": "Bún", "restaurant": "Quán Bún Bà Hiền", "prep_time": 15, "rating": 4.5, "description": "Riêu cua đồng thơm béo, cà chua chua ngọt, đậu hũ chiên, rau sống tươi."},
    {"name": "Mì Quảng gà", "price": 58000, "category": "Mì", "restaurant": "Mì Quảng Ông Tư", "prep_time": 15, "rating": 4.6, "description": "Mì vàng béo nước nhân gà, đậu phộng rang, bánh tráng nướng giòn."},
    {"name": "Hủ tiếu Nam Vang", "price": 62000, "category": "Bún", "restaurant": "Hủ Tiếu Thanh Xuân", "prep_time": 12, "rating": 4.5, "description": "Hủ tiếu dai mềm, thịt heo xay, tôm tươi, gan heo, nước lèo trong ngọt."},
    {"name": "Bánh mì thịt nguội", "price": 30000, "category": "Bánh mì", "restaurant": "Bánh Mì Huynh Hoa", "prep_time": 5, "rating": 4.9, "description": "Bánh mì giòn xốp với pate, thịt nguội, chả lụa, dưa leo, đồ chua rau mùi."},
    {"name": "Bánh mì gà nướng", "price": 35000, "category": "Bánh mì", "restaurant": "Bánh Mì Huynh Hoa", "prep_time": 7, "rating": 4.7, "description": "Ức gà nướng sả ớt thơm lừng, kẹp bánh mì nóng giòn, sốt mayo tỏi."},
    {"name": "Bánh cuốn tôm thịt", "price": 45000, "category": "Bánh", "restaurant": "Bánh Cuốn Thanh Trì", "prep_time": 10, "rating": 4.6, "description": "Bánh cuốn tráng mỏng nhân tôm thịt mộc nhĩ, ăn kèm chả quế và nước chấm."},
    {"name": "Lẩu thái hải sản", "price": 250000, "category": "Lẩu", "restaurant": "Lẩu Nướng Hoàng Gia", "prep_time": 20, "rating": 4.8, "description": "Lẩu thái chua cay với tôm, mực, cá, nấm các loại, rau sống phong phú."},
    {"name": "Lẩu bò nhúng dấm", "price": 220000, "category": "Lẩu", "restaurant": "Lẩu Nướng Hoàng Gia", "prep_time": 20, "rating": 4.7, "description": "Thịt bò Mỹ thượng hạng nhúng dấm, cuốn bánh tráng rau sống bún tươi."},
    {"name": "Gà nướng mật ong", "price": 150000, "category": "Nướng", "restaurant": "BBQ Việt", "prep_time": 30, "rating": 4.7, "description": "Gà ta nướng than hoa ướp mật ong sả ớt, da giòn thịt mềm."},
    {"name": "Sườn nướng BBQ", "price": 120000, "category": "Nướng", "restaurant": "BBQ Việt", "prep_time": 25, "rating": 4.6, "description": "Sườn heo non ướp sốt BBQ Mỹ, nướng than cho đến khi caramel hóa."},
    {"name": "Cơm chay thập cẩm", "price": 40000, "category": "Chay", "restaurant": "Quán Chay Tâm An", "prep_time": 10, "rating": 4.4, "description": "Cơm trắng với các món chay phong phú: đậu hũ, rau củ, nấm, dưa cải."},
    {"name": "Phở chay nấm", "price": 45000, "category": "Chay", "restaurant": "Quán Chay Tâm An", "prep_time": 10, "rating": 4.3, "description": "Nước dùng từ rau củ và nấm, bánh phở mềm, ăn kèm rau sống."},
    {"name": "Trà sữa trân châu đen", "price": 45000, "category": "Đồ uống", "restaurant": "The Alley", "prep_time": 5, "rating": 4.8, "description": "Trà sữa pha sẵn với trân châu đen dẻo, có thể chọn độ ngọt và đá."},
    {"name": "Cà phê sữa đá", "price": 30000, "category": "Đồ uống", "restaurant": "Phúc Long", "prep_time": 3, "rating": 4.9, "description": "Cà phê phin truyền thống đậm đà pha sữa đặc, uống với đá."},
    {"name": "Nước ép cam tươi", "price": 35000, "category": "Đồ uống", "restaurant": "Juice Bar Fresh", "prep_time": 5, "rating": 4.6, "description": "Cam vắt tươi nguyên chất 100%, không đường, không phẩm màu."},
    {"name": "Sinh tố bơ mật ong", "price": 40000, "category": "Đồ uống", "restaurant": "Juice Bar Fresh", "prep_time": 5, "rating": 4.7, "description": "Bơ Đắk Lắk chín mềm xay với sữa và mật ong, béo ngậy."},
    {"name": "Chè ba màu", "price": 25000, "category": "Tráng miệng", "restaurant": "Chè Hiển Khánh", "prep_time": 5, "rating": 4.5, "description": "Đậu xanh, đậu đỏ, thạch lá dứa, nước dừa mát lạnh."},
    {"name": "Kem dừa Bến Tre", "price": 30000, "category": "Tráng miệng", "restaurant": "Chè Hiển Khánh", "prep_time": 3, "rating": 4.7, "description": "Cơm dừa tươi, kem vanilla, thạch dừa, thịt dừa non giòn."},
    {"name": "Bánh flan caramel", "price": 28000, "category": "Tráng miệng", "restaurant": "Pâtisserie Sài Gòn", "prep_time": 5, "rating": 4.6, "description": "Bánh flan mịn mượt kiểu Pháp, sốt caramel đắng nhẹ."},
    {"name": "Pizza Margherita", "price": 160000, "category": "Pizza", "restaurant": "Pizza 4P's", "prep_time": 20, "rating": 4.8, "description": "Pizza truyền thống với sốt cà chua, phô mai mozzarella tươi, húng quế."},
    {"name": "Pizza hải sản", "price": 190000, "category": "Pizza", "restaurant": "Pizza 4P's", "prep_time": 20, "rating": 4.7, "description": "Tôm, mực, cua, sốt kem trắng, phô mai kéo sợi."},
    {"name": "Chả giò chiên", "price": 35000, "category": "Ăn vặt", "restaurant": "Quán Ăn Bình Dân", "prep_time": 10, "rating": 4.5, "description": "Chả giò tôm thịt chiên giòn vàng, chấm tương ớt chua ngọt."},
    {"name": "Gỏi cuốn tôm thịt", "price": 40000, "category": "Ăn vặt", "restaurant": "Quán Ăn Bình Dân", "prep_time": 10, "rating": 4.6, "description": "Cuốn tươi với tôm, thịt, bún, rau sống, chấm tương hoisin đậu phộng."},
    {"name": "Bánh tráng trộn", "price": 28000, "category": "Ăn vặt", "restaurant": "Ăn Vặt Cô Ba", "prep_time": 7, "rating": 4.4, "description": "Bánh tráng mềm trộn khô bò, xoài xanh, trứng cút, sa tế, rau răm."},
    {"name": "Tokbokki hải sản", "price": 69000, "category": "Ăn vặt", "restaurant": "K-Food House", "prep_time": 15, "rating": 4.5, "description": "Bánh gạo Hàn Quốc cay ngọt, thêm chả cá và hải sản tươi."},
]

SAMPLE_ORDERS_STATUS = ["delivered", "delivered", "confirmed", "preparing", "pending", "shipping", "delivered", "cancelled", "confirmed", "pending"]


def seed_foods():
    if db.session.execute(db.select(FoodItem.id)).first():
        return

    for index, food in enumerate(SAMPLE_FOODS, start=1):
        image_filename = f"{index}.jpg"
        db.session.add(
            FoodItem(
                name=food["name"],
                description=food["description"],
                price=food["price"],
                category=food["category"],
                restaurant=food["restaurant"],
                rating=food["rating"],
                prep_time=food["prep_time"],
                image_filename=image_filename,
                is_available=True,
            )
        )
    db.session.commit()


def fetch_food(food_id):
    food = db.session.get(FoodItem, food_id)
    return food.to_dict() if food else None


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


def seed_orders():
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
            note="Don hang mau",
            status=status,
        )


def seed_data():
    seed_foods()
    seed_orders()


@app.get("/foods")
def get_foods():
    search = request.args.get("search", "").strip()
    category = request.args.get("category", "").strip()
    restaurant = request.args.get("restaurant", "").strip()
    min_price = request.args.get("min_price", 0, type=float)
    max_price = request.args.get("max_price", 9999999, type=float)
    sort_by = request.args.get("sort", "name")

    query = db.select(FoodItem).where(FoodItem.is_available.is_(True))
    if search:
        query = query.where(FoodItem.name.ilike(f"%{search}%"))
    if category:
        query = query.where(FoodItem.category == category)
    if restaurant:
        query = query.where(FoodItem.restaurant == restaurant)
    query = query.where(FoodItem.price.between(min_price, max_price))

    if sort_by == "price_asc":
        query = query.order_by(FoodItem.price.asc())
    elif sort_by == "price_desc":
        query = query.order_by(FoodItem.price.desc())
    elif sort_by == "rating":
        query = query.order_by(FoodItem.rating.desc())
    else:
        query = query.order_by(FoodItem.name.asc())

    foods = db.session.execute(query).scalars().all()
    return jsonify([food.to_dict() for food in foods])


@app.get("/foods/<int:food_id>")
def get_food(food_id: int):
    food = db.session.get(FoodItem, food_id)
    if not food:
        return jsonify({"error": "Food not found"}), 404
    return jsonify(food.to_dict())


@app.get("/foods/categories")
def get_categories():
    rows = db.session.execute(db.select(FoodItem.category).distinct().where(FoodItem.category.is_not(None))).all()
    categories = sorted([row[0] for row in rows if row[0]])
    return jsonify(categories)


@app.get("/foods/restaurants")
def get_restaurants():
    rows = db.session.execute(db.select(FoodItem.restaurant).distinct().where(FoodItem.restaurant.is_not(None))).all()
    restaurants = sorted([row[0] for row in rows if row[0]])
    return jsonify(restaurants)


@app.post("/foods")
def create_food():
    data = request.get_json(silent=True) or {}
    required_fields = ["name", "price"]
    for field in required_fields:
        if not data.get(field):
            return jsonify({"error": f"{field} is required"}), 400

    food = FoodItem(
        name=data["name"].strip(),
        description=(data.get("description") or "").strip(),
        price=float(data["price"]),
        category=(data.get("category") or "").strip(),
        restaurant=(data.get("restaurant") or "").strip(),
        image_filename=(data.get("image_filename") or f"{slugify(data['name'])}.jpg").strip(),
        is_available=bool(data.get("is_available", True)),
        rating=float(data.get("rating", 4.0)),
        prep_time=int(data.get("prep_time", 20)),
    )
    db.session.add(food)
    db.session.commit()
    return jsonify({"message": "Food created", "food": food.to_dict()}), 201


@app.put("/foods/<int:food_id>")
def update_food(food_id: int):
    food = db.session.get(FoodItem, food_id)
    if not food:
        return jsonify({"error": "Food not found"}), 404

    data = request.get_json(silent=True) or {}
    if "name" in data:
        food.name = str(data["name"]).strip()
    if "description" in data:
        food.description = str(data["description"]).strip()
    if "price" in data:
        food.price = float(data["price"])
    if "category" in data:
        food.category = str(data["category"]).strip()
    if "restaurant" in data:
        food.restaurant = str(data["restaurant"]).strip()
    if "image_filename" in data:
        food.image_filename = str(data["image_filename"]).strip()
    if "is_available" in data:
        food.is_available = bool(data["is_available"])
    if "rating" in data:
        food.rating = float(data["rating"])
    if "prep_time" in data:
        food.prep_time = int(data["prep_time"])

    db.session.commit()
    return jsonify({"message": "Food updated", "food": food.to_dict()})


# Backward compatibility endpoints
@app.get("/products")
def legacy_products():
    return get_foods()


@app.get("/products/<int:product_id>")
def legacy_product_detail(product_id: int):
    return get_food(product_id)


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
    return jsonify({"status": status, "service": "food-order-service", "database": db_status, "timestamp": datetime.utcnow().isoformat()}), code


if __name__ == "__main__":
    init_db_with_retry(app)
    with app.app_context():
        seed_data()
    app.run(host="0.0.0.0", port=5002, debug=False)
