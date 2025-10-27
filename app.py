import os
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash, session
import pymysql
from contextlib import contextmanager
from dotenv import load_dotenv
from decimal import Decimal

ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH, override=True)

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD") or ""
DB_NAME = os.getenv("DB_NAME", "shop_demo")
DB_SOCKET = (os.getenv("DB_SOCKET") or "").strip()
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")

app = Flask(__name__)
app.secret_key = SECRET_KEY

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

from contextlib import contextmanager
@contextmanager
def cursor(with_db=True):
    conn = _connect_base(with_db=with_db)
    try:
        with conn.cursor() as cur:
            yield cur
    finally:
        conn.close()

def ensure_schema():
    with _connect_base(with_db=False) as conn:
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME} DEFAULT CHARACTER SET utf8mb4;")
    with cursor(with_db=True) as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(120) NOT NULL,
                price DECIMAL(10,2) NOT NULL,
                size VARCHAR(20) DEFAULT 'F',
                stock INT NOT NULL DEFAULT 0,
                image_url VARCHAR(255) DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INT AUTO_INCREMENT PRIMARY KEY,
                customer_name VARCHAR(120),
                customer_email VARCHAR(120),
                total DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS order_items (
                id INT AUTO_INCREMENT PRIMARY KEY,
                order_id INT NOT NULL,
                product_id INT NOT NULL,
                qty INT NOT NULL,
                price DECIMAL(10,2) NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
                FOREIGN KEY (product_id) REFERENCES products(id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

def get_cart():
    return session.setdefault("cart", {})

def cart_count():
    return sum(get_cart().values())

def cart_items():
    items = []
    if not get_cart():
        return items
    ids = list(map(int, get_cart().keys()))
    placeholders = ",".join(["%s"]*len(ids))
    with cursor() as cur:
        cur.execute(f"SELECT id, name, price, size, image_url FROM products WHERE id IN ({placeholders})", ids)
        products = {row["id"]: row for row in cur.fetchall()}
    for pid_str, qty in get_cart().items():
        pid = int(pid_str)
        prod = products.get(pid)
        if prod:
            subtotal = Decimal(prod["price"]) * qty
            items.append({"id": pid, "name": prod["name"], "price": Decimal(prod["price"]), "qty": qty, "size": prod["size"], "image_url": prod["image_url"], "subtotal": subtotal})
    return items

def cart_total():
    return sum((it["subtotal"] for it in cart_items()), Decimal("0"))

@app.route("/")
def home():
    with cursor() as cur:
        cur.execute("SELECT id, name, price, size, stock, image_url FROM products ORDER BY id DESC")
        products = cur.fetchall()
    return render_template("products.html", products=products, cart_count=cart_count())

@app.route("/admin/products/new", methods=["GET", "POST"])
def admin_new_product():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        price = request.form.get("price","0").strip()
        size = request.form.get("size","F").strip()
        stock = int(request.form.get("stock","0"))
        image_url = request.form.get("image_url","").strip() or None
        if not name:
            flash("Name is required", "warning")
            return redirect(url_for("admin_new_product"))
        with cursor() as cur:
            cur.execute("INSERT INTO products (name, price, size, stock, image_url) VALUES (%s,%s,%s,%s,%s)",
                        (name, price, size, stock, image_url))
        flash("Product created", "success")
        return redirect(url_for("home"))
    return render_template("admin_new_product.html")

@app.route("/cart")
def view_cart():
    items = cart_items()
    total = cart_total()
    return render_template("cart.html", items=items, total=total)

@app.route("/cart/add/<int:pid>", methods=["POST"])
def add_to_cart(pid):
    c = get_cart()
    c[str(pid)] = c.get(str(pid), 0) + 1
    session.modified = True
    flash("Added to cart", "success")
    return redirect(url_for("home"))

@app.route("/cart/remove/<int:pid>", methods=["POST"])
def remove_from_cart(pid):
    c = get_cart()
    c.pop(str(pid), None)
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
            except:
                qty = 0
            if qty == 0:
                c.pop(pid, None)
            else:
                c[pid] = qty
    session.modified = True
    return redirect(url_for("view_cart"))

@app.route("/checkout", methods=["POST"])
def checkout():
    items = cart_items()
    if not items:
        flash("Cart is empty", "warning")
        return redirect(url_for("home"))
    name = request.form.get("customer_name","Guest")
    email = request.form.get("customer_email","")
    total = cart_total()
    with cursor() as cur:
        cur.execute("INSERT INTO orders (customer_name, customer_email, total) VALUES (%s,%s,%s)", (name, email, str(total)))
        cur.execute("SELECT LAST_INSERT_ID() AS id")
        order_id = cur.fetchone()["id"]
        for it in items:
            cur.execute("INSERT INTO order_items (order_id, product_id, qty, price) VALUES (%s,%s,%s,%s)",
                        (order_id, it["id"], it["qty"], str(it["price"])))
            cur.execute("UPDATE products SET stock = GREATEST(stock - %s, 0) WHERE id=%s", (it["qty"], it["id"]))
    session["cart"] = {}
    flash(f"Order #{order_id} created. Thank you!", "success")
    return redirect(url_for("home"))

@app.route("/orders")
def orders():
    with cursor() as cur:
        cur.execute("SELECT id, customer_name, customer_email, total, created_at FROM orders ORDER BY id DESC")
        rows = cur.fetchall()
    return render_template("orders.html", orders=rows)

if __name__ == "__main__":
    ensure_schema()
    app.run(debug=True)
