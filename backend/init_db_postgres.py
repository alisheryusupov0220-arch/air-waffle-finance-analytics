"""
Air Waffle Finance - PostgreSQL Database Initialization
Применяет полную схему БД к PostgreSQL на Render
"""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def init_database():
    """Инициализировать базу данных PostgreSQL"""
    
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        raise Exception("❌ DATABASE_URL not found! Check environment variables")
    
    print("🔄 Connecting to PostgreSQL...")
    
    try:
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        
        print("✅ Connected to PostgreSQL")
        print("🔄 Applying schema...")
        
        # Читаем SQL схему
        schema_path = os.path.join(os.path.dirname(__file__), 'schema_postgresql.sql')
        
        if not os.path.exists(schema_path):
            print("⚠️  schema_postgresql.sql not found, using inline schema...")
            schema_sql = get_inline_schema()
        else:
            with open(schema_path, 'r', encoding='utf-8') as f:
                schema_sql = f.read()
        
        # Применяем схему
        cursor.execute(schema_sql)
        conn.commit()
        
        print("✅ Schema applied successfully")
        
        # Проверяем что все таблицы созданы
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name
        """)
        
        tables = cursor.fetchall()
        print(f"\n📊 Tables in database: {len(tables)}")
        for table in tables:
            print(f"   ✅ {table[0]}")
        
        # Проверяем seed data
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM accounts")
        account_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM payment_methods")
        payment_count = cursor.fetchone()[0]
        
        print(f"\n📈 Initial data:")
        print(f"   Users: {user_count}")
        print(f"   Accounts: {account_count}")
        print(f"   Payment methods: {payment_count}")
        
        cursor.close()
        conn.close()
        
        print("\n✅ DATABASE INITIALIZATION COMPLETE!")
        return True
        
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        raise e


def get_inline_schema():
    """Встроенная схема если файл не найден"""
    return """
    -- Основные таблицы
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        telegram_id BIGINT UNIQUE NOT NULL,
        username TEXT,
        full_name TEXT,
        role TEXT NOT NULL DEFAULT 'cashier',
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE TABLE IF NOT EXISTS locations (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        address TEXT,
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE TABLE IF NOT EXISTS accounts (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        type TEXT NOT NULL,
        currency TEXT DEFAULT 'UZS',
        initial_balance DECIMAL(15, 2) DEFAULT 0,
        current_balance DECIMAL(15, 2) DEFAULT 0,
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE TABLE IF NOT EXISTS payment_methods (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        commission_percent DECIMAL(5, 2) DEFAULT 0,
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE TABLE IF NOT EXISTS expense_categories (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        parent_id INTEGER REFERENCES expense_categories(id),
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE TABLE IF NOT EXISTS income_categories (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE TABLE IF NOT EXISTS timeline (
        id SERIAL PRIMARY KEY,
        date DATE NOT NULL,
        type TEXT NOT NULL,
        category_id INTEGER,
        category_type TEXT,
        from_account_id INTEGER REFERENCES accounts(id),
        to_account_id INTEGER REFERENCES accounts(id),
        amount DECIMAL(15, 2) NOT NULL,
        payment_method_id INTEGER REFERENCES payment_methods(id),
        description TEXT,
        location_id INTEGER REFERENCES locations(id),
        user_id INTEGER REFERENCES users(id) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE TABLE IF NOT EXISTS analytic_blocks (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        category_ids TEXT,
        is_active BOOLEAN DEFAULT TRUE,
        display_order INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE TABLE IF NOT EXISTS analytics_settings (
        id SERIAL PRIMARY KEY,
        category_id INTEGER NOT NULL,
        category_type TEXT NOT NULL,
        analytic_type TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE TABLE IF NOT EXISTS cashier_reports (
        id SERIAL PRIMARY KEY,
        report_date DATE NOT NULL,
        location_id INTEGER REFERENCES locations(id),
        user_id INTEGER REFERENCES users(id) NOT NULL,
        opening_balance DECIMAL(15, 2) DEFAULT 0,
        closing_balance DECIMAL(15, 2) DEFAULT 0,
        total_income DECIMAL(15, 2) DEFAULT 0,
        total_expenses DECIMAL(15, 2) DEFAULT 0,
        notes TEXT,
        status TEXT DEFAULT 'draft',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE TABLE IF NOT EXISTS cashier_report_income (
        id SERIAL PRIMARY KEY,
        report_id INTEGER REFERENCES cashier_reports(id) ON DELETE CASCADE NOT NULL,
        category_id INTEGER NOT NULL,
        amount DECIMAL(15, 2) NOT NULL,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE TABLE IF NOT EXISTS cashier_report_expenses (
        id SERIAL PRIMARY KEY,
        report_id INTEGER REFERENCES cashier_reports(id) ON DELETE CASCADE NOT NULL,
        category_id INTEGER NOT NULL,
        amount DECIMAL(15, 2) NOT NULL,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE TABLE IF NOT EXISTS cashier_report_payments (
        id SERIAL PRIMARY KEY,
        report_id INTEGER REFERENCES cashier_reports(id) ON DELETE CASCADE NOT NULL,
        payment_method_id INTEGER REFERENCES payment_methods(id) NOT NULL,
        amount DECIMAL(15, 2) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    -- Seed data
    INSERT INTO locations (name, address) VALUES ('D&D Magic City', 'Main Location') ON CONFLICT DO NOTHING;
    INSERT INTO payment_methods (name, commission_percent) VALUES ('Наличные', 0), ('Карта', 2.5), ('Click', 1.5), ('Payme', 2.0) ON CONFLICT DO NOTHING;
    INSERT INTO accounts (name, type) VALUES ('Касса', 'cash'), ('Основной банк', 'bank'), ('Карта бизнес', 'card') ON CONFLICT DO NOTHING;
    INSERT INTO expense_categories (name) VALUES ('Food Cost'), ('Labor Cost'), ('Overhead') ON CONFLICT DO NOTHING;
    INSERT INTO income_categories (name) VALUES ('Продажа товаров'), ('Услуги'), ('Прочее') ON CONFLICT DO NOTHING;
    """


if __name__ == "__main__":
    init_database()
