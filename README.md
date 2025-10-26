# 資料庫系統
姓名：劉澤文

學號：41271128H

系級：科技116

## Quickstart

1) Create and activate a virtualenv
```bash
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

2) Install dependencies
```bash
pip install -r requirements.txt
```

3) Configure DB (copy .env.example -> .env and edit values), or use defaults:
- DB_HOST=127.0.0.1
- DB_PORT=3306
- DB_USER=root
- DB_PASSWORD=your_mysql_password
- DB_NAME=flask_demo

4) Run MySQL locally and ensure your user/password are correct.

5) Start the app
```bash
python app.py
```

The app will auto-create the database/table on first run.
Open http://127.0.0.1:5000 to insert and show data.
