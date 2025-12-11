import os
import json
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash, session
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId

# ======================================================
# 讀取 .env（本機） / Render 環境變數
# ======================================================
ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH, override=True)

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
IS_ON_RENDER = os.getenv("ON_RENDER") == "1"   # ★ 判斷是否在 Render

# ======================================================
# MongoDB 設定（Atlas）
# ======================================================
MONGO_URI = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI") or "mongodb://localhost:27017"
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "shop_demo")
MONGO_COLLECTION_NAME = os.getenv("MONGO_COLLECTION_NAME", "batch_products")

mongo_client = MongoClient(MONGO_URI)
mongo_db = mongo_client[MONGO_DB_NAME]
mongo_products = mongo_db[MONGO_COLLECTION_NAME]

# ======================================================
# Flask 初始化
# ======================================================
app = Flask(__name__)
app.secret_key = SECRET_KEY

# ======================================================
# 首頁 /home：給 navbar 用的統一入口
# ======================================================

@app.route("/")
def index():
    # 根據環境導向
    if IS_ON_RENDER:
        return redirect(url_for("admin_batch"))
    return redirect(url_for("home_mysql"))

# ★★★ 這個就是修正錯誤關鍵：給 base.html 用的 home endpoint ★★★
@app.route("/home")
def home():
    if IS_ON_RENDER:
        return redirect(url_for("admin_batch"))
    return redirect(url_for("home_mysql"))

# ======================================================
# ======= ★★★★★ MongoDB — 批次新增 + Multiple Delete ★★★★★
# ======================================================

@app.route("/admin_batch")
def admin_batch():
    docs = list(mongo_products.find())
    for d in docs:
        d["_id"] = str(d["_id"])
    return render_template("admin_batch.html", items=docs)

# 批次新增 insert_many
@app.route("/batch_insert", methods=["POST"])
def batch_insert():
    raw = request.form.get("json_data", "").strip()
    if not raw:
        flash("請貼上 JSON 資料", "warning")
        return redirect(url_for("admin_batch"))

    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            raise ValueError("JSON 必須是物件或物件陣列")

        result = mongo_products.insert_many(data)
        flash(f"成功新增 {len(result.inserted_ids)} 筆資料到 MongoDB", "success")

    except Exception as e:
        flash(f"JSON 錯誤：{e}", "danger")

    return redirect(url_for("admin_batch"))

# Multiple Delete：一次刪除多筆
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

# ======================================================================
# 🟦 以下是本機版（Local MySQL 版本）購物功能（Render 不會真的用到）
# ======================================================================

import pymysql
from contextlib import contextmanager
from decimal import Decimal

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

# =========== MySQL 商品頁（只有本機能用） ============
@app.route("/products")
def home_mysql():
    if IS_ON_RENDER:
        # Render 上沒有 MySQL，保險起見直接導回 MongoDB 頁
        return redirect(url_for("admin_batch"))

    with cursor() as cur:
        cur.execute("SELECT * FROM products ORDER BY id DESC")
        rows = cur.fetchall()

    return render_template("products.html", products=rows, cart_count=cart_count())

# ========== Local Cart（Render 不使用） ==========
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

@app.route("/cart")
def view_cart():
    if IS_ON_RENDER:
        return redirect(url_for("admin_batch"))
    return render_template("cart.html", items=cart_items(), total=sum(i["subtotal"] for i in cart_items()))

# ========== Local Add to Cart ==========
@app.route("/cart/add/<int:pid>", methods=["POST"])
def add_to_cart(pid):
    if IS_ON_RENDER:
        return redirect(url_for("admin_batch"))

    c = get_cart()
    c[str(pid)] = c.get(str(pid), 0) + 1
    session.modified = True
    flash("Added to cart", "success")
    return redirect(url_for("home_mysql"))

# ========== Local Delete Product（MySQL） ==========
@app.route("/delete_product/<int:pid>", methods=["POST"])
def delete_product(pid):
    if IS_ON_RENDER:
        return redirect(url_for("admin_batch"))

    with cursor() as cur:
        cur.execute("DELETE FROM products WHERE id=%s", (pid,))
    flash("商品已刪除", "success")
    return redirect(url_for("home_mysql"))

# ======================================================
# 啟動（Render 必須用 0.0.0.0）
# ======================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
