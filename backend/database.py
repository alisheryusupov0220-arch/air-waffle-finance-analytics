import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    # python-dotenv not installed in this environment — continue without loading .env
    pass

ROOT_DIR = Path(__file__).resolve().parent.parent

# If a FINANCE_DB_PATH env var is provided, use it. Otherwise prefer a
# mounted persistent volume under /data (Railway, Docker volumes). If /data
# doesn't exist, fall back to the local development path.
_dev_path = Path("/Users/alisheryusupov2002/Desktop/finance_system_v5/finance_v5.db")
_railway_path = Path("/data/finance_v5.db")
DEFAULT_DB_PATH = _railway_path if Path("/data").exists() else _dev_path
DB_PATH = Path(os.getenv("FINANCE_DB_PATH", DEFAULT_DB_PATH))


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db_session() -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_cashier_reports_tables():
    """Инициализация таблиц для кассирских отчётов"""
    import os

    # ПРАВИЛЬНЫЙ ПУТЬ К БД
    if os.path.exists('/data'):
        DB_PATH = '/data/finance_v5.db'
    else:
        DB_PATH = 'finance_v5.db'

    print(f"Creating DB at: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Таблица точек продаж
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            address TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица методов оплаты
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payment_methods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            method_type TEXT CHECK (method_type IN ('terminal', 'online', 'delivery', 'cash')),
            commission_percent REAL DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Основная таблица отчётов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cashier_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date TEXT NOT NULL,
            location_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            total_sales REAL NOT NULL,
            cash_expected REAL,
            cash_actual REAL,
            cash_difference REAL,
            status TEXT DEFAULT 'open' CHECK (status IN ('open', 'closed', 'verified')),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            closed_at TEXT,
            notes TEXT,
            FOREIGN KEY (location_id) REFERENCES locations(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(report_date, location_id)
        )
    ''')
    
    # Детали по методам оплаты
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cashier_report_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id INTEGER NOT NULL,
            payment_method_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            commission_amount REAL DEFAULT 0,
            net_amount REAL NOT NULL,
            FOREIGN KEY (report_id) REFERENCES cashier_reports(id) ON DELETE CASCADE,
            FOREIGN KEY (payment_method_id) REFERENCES payment_methods(id)
        )
    ''')
    
    # Расходы в отчёте
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cashier_report_expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id INTEGER NOT NULL,
            category_id INTEGER,
            amount REAL NOT NULL,
            description TEXT,
            FOREIGN KEY (report_id) REFERENCES cashier_reports(id) ON DELETE CASCADE,
            FOREIGN KEY (category_id) REFERENCES expense_categories(id)
        )
    ''')
    
    # Прочие приходы в отчёте
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cashier_report_income (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id INTEGER NOT NULL,
            category_id INTEGER,
            amount REAL NOT NULL,
            description TEXT,
            FOREIGN KEY (report_id) REFERENCES cashier_reports(id) ON DELETE CASCADE,
            FOREIGN KEY (category_id) REFERENCES income_categories(id)
        )
    ''')
    
    # Индексы
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_cashier_reports_date ON cashier_reports(report_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_cashier_reports_location ON cashier_reports(location_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_cashier_reports_user ON cashier_reports(user_id)')
    
    conn.commit()
    conn.close()
    print("✅ Таблицы для кассирских отчётов созданы")


if __name__ == "__main__":
    init_cashier_reports_tables()

