import os
import json
from pathlib import Path
from decimal import Decimal
from contextlib import contextmanager

from flask import (
    Flask, render_template, request,
    redirect, url_for, flash, session
)
from dotenv import load_dotenv
import pymysql

from pymongo import MongoClient
from bson import ObjectId

# =========================
# 環境變數設定
# =========================
ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH, override=True)

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")

# --- MySQL 設定（本機用，Render 目前沒接 MySQL） ---
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD") or ""
DB_NAME = os.getenv("DB_NAME", "shop_demo")
DB_SOCKET = (os.getenv("DB_SOCKET") or "").strip()

# --- MongoDB 設定（作業 3 + 4 用） ---
MONGO_URI = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI") or "mongodb://localhost:27017"
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "shop_demo")
MONGO_COLLECTION_NAME = os.getenv("MONGO_COLLECTION_NAME", "batch_products")

mongo_client = MongoClient(MONGO_URI)
mongo_db = mongo_client[MONGO_DB_NAME]
mongo_products = mongo_db[MONGO_COLLECTION_NAME]

app = Flask(__name__)
app.secret_key = SECRET_KEY

# =========================
# MySQL 連線 & Schema
# =========================
def _connect_base(with_db: bool = False):
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
def cursor(with_db: bool = True):
    conn = _connect_base(with_db=with_db)
    try:
        with conn.cursor() as cur:
            yield cur
    finally:
        conn.close()


