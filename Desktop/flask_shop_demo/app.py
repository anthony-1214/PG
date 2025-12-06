import os
import json
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash, session
import pymysql
from contextlib import contextmanager
from dotenv import load_dotenv
from decimal import Decimal
from pymongo import MongoClient  # MongoDB

# ========================
# 載入 .env（本機用）
# ========================
ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH, override=True)

# ========================
# MySQL（僅本機使用）
# ========================
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD") or ""
DB_NAME = os.getenv("DB_NAME", "shop_demo")
DB_SOCKET = (os.getenv("DB_SOCKET") or "").strip()

# ========================
# MongoDB（Render 專用）
# ========================
MONGO_URI = os.getenv("MONGO_URI") or "mongodb://localhost:27017"
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "shop_demo")
MONGO_COLLECTION_NAME = os.getenv("MONGO_COLLECTION_NAME", "batch_products")

mongo_client = MongoClient(MONGO_URI)
mongo_db = mongo_client[MONGO_DB_NAME]
mongo_products = mongo_db[MONGO_COLLECTION_NAME]

# ========================
# Flask 初始化
# ========================
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")

# ========================
# MySQL 連線（本機）
# ========================
def _connect_base(with_db=False):
    """本機端 MySQL，Render 不會用到"""
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
    return pymysql.connect(host=DB_HOST, port=DB_PORT, **common)


@contextmanager
def cursor(with_db=True):
    """MySQL 游標（本機）"""
    conn = _connect_base(with_db=with_db)
    try:
        with conn.cursor() as cur:
            yield cur
    finally:
        conn.close()


def ensure_schema():
    """本機建立 MySQL 資料表"""
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
                image_url VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

# ========================
# 購物車邏輯（本機使用）
# ========================
def get_cart():
    return session.setdefault("cart", {})

def cart_count():
    return sum(get_cart().values())


# ========================
# 網站頁面（Render 仍可顯示）
# ========================

@app.route("/")
def home():
    """Render 版：只顯示 MongoDB 的商品"""
    docs = list(mongo_products.find())
    for d in docs:
        d["_id"] = str(d["_id"])
    return render_template("products.html", products=docs, cart_count=0)

# ========================
# MongoDB 批次新增（作業三重點）
# ========================
@app.route("/admin_batch")
def admin_batch():
    docs = list(mongo_products.find())
    for d in docs:
        d["_id"] = str(d["_id"])
    return render_template("admin_batch.html", items=docs, cart_count=0)

@app.route("/batch_insert", methods=["POST"])
def batch_insert():
    raw = request.form.get("json_data", "").strip()
    if not raw:
        flash("請貼上 JSON", "warning")
        return redirect(url_for("admin_batch"))

    try:
        data = json.loads(raw)

        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            raise ValueError("格式錯誤，必須是列表或物件")

        result = mongo_products.insert_many(data)
        flash(f"成功新增 {len(result.inserted_ids)} 筆資料", "success")
    except Exception as e:
        flash(f"JSON 錯誤：{e}", "danger")

    return redirect(url_for("admin_batch"))


# ========================
# 啟動設定（支援 Render）
# ========================
if __name__ == "__main__":
    # Render = 不使用 MySQL
    if os.getenv("RENDER") != "1":
        try:
            ensure_schema()
        except Exception as e:
            print("本機 MySQL 初始化失敗：", e)

    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=False)