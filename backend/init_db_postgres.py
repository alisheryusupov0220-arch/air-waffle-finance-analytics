import os
import psycopg2
from psycopg2.extras import RealDictCursor

def get_database_url():
    """Получить URL базы данных"""
    return os.getenv('DATABASE_URL')

def init_database():
    """Инициализация PostgreSQL базы данных"""
    database_url = get_database_url()
    
    if not database_url:
        print("⚠️ DATABASE_URL not found, using SQLite fallback")
        return None
    
    print(f"🔧 Initializing PostgreSQL database")
    
    # Подключаемся к PostgreSQL
    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()
    
    # Создаём таблицу users
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE NOT NULL,
            username TEXT,
            full_name TEXT,
            role TEXT CHECK (role IN ('owner', 'manager', 'accountant', 'cashier')) DEFAULT 'owner',
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    print("✅ Table 'users' created/verified")
    
    # Создаём таблицу accounts
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            type TEXT CHECK (type IN ('cash', 'bank', 'card')),
            account_type TEXT CHECK (account_type IN ('cash', 'bank')),
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    print("✅ Table 'accounts' created/verified")
    
    # Создаём таблицу expense_categories
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expense_categories (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            parent_id INTEGER REFERENCES expense_categories(id),
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    print("✅ Table 'expense_categories' created/verified")
    
    # Создаём таблицу income_categories
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS income_categories (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    print("✅ Table 'income_categories' created/verified")
    
    # Создаём таблицу timeline
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS timeline (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            date DATE NOT NULL,
            type TEXT CHECK (type IN ('expense', 'income', 'transfer', 'incasation')),
            category_id INTEGER,
            account_id INTEGER REFERENCES accounts(id),
            from_account_id INTEGER,
            to_account_id INTEGER,
            amount DECIMAL(15,2) NOT NULL,
            commission_amount DECIMAL(15,2) DEFAULT 0,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    print("✅ Table 'timeline' created/verified")
    
    # Создаём таблицу locations
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS locations (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            address TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    print("✅ Table 'locations' created/verified")
    
    # Создаём таблицу payment_methods
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payment_methods (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            method_type TEXT CHECK (method_type IN ('terminal', 'online', 'delivery', 'cash')),
            commission_percent DECIMAL(5,2) DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    print("✅ Table 'payment_methods' created/verified")
    
    # Создаём таблицу cashier_reports
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cashier_reports (
            id SERIAL PRIMARY KEY,
            report_date DATE NOT NULL,
            location_id INTEGER REFERENCES locations(id),
            user_id INTEGER REFERENCES users(id),
            total_sales DECIMAL(15,2) NOT NULL,
            cash_expected DECIMAL(15,2),
            cash_actual DECIMAL(15,2),
            cash_difference DECIMAL(15,2),
            status TEXT DEFAULT 'open' CHECK (status IN ('open', 'closed', 'verified')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            closed_at TIMESTAMP,
            notes TEXT,
            UNIQUE(report_date, location_id)
        )
    ''')
    print("✅ Table 'cashier_reports' created/verified")
    
    # Создаём таблицу cashier_report_payments
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cashier_report_payments (
            id SERIAL PRIMARY KEY,
            report_id INTEGER REFERENCES cashier_reports(id) ON DELETE CASCADE,
            payment_method_id INTEGER REFERENCES payment_methods(id),
            amount DECIMAL(15,2) NOT NULL,
            commission_amount DECIMAL(15,2) DEFAULT 0,
            net_amount DECIMAL(15,2) NOT NULL
        )
    ''')
    print("✅ Table 'cashier_report_payments' created/verified")
    
    # Создаём таблицу cashier_report_expenses
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cashier_report_expenses (
            id SERIAL PRIMARY KEY,
            report_id INTEGER REFERENCES cashier_reports(id) ON DELETE CASCADE,
            category_id INTEGER REFERENCES expense_categories(id),
            amount DECIMAL(15,2) NOT NULL,
            description TEXT
        )
    ''')
    print("✅ Table 'cashier_report_expenses' created/verified")
    
    # Создаём таблицу cashier_report_income
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cashier_report_income (
            id SERIAL PRIMARY KEY,
            report_id INTEGER REFERENCES cashier_reports(id) ON DELETE CASCADE,
            category_id INTEGER REFERENCES income_categories(id),
            amount DECIMAL(15,2) NOT NULL,
            description TEXT
        )
    ''')
    print("✅ Table 'cashier_report_income' created/verified")
    
    # Создаём индексы
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_timeline_user ON timeline(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_timeline_date ON timeline(date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_cashier_reports_date ON cashier_reports(report_date)')
    print("✅ Indexes created/verified")
    
    conn.commit()
    cursor.close()
    conn.close()
    
    print(f"✅ PostgreSQL database initialization complete")
    return database_url

if __name__ == "__main__":
    init_database()
