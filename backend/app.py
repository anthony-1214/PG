import os, datetime
from functools import wraps

import jwt, bcrypt
from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from bson import ObjectId

app = Flask(__name__)

# ===== Env (Render 用) =====
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("MONGODB_DB", "smartmeal")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")

CORS(app, resources={r"/*": {"origins": CORS_ORIGINS.split(",")}})

# ===== DB =====
client = MongoClient(MONGODB_URI)
db = client[DB_NAME]
users = db["users"]
menu_items = db["menu_items"]
orders = db["orders"]

# ===== Helpers =====
def now_iso():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def sign_token(payload, mins=60*24*7):
    exp = datetime.datetime.utcnow() + datetime.timedelta(minutes=mins)
    return jwt.encode({**payload, "exp": exp}, SECRET_KEY, algorithm="HS256")

def auth_required(fn):
    @wraps(fn)
    def w(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "Missing Bearer token"}), 401
        token = auth.split(" ", 1)[1].strip()
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        except Exception:
            return jsonify({"error": "Invalid/expired token"}), 401
        request.user = payload
        return fn(*args, **kwargs)
    return w

def vendor_required(fn):
    @wraps(fn)
    def w(*args, **kwargs):
        if request.user.get("role") not in ["vendor", "admin"]:
            return jsonify({"error": "Vendor/Admin only"}), 403
        return fn(*args, **kwargs)
    return w

@app.get("/")
def home():
    return {"status": "SmartMeal backend running", "time": now_iso()}

# ===== Seed menu (方便 demo) =====
@app.post("/seed/menu")
def seed_menu():
    if menu_items.count_documents({}) > 0:
        return {"ok": True, "message": "already seeded", "count": menu_items.count_documents({})}
    sample = [
        {"name": "豚骨拉麵", "price": 180, "category": "food", "is_available": True, "created_at": now_iso()},
        {"name": "醬油拉麵", "price": 160, "category": "food", "is_available": True, "created_at": now_iso()},
        {"name": "可樂", "price": 35, "category": "drink", "is_available": True, "created_at": now_iso()},
        {"name": "烏龍茶", "price": 30, "category": "drink", "is_available": True, "created_at": now_iso()},
    ]
    menu_items.insert_many(sample)
    return {"ok": True, "count": menu_items.count_documents({})}

# ===== Auth =====
@app.post("/register")
def register():
    d = request.get_json(force=True)
    name = (d.get("name") or "").strip()
    email = (d.get("email") or "").strip().lower()
    password = d.get("password") or ""
    role = (d.get("role") or "student").strip().lower()

    if not name or not email or not password:
        return {"error": "name/email/password required"}, 400
    if role not in ["student", "vendor", "admin"]:
        return {"error": "role must be student/vendor/admin"}, 400
    if users.find_one({"email": email}):
        return {"error": "Email already registered"}, 409

    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    res = users.insert_one({"name": name, "email": email, "pw": pw_hash, "role": role, "created_at": now_iso()})
    token = sign_token({"user_id": str(res.inserted_id), "role": role, "name": name, "email": email})
    return {"token": token, "user": {"_id": str(res.inserted_id), "name": name, "email": email, "role": role}}

@app.post("/login")
def login():
    d = request.get_json(force=True)
    email = (d.get("email") or "").strip().lower()
    password = d.get("password") or ""
    u = users.find_one({"email": email})
    if not u:
        return {"error": "Invalid email or password"}, 401
    if not bcrypt.checkpw(password.encode(), u["pw"].encode()):
        return {"error": "Invalid email or password"}, 401
    token = sign_token({"user_id": str(u["_id"]), "role": u["role"], "name": u["name"], "email": u["email"]})
    return {"token": token, "user": {"_id": str(u["_id"]), "name": u["name"], "email": u["email"], "role": u["role"]}}

# ===== Menu =====
@app.get("/menu")
def get_menu():
    items = list(menu_items.find({"is_available": True}).sort("category", 1))
    for it in items:
        it["_id"] = str(it["_id"])
    return {"menu": items}

# ===== Orders =====
# 建立訂單：items 格式建議 [{menu_item_id, qty}]
@app.post("/order")
@auth_required
def create_order():
    d = request.get_json(force=True)
    items = d.get("items") or []
    if not isinstance(items, list) or len(items) == 0:
        return {"error": "items required"}, 400

    built = []
    total = 0
    for row in items:
        mid = row.get("menu_item_id") or row.get("_id") or row.get("id")
        qty = int(row.get("qty") or 1)
        mi = menu_items.find_one({"_id": ObjectId(mid)})
        if not mi:
            return {"error": f"menu item not found: {mid}"}, 404
        subtotal = int(mi["price"]) * qty
        total += subtotal
        built.append({"menu_item_id": str(mi["_id"]), "name": mi["name"], "unit_price": int(mi["price"]), "qty": qty, "subtotal": subtotal})

    doc = {
        "user_id": request.user["user_id"],
        "status": "PREPARING",
        "items": built,
        "total_price": total,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    res = orders.insert_one(doc)
    return {"ok": True, "order_id": str(res.inserted_id), "total_price": total, "status": "PREPARING"}

# 學生看自己的訂單
@app.get("/orders/my")
@auth_required
def my_orders():
    docs = list(orders.find({"user_id": request.user["user_id"]}).sort("created_at", -1))
    for o in docs:
        o["_id"] = str(o["_id"])
    return {"orders": docs}

# 店家看全部訂單
@app.get("/orders")
@auth_required
@vendor_required
def all_orders():
    docs = list(orders.find({}).sort("created_at", -1).limit(100))
    for o in docs:
        o["_id"] = str(o["_id"])
    return docs  # 讓你 vendor.html 的 data.map() 直接吃

# 店家改狀態
@app.post("/order/status")
@auth_required
@vendor_required
def set_status():
    d = request.get_json(force=True)
    oid = d.get("id")
    status = (d.get("status") or "").upper()
    if status not in ["PREPARING", "READY", "COMPLETED", "CANCELLED"]:
        return {"error": "Invalid status"}, 400
    r = orders.update_one({"_id": ObjectId(oid)}, {"$set": {"status": status, "updated_at": now_iso()}})
    if r.matched_count == 0:
        return {"error": "Order not found"}, 404
    return {"ok": True, "id": oid, "status": status}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)