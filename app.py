import os
import json
from pathlib import Path
from decimal import Decimal
from datetime import datetime

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
)
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId

# ==========================
#   環境變數 & Mongo 連線
# ==========================
ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH, override=True)

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")

# MongoDB 設定（Atlas）
MONGO_URI = (
    os.getenv("MONGO_URI")
    or os.getenv("MONGODB_URI")
    or "mongodb://localhost:27017"
)
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "shop_demo")
MONGO_COLLECTION_NAME = os.getenv("MONGO_COLLECTION_NAME", "batch_products")

# 建立 MongoDB 連線
mongo_client = MongoClient(MONGO_URI)
mongo_db = mongo_client[MONGO_DB_NAME]
mongo_products = mongo_db[MONGO_COLLECTION_NAME]  # 商品集合
mongo_orders = mongo_db["orders"]                 # 訂單集合

app = Flask(__name__)
app.secret_key = SECRET_KEY


# ==========================
#   小工具：購物車 & 轉換
# ==========================
def get_cart():
    """session 裡的購物車：{ product_id(str): qty(int) }"""
    return session.setdefault("cart", {})


def cart_count():
    return sum(get_cart().values())


def mongo_doc_to_product(doc):
    """把 Mongo 的商品 doc 轉成模板好用的 dict"""
    return {
        "id": str(doc["_id"]),
        "name": doc.get("name", ""),
        "price": Decimal(str(doc.get("price", 0))),
        "size": doc.get("size", "F"),
        "stock": int(doc.get("stock", 0)),
        "image_url": doc.get("image_url") or "",
    }


def cart_items():
    """把購物車內容轉成 [ {id,name,price,qty,subtotal,...}, ... ]"""
    c = get_cart()
    if not c:
        return []

    ids = list(c.keys())
    obj_ids = [ObjectId(pid) for pid in ids]

    docs = list(mongo_products.find({"_id": {"$in": obj_ids}}))
    products_map = {str(d["_id"]): mongo_doc_to_product(d) for d in docs}

    items = []
    for pid, qty in c.items():
        prod = products_map.get(pid)
        if not prod:
            continue
        qty = int(qty)
        subtotal = prod["price"] * qty
        row = prod.copy()
        row["qty"] = qty
        row["subtotal"] = subtotal
        items.append(row)
    return items


def cart_total():
    return sum((it["subtotal"] for it in cart_items()), Decimal("0"))


# ==========================
#   首頁：Products 清單
# ==========================
@app.route("/")
def home():
    docs = list(mongo_products.find().sort("_id", -1))
    products = [mongo_doc_to_product(d) for d in docs]
    return render_template("products.html", products=products, cart_count=cart_count())


# ==========================
#   單筆新增商品（表單）
# ==========================
@app.route("/admin/products/new", methods=["GET", "POST"])
def admin_new_product():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        price = request.form.get("price", "0").strip()
        size = request.form.get("size", "F").strip()
        stock = request.form.get("stock", "0").strip()
        image_url = request.form.get("image_url", "").strip() or None

        if not name:
            flash("Name is required", "warning")
            return redirect(url_for("admin_new_product"))

        try:
            price_val = float(price)
            stock_val = int(stock)
        except ValueError:
            flash("價格或庫存格式錯誤", "warning")
            return redirect(url_for("admin_new_product"))

        mongo_products.insert_one(
            {
                "name": name,
                "price": price_val,
                "size": size,
                "stock": stock_val,
                "image_url": image_url,
            }
        )
        flash("Product created", "success")
        return redirect(url_for("home"))

    return render_template("admin_new_product.html", cart_count=cart_count())


# ==========================
#   刪除商品
# ==========================
@app.route("/delete_product/<pid>", methods=["POST"])
def delete_product(pid):
    try:
        mongo_products.delete_one({"_id": ObjectId(pid)})
        flash("Product deleted", "success")
    except Exception as e:
        flash(f"刪除失敗：{e}", "danger")
    return redirect(url_for("home"))


# ==========================
#   購物車相關
# ==========================
@app.route("/cart")
def view_cart():
    items = cart_items()
    total = cart_total()
    return render_template(
        "cart.html", items=items, total=total, cart_count=cart_count()
    )


@app.route("/cart/add/<pid>", methods=["POST"])
def add_to_cart(pid):
    c = get_cart()
    c[pid] = c.get(pid, 0) + 1
    session.modified = True
    flash("Added to cart", "success")
    return redirect(url_for("home"))


@app.route("/cart/remove/<pid>", methods=["POST"])
def remove_from_cart(pid):
    c = get_cart()
    c.pop(pid, None)
    session.modified = True
    return redirect(url_for("view_cart"))


@app.route("/cart/update", methods=["POST"])
def update_cart():
    c = get_cart()
    for key, value in request.form.items():
        if key.startswith("qty_"):
            pid = key[4:]
            try:
                qty = max(0, int(value))
            except ValueError:
                qty = 0
            if qty == 0:
                c.pop(pid, None)
            else:
                c[pid] = qty
    session.modified = True
    return redirect(url_for("view_cart"))


# ==========================
#   結帳 & 訂單列表（Mongo）
# ==========================
@app.route("/checkout", methods=["POST"])
def checkout():
    items = cart_items()
    if not items:
        flash("Cart is empty", "warning")
        return redirect(url_for("home"))

    name = request.form.get("customer_name", "Guest").strip()
    email = request.form.get("customer_email", "").strip()
    total = cart_total()

    order_doc = {
        "customer_name": name,
        "customer_email": email,
        "total": float(total),
        "created_at": datetime.utcnow(),
        "items": [
            {
                "product_id": it["id"],
                "name": it["name"],
                "qty": it["qty"],
                "price": float(it["price"]),
            }
            for it in items
        ],
    }

    result = mongo_orders.insert_one(order_doc)
    session["cart"] = {}
    flash(f"Order #{str(result.inserted_id)[:8]} created. Thank you!", "success")
    return redirect(url_for("home"))


@app.route("/orders")
def orders():
    docs = list(mongo_orders.find().sort("created_at", -1))
    orders = []
    for d in docs:
        orders.append(
            {
                "id": str(d["_id"]),
                "customer_name": d.get("customer_name", ""),
                "customer_email": d.get("customer_email", ""),
                "total": d.get("total", 0),
                "created_at": d.get("created_at"),
            }
        )
    return render_template("orders.html", orders=orders, cart_count=cart_count())


# ==========================
#   MongoDB 批次新增 insert_many
# ==========================
@app.route("/admin_batch")
def admin_batch():
    docs = list(mongo_products.find().sort("_id", -1))
    for d in docs:
        d["_id"] = str(d["_id"])
    return render_template("admin_batch.html", items=docs, cart_count=cart_count())


@app.route("/batch_insert", methods=["POST"])
def batch_insert():
    raw = request.form.get("json_data", "").strip()
    if not raw:
        flash("請貼上 JSON 資料", "warning")
        return redirect(url_for("admin_batch"))

    try:
        data = json.loads(raw)

        # 允許單一物件或陣列
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            raise ValueError("JSON 必須是物件或物件陣列")

        for doc in data:
            if not isinstance(doc, dict):
                raise ValueError("每筆資料都必須是 JSON 物件")

        result = mongo_products.insert_many(data)
        flash(f"成功批次新增 {len(result.inserted_ids)} 筆商品到 MongoDB", "success")
    except Exception as e:
        flash(f"JSON 或資料格式錯誤：{e}", "danger")

    return redirect(url_for("admin_batch"))


# ==========================
#   啟動（本機 / Render）
# ==========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
