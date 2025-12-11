import os
import json
from pathlib import Path

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

import pymysql
from contextlib import contextmanager
from decimal import Decimal

# ======================================================
# 讀取 .env（本機） / Render 環境變數
# ======================================================
ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH, override=True)

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
IS_ON_RENDER = os.getenv("ON_RENDER") == "1"   # 在 Render 上就設成 1

# ======================================================
# MongoDB 設定（Atlas / Local）
# ======================================================
MONGO_URI = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI") or "mongodb://localhost:27017"
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "shop_demo")
MONGO_COLLECTION_NAME = os.getenv("MONGO_COLLECTION_NAME", "batch_products")

mongo_client = MongoClient(MONGO_URI)
mongo_db = mongo_client[MONGO_DB_NAME]
mongo_products = mongo_db[MONGO_COLLECTION_NAME]

# ======================================================
# MySQL 設定（本機用，不在 Render 連）
# ======================================================
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "shop_demo")
DB_SOCKET = (os.getenv("DB_SOCKET") or "").strip()


def _connect_base(with_db=False):
    common = dict(
        user=DB_USER,
        password=DB_PASSWORD,
        charset="utf8mb4",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )
    if with_db:
        common["database"] = DB_NAME
    if DB_SOCKET:
        return pymysql.connect(unix_socket=DB_SOCKET, **common)
    else:
        return pymysql.connect(host=DB_HOST, port=DB_PORT, **common)


@contextmanager
def cursor(with_db=True):
    conn = _connect_base(with_db=with_db)
    try:
        with conn.cursor() as cur:
            yield cur
    finally:
        conn.close()


# ======================================================
# Flask 初始化
# ======================================================
app = Flask(__name__)
app.secret_key = SECRET_KEY

# ======================================================
# 首頁 /home：navbar 用的統一入口
# ======================================================

@app.route("/")
def index():
    # Render：直接看 MongoDB 批次頁
    if IS_ON_RENDER:
        return redirect(url_for("admin_batch"))
    # 本機：看 MySQL 商品列表
    return redirect(url_for("home_mysql"))


@app.route("/home")
def home():
    if IS_ON_RENDER:
        return redirect(url_for("admin_batch"))
    return redirect(url_for("home_mysql"))


# ======================================================
# ======= MongoDB — 批次新增 + Multiple Delete =======
# ======================================================

@app.route("/admin_batch")
def admin_batch():
    docs = list(mongo_products.find())
    for d in docs:
        d["_id"] = str(d["_id"])
    return render_template("admin_batch.html", items=docs)


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


@app.route("/batch_delete", methods=["POST"])
def batch_delete():
    ids = request.form.getlist("selected_ids")
    if not ids:
        flash("請至少勾選一筆資料", "warning")
        return redirect(url_for("admin_batch"))

    object_ids = [ObjectId(x) for x in ids]
    result = mongo_products.delete_many({"_id": {"$in": object_ids}})
    flash(f"成功刪除 {result.deleted_count} 筆商品", "success")
    return redirect(url_for("admin_batch"))


# ======================================================
# ======= 本機 MySQL 商城功能（Render 只保留 endpoint）=======
# ======================================================

def get_cart():
    return session.setdefault("cart", {})


def cart_count():
    return sum(get_cart().values())


def cart_items():
    items = []
    cart = get_cart()
    if not cart:
        return items

    ids = list(map(int, cart.keys()))
    placeholders = ",".join(["%s"] * len(ids))

    with cursor() as cur:
        cur.execute(f"SELECT * FROM products WHERE id IN ({placeholders})", ids)
        products = {p["id"]: p for p in cur.fetchall()}

    for pid_str, qty in cart.items():
        pid = int(pid_str)
        p = products.get(pid)
        if p:
            subtotal = Decimal(p["price"]) * qty
            items.append({**p, "qty": qty, "subtotal": subtotal})

    return items


@app.route("/products")
def home_mysql():
    # Render 上沒有 MySQL：避免連線錯誤，直接導回 MongoDB demo
    if IS_ON_RENDER:
        return redirect(url_for("admin_batch"))

    with cursor() as cur:
        cur.execute("SELECT * FROM products ORDER BY id DESC")
        rows = cur.fetchall()

    return render_template("products.html", products=rows, cart_count=cart_count())


@app.route("/cart")
def view_cart():
    if IS_ON_RENDER:
        return redirect(url_for("admin_batch"))

    items = cart_items()
    total = sum(i["subtotal"] for i in items)
    return render_template("cart.html", items=items, total=total, cart_count=cart_count())


@app.route("/cart/add/<int:pid>", methods=["POST"])
def add_to_cart(pid):
    if IS_ON_RENDER:
        return redirect(url_for("admin_batch"))

    c = get_cart()
    c[str(pid)] = c.get(str(pid), 0) + 1
    session.modified = True
    flash("Added to cart", "success")
    return redirect(url_for("home_mysql"))


@app.route("/delete_product/<int:pid>", methods=["POST"])
def delete_product(pid):
    if IS_ON_RENDER:
        return redirect(url_for("admin_batch"))

    with cursor() as cur:
        cur.execute("DELETE FROM products WHERE id=%s", (pid,))
    flash("商品已刪除", "success")
    return redirect(url_for("home_mysql"))


# ★★★ 補上 navbar 用的「新增商品」 endpoint ★★★
@app.route("/admin/products/new", methods=["GET", "POST"])
def admin_new_product():
    # Render：不連 MySQL，只給提示訊息然後導回 MongoDB 頁面
    if IS_ON_RENDER:
        flash("線上 Demo 只開啟 MongoDB 批次功能，新增商品請在本機 MySQL 版操作。", "info")
        return redirect(url_for("admin_batch"))

    # 本機：真的顯示 / 處理新增商品表單
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        price = request.form.get("price", "0").strip()
        size = request.form.get("size", "F").strip()
        stock = int(request.form.get("stock", "0") or 0)
        image_url = request.form.get("image_url", "").strip() or None

        if not name:
            flash("Name is required", "warning")
            return redirect(url_for("admin_new_product"))

        with cursor() as cur:
            cur.execute(
                "INSERT INTO products (name, price, size, stock, image_url) "
                "VALUES (%s, %s, %s, %s, %s)",
                (name, price, size, stock, image_url),
            )

        flash("Product created", "success")
        return redirect(url_for("home_mysql"))

    return render_template("admin_new_product.html", cart_count=cart_count())


@app.route("/orders")
def orders():
    if IS_ON_RENDER:
        # Render 上不查 MySQL
        return redirect(url_for("admin_batch"))

    with cursor() as cur:
        cur.execute(
            "SELECT id, customer_name, customer_email, total, created_at "
            "FROM orders ORDER BY id DESC"
        )
        rows = cur.fetchall()

    return render_template("orders.html", orders=rows, cart_count=cart_count())


# ======================================================
# 啟動（Render 必須用 0.0.0.0）
# ======================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
