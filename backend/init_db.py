import os
import sqlite3
from pathlib import Path


def init_database():
    """Инициализация базы данных со всеми таблицами"""

    # ПРАВИЛЬНЫЙ путь к БД
    if os.path.exists('/data'):
        DB_PATH = '/data/finance_v5.db'
        print(f"🔧 Production mode: using {DB_PATH}")
    else:
        DB_PATH = 'finance_v5.db'
        print(f"🔧 Development mode: using {DB_PATH}")

    # Создаём директорию если нужно
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
        print(f"✅ Created directory: {db_dir}")

    # Ensure the DB file exists (connect will create it)
    conn = sqlite3.connect(DB_PATH)
    conn.close()

    # Run existing table initialization from database.py
    try:
        from database import init_cashier_reports_tables
        init_cashier_reports_tables()
    except Exception as e:
        print(f"Warning: failed to run init_cashier_reports_tables: {e}")

    return DB_PATH
