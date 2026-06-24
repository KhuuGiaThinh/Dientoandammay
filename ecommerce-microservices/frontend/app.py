import os
from pathlib import Path

import requests
from flask import Flask, flash, jsonify, redirect, render_template, request, send_from_directory, session, url_for

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "foodnow-dev-secret-2024")

API_GATEWAY_URL = os.getenv("API_GATEWAY_URL", "http://api-gateway:5000")
FOOD_IMAGE_DIR = Path(app.root_path) / "static" / "images" / "foods"


def gateway_get(path, params=None):
    try:
        return requests.get(f"{API_GATEWAY_URL}{path}", params=params, timeout=10)
    except requests.RequestException:
        return None


def gateway_post(path, payload):
    try:
        return requests.post(f"{API_GATEWAY_URL}{path}", json=payload, timeout=10)
    except requests.RequestException:
        return None


def gateway_put(path, payload):
    try:
        return requests.put(f"{API_GATEWAY_URL}{path}", json=payload, timeout=10)
    except requests.RequestException:
        return None


def normalize_food_image_url(raw_image_url, food_id=None):
    filename = "default.jpg"
    if raw_image_url:
        candidate = Path(str(raw_image_url)).name
        if candidate:
            filename = candidate

    if not (FOOD_IMAGE_DIR / filename).exists():
        id_filename = f"{food_id}.jpg" if food_id is not None else ""
        if id_filename and (FOOD_IMAGE_DIR / id_filename).exists():
            filename = id_filename
        else:
            filename = "default.jpg"

    if not (FOOD_IMAGE_DIR / filename).exists():
        filename = "default.jpg"

    return url_for("food_image", filename=filename)


def get_foods(filters=None):
    response = gateway_get("/api/foods", filters or {})
    if response and response.status_code == 200:
        foods = response.json()
        for food in foods:
            food["image_url"] = normalize_food_image_url(food.get("image_url"), food.get("id"))
        return foods, None
    return [], "Không tải được danh sách món ăn"


def get_categories():
    response = gateway_get("/api/foods/categories")
    if response and response.status_code == 200:
        return response.json()
    return []


def get_food_detail(food_id):
    response = gateway_get(f"/api/foods/{food_id}")
    if response and response.status_code == 200:
        food = response.json()
        food["image_url"] = normalize_food_image_url(food.get("image_url"), food.get("id"))
        return food, None
    return None, "Không tìm thấy món ăn"


def get_cart():
    return session.setdefault("cart", {})


def save_cart(cart):
    session["cart"] = cart
    session.modified = True


def cart_count():
    return sum(int(item.get("quantity", 0)) for item in get_cart().values())


def build_cart_view():
    foods, error = get_foods()
    if error:
        return [], 0, error

    food_map = {str(food["id"]): food for food in foods}
    cart = get_cart()
    items = []
    total = 0
    for food_id, item in cart.items():
        food = food_map.get(food_id)
        if not food:
            continue
        quantity = int(item.get("quantity", 1))
        line_total = float(food["price"]) * quantity
        total += line_total
        items.append(
            {
                "food_id": food["id"],
                "name": food["name"],
                "price": float(food["price"]),
                "quantity": quantity,
                "line_total": line_total,
                "image_url": food.get("image_url", "/static/images/foods/default.jpg"),
                "restaurant": food.get("restaurant", ""),
            }
        )
    return items, total, None


@app.context_processor
def inject_common():
    return {"cart_badge_count": cart_count()}


@app.route("/static/images/foods/<filename>")
def food_image(filename):
    target = FOOD_IMAGE_DIR / filename
    if target.exists():
        return send_from_directory(FOOD_IMAGE_DIR, filename)
    return send_from_directory(FOOD_IMAGE_DIR, "default.jpg")


@app.route("/images/foods/<filename>")
def food_image_proxy(filename):
    return food_image(filename)


@app.get("/")
def index():
    return redirect(url_for("home"))


@app.get("/home")
def home():
    filters = {
        "search": request.args.get("search", "").strip(),
        "category": request.args.get("category", "").strip(),
        "restaurant": request.args.get("restaurant", "").strip(),
        "sort": request.args.get("sort", "name"),
    }
    foods, error = get_foods(filters)
    categories = get_categories()
    return render_template(
        "home.html",
        foods=foods,
        error=error,
        categories=categories,
        selected_category=filters["category"],
        selected_sort=filters["sort"],
    )


