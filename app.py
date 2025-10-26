import os
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash
import pymysql
from contextlib import contextmanager
from dotenv import load_dotenv

# ① 明確指定 .env 路徑 = 與 app.py 同層的 .env
ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH, override=True)

# ② 讀取環境變數（含「回退密碼」確保先能連上）
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD") or "anthony1214"  # ← 暫時回退，跑通後可移除
DB_NAME = os.getenv("DB_NAME", "flask_demo")
DB_SOCKET = (os.getenv("DB_SOCKET") or "").strip()

# ③（除錯用）確認真的讀到密碼；跑通後可刪
print("DBG .env path:", ENV_PATH)
print("DBG Password present? ->", bool(DB_PASSWORD))

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key")

# --- DB helpers ---
def get_conn(db=None):
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=db,
        charset="utf8mb4",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )

@contextmanager
def cursor(db=DB_NAME):
    conn = get_conn(db=db)
    try:
        with conn.cursor() as cur:
            yield cur
    finally:
        conn.close()

def ensure_schema():
    # Create database and table if not exists
    with get_conn(db=None) as conn:
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME} DEFAULT CHARACTER SET utf8mb4;")
    with cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(120) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
        )

# --- Routes ---
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        if not name or not email:
            flash("Name and Email are required.", "warning")
            return redirect(url_for("index"))
        with cursor() as cur:
            cur.execute("INSERT INTO users (name, email) VALUES (%s, %s)", (name, email))
        flash("User added!", "success")
        return redirect(url_for("show"))
    return render_template("index.html")

@app.route("/show")
def show():
    with cursor() as cur:
        cur.execute("SELECT id, name, email, created_at FROM users ORDER BY id DESC")
        rows = cur.fetchall()
    return render_template("show.html", rows=rows)

@app.route("/delete/<int:user_id>", methods=["POST"])
def delete(user_id):
    with cursor() as cur:
        cur.execute("DELETE FROM users WHERE id=%s", (user_id,))
    flash("Deleted.", "info")
    return redirect(url_for("show"))

if __name__ == "__main__":
    ensure_schema()
    app.run(debug=True)