def ensure_schema():
    """本機開發用：建立 MySQL 資料表"""
    with _connect_base(with_db=False) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS {DB_NAME} DEFAULT CHARACTER SET utf8mb4;"
            )

    with cursor(with_db=True) as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(120) NOT NULL,
                price DECIMAL(10,2) NOT NULL,
                size VARCHAR(20) DEFAULT 'F',
                stock INT NOT NULL DEFAULT 0,
                image_url VARCHAR(255) DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INT AUTO_INCREMENT PRIMARY KEY,
                customer_name VARCHAR(120),
                customer_email VARCHAR(120),
                total DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS order_items (
                id INT AUTO_INCREMENT PRIMARY KEY,
                order_id INT NOT NULL,
                product_id INT NOT NULL,
                qty INT NOT NULL,
                price DECIMAL(10,2) NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
                FOREIGN KEY (product_id) REFERENCES products(id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        )

# =========================
# 購物車邏輯（MySQL）
# =========================
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
        cur.execute(
            f"SELECT id, name, price, size, stock, image_url FROM products WHERE id IN ({placeholders})",
            ids,
        )
        products = {row["id"]: row for row in cur.fetchall()}

    for pid_str, qty in cart.items():
        pid = int(pid_str)
        prod = products.get(pid)
        if not prod:
            continue
        subtotal = Decimal(prod["price"]) * qty
        items.append(
            dict(
                id=pid,
                name=prod["name"],
                price=Decimal(prod["price"]),
                size=prod["size"],
                stock=prod["stock"],
                image_url=prod["image_url"],
                qty=qty,
                subtotal=subtotal,
            )
        )
    return items


def cart_total():
    return sum((it["subtotal"] for it in cart_items()), Decimal("0"))

# =========================
# 一般商品 / 購物車 / 訂單（MySQL）
# =========================
@app.route("/")
def home():
    with cursor() as cur:
        cur.execute(
            "SELECT id, name, price, size, stock, image_url FROM products ORDER BY id DESC"
        )
        products = cur.fetchall()
    return render_template(
        "products.html", products=products, cart_count=cart_count()
    )


@app.route("/admin/products/new", methods=["GET", "POST"])
def admin_new_product():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        price = request.form.get("price", "0").strip()
        size = request.form.get("size", "F").strip()
        stock = int(request.form.get("stock", "0"))
        image_url = request.form.get("image_url", "").strip() or None

        if not name:
            flash("Name is required", "warning")
            return redirect(url_for("admin_new_product"))

        with cursor() as cur:
            cur.execute(
                "INSERT INTO products (name, price, size, stock, image_url) VALUES (%s,%s,%s,%s,%s)",
                (name, price, size, stock, image_url),
            )
        flash("Product created", "success")
        return redirect(url_for("home"))

    return render_template("admin_new_product.html", cart_count=cart_count())


@app.route("/delete_product/<int:pid>", methods=["POST"])
def delete_product(pid):
    with cursor() as cur:
        # 同時把 order_items 相關紀錄刪掉
        cur.execute("DELETE FROM order_items WHERE product_id = %s", (pid,))
        cur.execute("DELETE FROM products WHERE id = %s", (pid,))
    flash("Product and related order items deleted successfully", "success")
    return redirect(url_for("home"))


@app.route("/cart")
def view_cart():
    items = cart_items()
    total = cart_total()
    return render_template("cart.html", items=items, total=total, cart_count=cart_count())


@app.route("/cart/add/<int:pid>", methods=["POST"])
def add_to_cart(pid):
    cart = get_cart()
    cart[str(pid)] = cart.get(str(pid), 0) + 1
    session.modified = True
    flash("Added to cart", "success")
    return redirect(url_for("home"))


@app.route("/cart/remove/<int:pid>", methods=["POST"])
def remove_from_cart(pid):
    cart = get_cart()
    cart.pop(str(pid), None)
    session.modified = True
    return redirect(url_for("view_cart"))


@app.route("/cart/update", methods=["POST"])
def update_cart():
    cart = get_cart()
    for key, value in request.form.items():
        if not key.startswith("qty_"):
            continue
        pid = key[4:]
        try:
            qty = max(0, int(value))
        except Exception:
            qty = 0
        if qty == 0:
            cart.pop(pid, None)
        else:
            cart[pid] = qty
    session.modified = True
    return redirect(url_for("view_cart"))


@app.route("/checkout", methods=["POST"])
def checkout():
    items = cart_items()
    if not items:
        flash("Cart is empty", "warning")
        return redirect(url_for("home"))

    name = request.form.get("customer_name", "Guest")
    email = request.form.get("customer_email", "")

    total = cart_total()

    with cursor() as cur:
        cur.execute(
            "INSERT INTO orders (customer_name, customer_email, total) VALUES (%s,%s,%s)",
            (name, email, str(total)),
        )
        cur.execute("SELECT LAST_INSERT_ID() AS id")
        order_id = cur.fetchone()["id"]

        for it in items:
            cur.execute(
                "INSERT INTO order_items (order_id, product_id, qty, price) VALUES (%s,%s,%s,%s)",
                (order_id, it["id"], it["qty"], str(it["price"])),
            )
            cur.execute(
                "UPDATE products SET stock = GREATEST(stock - %s, 0) WHERE id=%s",
                (it["qty"], it["id"]),
            )

    session["cart"] = {}
    flash(f"Order #{order_id} created. Thank you!", "success")
    return redirect(url_for("home"))


@app.route("/orders")
def orders():
    with cursor() as cur:
        cur.execute(
            "SELECT id, customer_name, customer_email, total, created_at FROM orders ORDER BY id DESC"
        )
        rows = cur.fetchall()
    return render_template("orders.html", orders=rows, cart_count=cart_count())

# =========================
# MongoDB：批次新增 + 批次刪除
# =========================
@app.route("/admin_batch")
def admin_batch():
    docs = list(mongo_products.find())
    # _id 轉字串，模板好顯示
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
    ids = request.form.getlist("delete_ids")
    if not ids:
        flash("請先勾選要刪除的商品", "warning")
        return redirect(url_for("admin_batch"))

    object_ids = []
    for _id in ids:
        try:
            object_ids.append(ObjectId(_id))
        except Exception:
            # 有人亂改表單就略過
            continue

    if not object_ids:
        flash("沒有有效的商品可以刪除", "warning")
        return redirect(url_for("admin_batch"))

    result = mongo_products.delete_many({"_id": {"$in": object_ids}})
    flash(f"成功刪除 {result.deleted_count} 筆 MongoDB 商品", "success")
    return redirect(url_for("admin_batch"))

# =========================
# 啟動
# =========================
if __name__ == "__main__":
    # Render 上不要跑 MySQL schema（你有設定 ON_RENDER=1）
    if os.getenv("ON_RENDER") != "1":
        ensure_schema()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