@app.get("/food/<int:food_id>")
def food_detail(food_id: int):
    food, error = get_food_detail(food_id)
    if error:
        flash(error, "danger")
        return redirect(url_for("home"))

    related, _ = get_foods({"restaurant": food.get("restaurant", "")})
    related = [item for item in related if item["id"] != food_id][:8]
    return render_template("food_detail.html", food=food, related_foods=related)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        payload = {
            "full_name": request.form.get("full_name", "").strip(),
            "name": request.form.get("full_name", "").strip(),
            "username": request.form.get("username", "").strip(),
            "email": request.form.get("email", "").strip(),
            "password": request.form.get("password", "").strip(),
            "phone": request.form.get("phone", "").strip(),
            "address": request.form.get("address", "").strip(),
        }
        if not payload["username"] or not payload["password"]:
            flash("Vui lòng nhập tên đăng nhập và mật khẩu", "danger")
            return redirect(url_for("register"))

        response = gateway_post("/api/users/register", payload)
        if not response:
            flash("Không thể kết nối dịch vụ đăng ký", "danger")
            return redirect(url_for("register"))
        if response.status_code == 201:
            flash("Đăng ký thành công, vui lòng đăng nhập", "success")
            return redirect(url_for("login"))

        flash(response.json().get("error", "Đăng ký thất bại"), "danger")
        return redirect(url_for("register"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        payload = {
            "username": request.form.get("username", "").strip(),
            "password": request.form.get("password", "").strip(),
        }
        if not payload["username"] or not payload["password"]:
            flash("Vui lòng nhập tên đăng nhập và mật khẩu", "danger")
            return redirect(url_for("login"))

        response = gateway_post("/api/users/login", payload)
        if not response:
            flash("Không thể kết nối dịch vụ đăng nhập", "danger")
            return redirect(url_for("login"))
        if response.status_code != 200:
            flash("Đăng nhập thất bại", "danger")
            return redirect(url_for("login"))

        user = response.json()["user"]
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        flash("Đăng nhập thành công", "success")
        return redirect(url_for("home"))

    return render_template("login.html")


@app.get("/logout")
def logout():
    session.clear()
    flash("Đã đăng xuất thành công.", "success")
    return redirect(url_for("login"))


@app.route("/profile", methods=["GET"])
def profile():
    if "user_id" not in session:
        return redirect(url_for("login"))
    response = gateway_get(f"/api/users/{session['user_id']}/profile")
    if not response or response.status_code != 200:
        flash("Không tải được hồ sơ", "danger")
        return redirect(url_for("home"))
    return render_template("profile.html", profile=response.json())


@app.post("/profile/update")
def profile_update():
    if "user_id" not in session:
        return redirect(url_for("login"))
    payload = {
        "full_name": request.form.get("full_name", "").strip(),
        "phone": request.form.get("phone", "").strip(),
        "address": request.form.get("address", "").strip(),
    }
    response = gateway_put(f"/api/users/{session['user_id']}/profile", payload)
    if response and response.status_code == 200:
        flash("Cập nhật hồ sơ thành công", "success")
    else:
        flash("Cập nhật hồ sơ thất bại", "danger")
    return redirect(url_for("profile"))


@app.post("/profile/password")
def profile_password():
    if "user_id" not in session:
        return redirect(url_for("login"))
    payload = {
        "old_password": request.form.get("old_password", "").strip(),
        "new_password": request.form.get("new_password", "").strip(),
    }
    response = gateway_post(f"/api/users/{session['user_id']}/change-password", payload)
    if response and response.status_code == 200:
        flash("Đổi mật khẩu thành công", "success")
    else:
        message = response.json().get("error", "Đổi mật khẩu thất bại") if response else "Không thể kết nối dịch vụ"
        flash(message, "danger")
    return redirect(url_for("profile"))


@app.route("/cart/add", methods=["POST"])
def cart_add():
    data = request.get_json()
    if not data:
        return jsonify({"error": "invalid json"}), 400

    food_id = str(data.get("food_id"))
    name = data.get("name", "")
    price = float(data.get("price", 0))
    quantity = int(data.get("quantity", 1))

    cart = session.get("cart", {})
    if food_id in cart:
        cart[food_id]["quantity"] += quantity
    else:
        cart[food_id] = {"name": name, "price": price, "quantity": quantity}

    session["cart"] = cart
    session.modified = True

    return jsonify({"success": True, "cart_count": cart_count()})


@app.route("/cart", methods=["GET", "POST"])
def cart():
    cart_data = get_cart()
    if request.method == "POST":
        action = request.form.get("action")
        food_id = request.form.get("food_id", "")
        if action in {"increase", "decrease", "remove"} and food_id:
            key = str(food_id)
            current = int(cart_data.get(key, {}).get("quantity", 0))
            if action == "increase":
                cart_data[key]["quantity"] = current + 1
            elif action == "decrease":
                if current > 1:
                    cart_data[key]["quantity"] = current - 1
                else:
                    cart_data.pop(key, None)
            elif action == "remove":
                cart_data.pop(key, None)
            save_cart(cart_data)
            return redirect(url_for("cart"))

        if action == "checkout":
            if "user_id" not in session:
                flash("Vui lòng đăng nhập để thanh toán", "danger")
                return redirect(url_for("login"))

            note = request.form.get("note", "").strip()
            delivery_address = request.form.get("delivery_address", "").strip()
            items = [{"food_id": int(fid), "quantity": int(data["quantity"])} for fid, data in cart_data.items()]
            if not items:
                flash("Giỏ hàng đang trống", "danger")
                return redirect(url_for("cart"))

            response = gateway_post(
                "/api/cart/checkout",
                {"user_id": session["user_id"], "items": items, "note": note, "delivery_address": delivery_address},
            )
            if response and response.status_code == 201:
                flash("Thanh toán thành công", "success")
                save_cart({})
                return redirect(url_for("orders"))

            flash("Thanh toán thất bại", "danger")
            return redirect(url_for("cart"))

    cart_items, total_price, error = build_cart_view()
    if error:
        flash(error, "danger")
    return render_template("cart.html", cart_items=cart_items, total_price=total_price)


@app.route("/orders", methods=["GET"])
def orders():
    if "user_id" not in session:
        return redirect(url_for("login"))

    page = request.args.get("page", 1, type=int)
    response = gateway_get("/api/orders", {"user_id": session["user_id"], "page": page, "per_page": 8})
    if not response or response.status_code != 200:
        flash("Không tải được đơn hàng", "danger")
        return render_template("orders.html", orders=[], pagination={"current_page": 1, "pages": 1, "total": 0})

    data = response.json()
    return render_template(
        "orders.html",
        orders=data.get("orders", []),
        pagination={
            "current_page": data.get("current_page", 1),
            "pages": data.get("pages", 1),
            "total": data.get("total", 0),
        },
    )


@app.post("/orders/<int:order_id>/cancel")
def order_cancel(order_id: int):
    response = gateway_put(f"/api/orders/{order_id}/cancel", {})
    if response and response.status_code == 200:
        flash("Đã hủy đơn hàng", "success")
    else:
        message = response.json().get("error", "Không thể hủy đơn") if response else "Không thể kết nối dịch vụ"
        flash(message, "danger")
    return redirect(url_for("orders"))


@app.post("/orders/<int:order_id>/reorder")
def order_reorder(order_id: int):
    response = gateway_get(f"/api/orders/{order_id}")
    if not response or response.status_code != 200:
        flash("Không thể đặt lại đơn hàng", "danger")
        return redirect(url_for("orders"))

    order = response.json()
    cart = get_cart()
    for item in order.get("items", []):
        food_id = str(item.get("food_id") or item.get("product_id"))
        qty = int(item.get("quantity", 1))
        if food_id not in cart:
            cart[food_id] = {"quantity": 0}
        cart[food_id]["quantity"] += qty
    save_cart(cart)
    flash("Đã thêm món từ đơn cũ vào giỏ hàng", "success")
    return redirect(url_for("cart"))


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "frontend"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000, debug=False)
