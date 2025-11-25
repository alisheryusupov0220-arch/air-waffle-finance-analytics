-- ============================================
-- AIR WAFFLE FINANCE - POSTGRESQL SCHEMA
-- Полная схема базы данных для продакшна
-- ============================================

-- Очистка (только для dev/test)
-- DROP TABLE IF EXISTS cashier_report_payments CASCADE;
-- DROP TABLE IF EXISTS cashier_report_expenses CASCADE;
-- DROP TABLE IF EXISTS cashier_report_income CASCADE;
-- DROP TABLE IF EXISTS cashier_reports CASCADE;
-- DROP TABLE IF EXISTS timeline CASCADE;
-- DROP TABLE IF EXISTS analytics_settings CASCADE;
-- DROP TABLE IF EXISTS analytic_blocks CASCADE;
-- DROP TABLE IF EXISTS expense_categories CASCADE;
-- DROP TABLE IF EXISTS income_categories CASCADE;
-- DROP TABLE IF EXISTS payment_methods CASCADE;
-- DROP TABLE IF EXISTS accounts CASCADE;
-- DROP TABLE IF EXISTS locations CASCADE;
-- DROP TABLE IF EXISTS users CASCADE;

-- ============================================
-- 1. USERS (базовая таблица)
-- ============================================
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username TEXT,
    full_name TEXT,
    role TEXT NOT NULL DEFAULT 'cashier' CHECK (role IN ('owner', 'manager', 'accountant', 'cashier')),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

