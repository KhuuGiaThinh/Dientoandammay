from datetime import datetime

from flask import Flask, jsonify, request
from sqlalchemy import text

from database import configure_database, db, init_db_with_retry

app = Flask(__name__)
configure_database(app)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True)
    password = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(200))
    phone = db.Column(db.String(20))
    address = db.Column(db.Text)
    avatar = db.Column(db.String(200), default="default-avatar.jpg")

    def to_public_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "name": self.full_name or self.username,
            "full_name": self.full_name,
            "email": self.email,
            "phone": self.phone,
            "address": self.address,
            "avatar": self.avatar,
        }


SAMPLE_USERS = [
    {"username": "nguyenvan_a", "email": "nguyenvana@gmail.com", "password": "123456", "full_name": "Nguyễn Văn A", "phone": "0901234567", "address": "123 Lê Lợi, Q1, TP.HCM"},
    {"username": "tranthib", "email": "tranthib@gmail.com", "password": "123456", "full_name": "Trần Thị B", "phone": "0912345678", "address": "456 Nguyễn Huệ, Q1, TP.HCM"},
    {"username": "lehongc", "email": "lehongc@gmail.com", "password": "123456", "full_name": "Lê Hồng C", "phone": "0923456789", "address": "789 Đinh Tiên Hoàng, Bình Thạnh"},
    {"username": "phamthi_d", "email": "phamthid@gmail.com", "password": "123456", "full_name": "Phạm Thị D", "phone": "0934567890", "address": "321 Cách Mạng Tháng 8, Q3"},
    {"username": "admin", "email": "admin@foodapp.vn", "password": "admin123", "full_name": "Quản Trị Viên", "phone": "0800000000", "address": "1 Công Trường Mê Linh, Q1"},
]


def seed_data():
    if db.session.execute(db.select(User.id)).first():
        return

    for sample in SAMPLE_USERS:
        db.session.add(
            User(
                username=sample["username"],
                email=sample["email"],
                password=sample["password"],
                full_name=sample["full_name"],
                phone=sample["phone"],
                address=sample["address"],
            )
        )
    db.session.commit()


@app.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    email = data.get("email", "").strip()
    full_name = data.get("full_name", "").strip() or data.get("name", "").strip() or username
    phone = data.get("phone", "").strip()
    address = data.get("address", "").strip()

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    existing_user = db.session.execute(db.select(User).where(User.username == username)).scalar_one_or_none()
    if existing_user:
        return jsonify({"error": "Username already exists"}), 409

    if email:
        existing_email = db.session.execute(db.select(User).where(User.email == email)).scalar_one_or_none()
        if existing_email:
            return jsonify({"error": "Email already exists"}), 409

    user = User(
        username=username,
        password=password,
        email=email or None,
        full_name=full_name,
        phone=phone or None,
        address=address or None,
    )
    db.session.add(user)
    db.session.commit()
    return jsonify({"message": "Registered successfully", "user_id": user.id}), 201


@app.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    user = db.session.execute(db.select(User).where(User.username == username)).scalar_one_or_none()
    if not user or user.password != password:
        return jsonify({"error": "Invalid credentials"}), 401

    return jsonify({"message": "Login successful", "user": user.to_public_dict()})


@app.get("/users/<int:user_id>")
def get_user(user_id: int):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(user.to_public_dict())


@app.get("/users/<int:user_id>/profile")
def get_profile(user_id: int):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(user.to_public_dict())


@app.put("/users/<int:user_id>/profile")
def update_profile(user_id: int):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json(silent=True) or {}
    if "full_name" in data:
        user.full_name = str(data["full_name"]).strip()
    if "phone" in data:
        user.phone = str(data["phone"]).strip()
    if "address" in data:
        user.address = str(data["address"]).strip()
    if "avatar" in data:
        user.avatar = str(data["avatar"]).strip()

    db.session.commit()
    return jsonify({"message": "Profile updated", "user": user.to_public_dict()})


@app.post("/users/<int:user_id>/change-password")
def change_password(user_id: int):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json(silent=True) or {}
    old_password = data.get("old_password", "").strip()
    new_password = data.get("new_password", "").strip()
    if not old_password or not new_password:
        return jsonify({"error": "old_password and new_password are required"}), 400
    if user.password != old_password:
        return jsonify({"error": "Old password is incorrect"}), 400

    user.password = new_password
    db.session.commit()
    return jsonify({"message": "Password changed successfully"})


@app.get("/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as exc:  # pragma: no cover
        db_status = str(exc)

    status = "ok" if db_status == "ok" else "degraded"
    code = 200 if status == "ok" else 503
    return jsonify({"status": status, "service": "user-service", "database": db_status, "timestamp": datetime.utcnow().isoformat()}), code


if __name__ == "__main__":
    init_db_with_retry(app)
    with app.app_context():
        seed_data()
    app.run(host="0.0.0.0", port=5001, debug=False)
