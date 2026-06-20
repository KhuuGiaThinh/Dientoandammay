import os
from datetime import datetime

import requests
from flask import Flask, Response, jsonify, request

app = Flask(__name__)

ROUTES = {
    "/api/users": os.getenv("USER_SERVICE_URL", "http://user-service:5001"),
    "/api/foods": os.getenv("PRODUCT_ORDER_SERVICE_URL", "http://product-order-service:5002"),
    "/api/products": os.getenv("PRODUCT_ORDER_SERVICE_URL", "http://product-order-service:5002"),
    "/api/orders": os.getenv("PRODUCT_ORDER_SERVICE_URL", "http://product-order-service:5002"),
    "/api/cart": os.getenv("PRODUCT_ORDER_SERVICE_URL", "http://product-order-service:5002"),
}


def forward_request(base_url: str, path: str):
    target_url = f"{base_url}/{path}" if path else base_url
    try:
        response = requests.request(
            method=request.method,
            url=target_url,
            params=request.args,
            json=request.get_json(silent=True),
            timeout=10,
        )
    except requests.RequestException:
        return jsonify({"error": "Service unavailable"}), 503

    excluded = {"content-encoding", "content-length", "transfer-encoding", "connection"}
    headers = [(k, v) for (k, v) in response.raw.headers.items() if k.lower() not in excluded]
    return Response(response.content, response.status_code, headers)


@app.route("/api/users", defaults={"path": ""}, methods=["GET", "POST", "PUT", "DELETE"])
@app.route("/api/users/<path:path>", methods=["GET", "POST", "PUT", "DELETE"])
def users_proxy(path: str):
    target_path = path
    if path and path.split("/")[0].isdigit():
        target_path = f"users/{path}"
    return forward_request(ROUTES["/api/users"], target_path)


@app.route("/api/foods", defaults={"path": ""}, methods=["GET", "POST", "PUT", "DELETE"])
@app.route("/api/foods/<path:path>", methods=["GET", "POST", "PUT", "DELETE"])
def foods_proxy(path: str):
    target_path = f"foods/{path}" if path else "foods"
    return forward_request(ROUTES["/api/foods"], target_path)


@app.route("/api/products", defaults={"path": ""}, methods=["GET", "POST", "PUT", "DELETE"])
@app.route("/api/products/<path:path>", methods=["GET", "POST", "PUT", "DELETE"])
def products_proxy(path: str):
    target_path = f"foods/{path}" if path else "foods"
    return forward_request(ROUTES["/api/products"], target_path)


@app.route("/api/orders", defaults={"path": ""}, methods=["GET", "POST", "PUT", "DELETE"])
@app.route("/api/orders/<path:path>", methods=["GET", "POST", "PUT", "DELETE"])
def orders_proxy(path: str):
    target_path = f"orders/{path}" if path else "orders"
    return forward_request(ROUTES["/api/orders"], target_path)


@app.route("/api/cart", defaults={"path": ""}, methods=["GET", "POST", "PUT", "DELETE"])
@app.route("/api/cart/<path:path>", methods=["GET", "POST", "PUT", "DELETE"])
def cart_proxy(path: str):
    target_path = f"cart/{path}" if path else "cart"
    return forward_request(ROUTES["/api/cart"], target_path)


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "api-gateway", "timestamp": datetime.utcnow().isoformat()})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
