import os
import json
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash
from dotenv import load_dotenv
from pymongo import MongoClient

# === 載入 .env（本機） / Render 環境變數 ===
ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH, override=True)

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")

# MongoDB 設定（Atlas）
MONGO_URI = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI") or "mongodb://localhost:27017"
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "shop_demo")
MONGO_COLLECTION_NAME = os.getenv("MONGO_COLLECTION_NAME", "batch_products")

# 建立 MongoDB 連線
mongo_client = MongoClient(MONGO_URI)
mongo_db = mongo_client[MONGO_DB_NAME]
mongo_products = mongo_db[MONGO_COLLECTION_NAME]

app = Flask(__name__)
app.secret_key = SECRET_KEY


# === 首頁：直接導到批次新增頁面 ===
@app.route("/")
def index():
    return redirect(url_for("admin_batch"))


# === 批次新增商品頁面（顯示目前 MongoDB 內容） ===
@app.route("/admin_batch")
def admin_batch():
    docs = list(mongo_products.find())
    # 把 _id 轉成字串，模板比較好顯示
    for d in docs:
        d["_id"] = str(d["_id"])
    return render_template("admin_batch.html", items=docs)


# === insert_many 功能 ===
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

        # 確認每一筆都是 dict
        for doc in data:
            if not isinstance(doc, dict):
                raise ValueError("每筆資料都必須是 JSON 物件")

        result = mongo_products.insert_many(data)
        flash(f"成功批次新增 {len(result.inserted_ids)} 筆商品到 MongoDB", "success")
    except Exception as e:
        flash(f"JSON 或資料格式錯誤：{e}", "danger")

    return redirect(url_for("admin_batch"))


# === 啟動 ===
if __name__ == "__main__":
    # Render 會給 PORT，沒給就用 5000
    port = int(os.environ.get("PORT", 5000))
    # 0.0.0.0 才能在 Render 對外服務
    app.run(host="0.0.0.0", port=port, debug=False)