-- ============================================
-- 2. LOCATIONS (локации/точки)
-- ============================================
CREATE TABLE IF NOT EXISTS locations (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    address TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- 3. ACCOUNTS (счета/кошельки)
-- ============================================
CREATE TABLE IF NOT EXISTS accounts (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('cash', 'bank', 'card')),
    currency TEXT DEFAULT 'UZS',
    initial_balance DECIMAL(15, 2) DEFAULT 0,
    current_balance DECIMAL(15, 2) DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_accounts_type ON accounts(type);
CREATE INDEX IF NOT EXISTS idx_accounts_active ON accounts(is_active);

-- ============================================
-- 4. PAYMENT METHODS (методы оплаты)
-- ============================================
CREATE TABLE IF NOT EXISTS payment_methods (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    commission_percent DECIMAL(5, 2) DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- 5. EXPENSE CATEGORIES (категории расходов - иерархия)
-- ============================================
CREATE TABLE IF NOT EXISTS expense_categories (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    parent_id INTEGER REFERENCES expense_categories(id) ON DELETE CASCADE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_expense_categories_parent ON expense_categories(parent_id);

-- ============================================
-- 6. INCOME CATEGORIES (категории доходов)
-- ============================================
CREATE TABLE IF NOT EXISTS income_categories (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- 7. TIMELINE (главная таблица операций)
-- ============================================
CREATE TABLE IF NOT EXISTS timeline (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('expense', 'income', 'transfer')),
    
    -- Для expense/income
    category_id INTEGER,
    category_type TEXT CHECK (category_type IN ('expense', 'income')),
    
    -- Для transfer
    from_account_id INTEGER REFERENCES accounts(id),
    to_account_id INTEGER REFERENCES accounts(id),
    
    amount DECIMAL(15, 2) NOT NULL,
    payment_method_id INTEGER REFERENCES payment_methods(id),
    
    description TEXT,
    location_id INTEGER REFERENCES locations(id),
    
    user_id INTEGER REFERENCES users(id) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Проверки
    CONSTRAINT check_expense_has_category CHECK (
        type != 'expense' OR (category_id IS NOT NULL AND category_type = 'expense')
    ),
    CONSTRAINT check_income_has_category CHECK (
        type != 'income' OR (category_id IS NOT NULL AND category_type = 'income')
    ),
    CONSTRAINT check_transfer_has_accounts CHECK (
        type != 'transfer' OR (from_account_id IS NOT NULL AND to_account_id IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_timeline_date ON timeline(date);
CREATE INDEX IF NOT EXISTS idx_timeline_type ON timeline(type);
CREATE INDEX IF NOT EXISTS idx_timeline_user ON timeline(user_id);
CREATE INDEX IF NOT EXISTS idx_timeline_category ON timeline(category_id, category_type);

-- ============================================
-- 8. ANALYTIC BLOCKS (блоки аналитики)
-- ============================================
CREATE TABLE IF NOT EXISTS analytic_blocks (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    category_ids TEXT, -- JSON array как строка: "[1,2,3]"
    is_active BOOLEAN DEFAULT TRUE,
    display_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- 9. ANALYTICS SETTINGS (настройки аналитики)
-- ============================================
CREATE TABLE IF NOT EXISTS analytics_settings (
    id SERIAL PRIMARY KEY,
    category_id INTEGER NOT NULL,
    category_type TEXT NOT NULL CHECK (category_type IN ('expense', 'income')),
    analytic_type TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(category_id, category_type)
);

-- ============================================
-- 10. CASHIER REPORTS (кассирские отчёты)
-- ============================================
CREATE TABLE IF NOT EXISTS cashier_reports (
    id SERIAL PRIMARY KEY,
    report_date DATE NOT NULL,
    location_id INTEGER REFERENCES locations(id),
    user_id INTEGER REFERENCES users(id) NOT NULL,
    
    -- Остатки
    opening_balance DECIMAL(15, 2) DEFAULT 0,
    closing_balance DECIMAL(15, 2) DEFAULT 0,
    
    -- Итоги
    total_income DECIMAL(15, 2) DEFAULT 0,
    total_expenses DECIMAL(15, 2) DEFAULT 0,
    
    notes TEXT,
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'submitted', 'approved')),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(report_date, location_id)
);

CREATE INDEX IF NOT EXISTS idx_cashier_reports_date ON cashier_reports(report_date);
CREATE INDEX IF NOT EXISTS idx_cashier_reports_user ON cashier_reports(user_id);

-- ============================================
-- 11. CASHIER REPORT INCOME (доходы в отчёте)
-- ============================================
CREATE TABLE IF NOT EXISTS cashier_report_income (
    id SERIAL PRIMARY KEY,
    report_id INTEGER REFERENCES cashier_reports(id) ON DELETE CASCADE NOT NULL,
    category_id INTEGER NOT NULL,
    amount DECIMAL(15, 2) NOT NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cashier_report_income_report ON cashier_report_income(report_id);

-- ============================================
-- 12. CASHIER REPORT EXPENSES (расходы в отчёте)
-- ============================================
CREATE TABLE IF NOT EXISTS cashier_report_expenses (
    id SERIAL PRIMARY KEY,
    report_id INTEGER REFERENCES cashier_reports(id) ON DELETE CASCADE NOT NULL,
    category_id INTEGER NOT NULL,
    amount DECIMAL(15, 2) NOT NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cashier_report_expenses_report ON cashier_report_expenses(report_id);

-- ============================================
-- 13. CASHIER REPORT PAYMENTS (платежи в отчёте)
-- ============================================
CREATE TABLE IF NOT EXISTS cashier_report_payments (
    id SERIAL PRIMARY KEY,
    report_id INTEGER REFERENCES cashier_reports(id) ON DELETE CASCADE NOT NULL,
    payment_method_id INTEGER REFERENCES payment_methods(id) NOT NULL,
    amount DECIMAL(15, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cashier_report_payments_report ON cashier_report_payments(report_id);

-- ============================================
-- TRIGGERS для updated_at
-- ============================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_accounts_updated_at BEFORE UPDATE ON accounts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_timeline_updated_at BEFORE UPDATE ON timeline
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_cashier_reports_updated_at BEFORE UPDATE ON cashier_reports
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- SEED DATA (начальные данные)
-- ============================================

-- Дефолтная локация
INSERT INTO locations (name, address) 
VALUES ('D&D Magic City', 'Main Location')
ON CONFLICT DO NOTHING;

-- Дефолтные методы оплаты
INSERT INTO payment_methods (name, commission_percent) VALUES
    ('Наличные', 0),
    ('Карта', 2.5),
    ('Click', 1.5),
    ('Payme', 2.0)
ON CONFLICT DO NOTHING;

-- Дефолтные счета
INSERT INTO accounts (name, type, initial_balance, current_balance) VALUES
    ('Касса', 'cash', 0, 0),
    ('Основной банк', 'bank', 0, 0),
    ('Карта бизнес', 'card', 0, 0)
ON CONFLICT DO NOTHING;

-- Базовые категории расходов
INSERT INTO expense_categories (name, parent_id) VALUES
    ('Food Cost', NULL),
    ('Labor Cost', NULL),
    ('Overhead', NULL)
ON CONFLICT DO NOTHING;

-- Базовые категории доходов
INSERT INTO income_categories (name) VALUES
    ('Продажа товаров'),
    ('Услуги'),
    ('Прочее')
ON CONFLICT DO NOTHING;

-- ============================================
-- ГОТОВО!
-- ============================================
