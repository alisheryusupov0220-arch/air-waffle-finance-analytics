"""
AIR WAFFLE FINANCE - BACKEND
PostgreSQL Full Implementation
"""

import os
from fastapi import FastAPI, HTTPException, Depends, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime, timedelta
from decimal import Decimal
import psycopg2
import psycopg2.extras
from contextlib import contextmanager

# ============================================
# FASTAPI APP
# ============================================

app = FastAPI(
    title="Air Waffle Finance API",
    description="Financial Management System",
    version="2.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# DATABASE CONNECTION
# ============================================

def get_db_connection():
    """Получить подключение к PostgreSQL"""
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        raise HTTPException(status_code=500, detail="DATABASE_URL not configured")
    
    # Render использует postgres://, но psycopg2 требует postgresql://
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    try:
        conn = psycopg2.connect(database_url)
        return conn
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection failed: {str(e)}")


@contextmanager
def get_cursor():
    """Context manager для курсора"""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield cursor, conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


# ============================================
# DATABASE HELPERS
# ============================================

def execute_query(query: str, params: tuple = None, fetch_one: bool = False, fetch_all: bool = True):
    """Универсальный execute query"""
    with get_cursor() as (cursor, conn):
        cursor.execute(query, params or ())
        
        if fetch_one:
            result = cursor.fetchone()
            return dict(result) if result else None
        
        if fetch_all:
            results = cursor.fetchall()
            return [dict(row) for row in results]
        
        return None


def get_one(table: str, where: str = None, params: tuple = None):
    """Получить одну запись"""
    query = f"SELECT * FROM {table}"
    if where:
        query += f" WHERE {where}"
    query += " LIMIT 1"
    
    return execute_query(query, params, fetch_one=True, fetch_all=False)


def get_all(table: str, where: str = None, params: tuple = None, order_by: str = None):
    """Получить все записи"""
    query = f"SELECT * FROM {table}"
    if where:
        query += f" WHERE {where}"
    if order_by:
        query += f" ORDER BY {order_by}"
    
    return execute_query(query, params, fetch_all=True)


def execute_insert(table: str, data: dict) -> int:
    """Вставить запись"""
    columns = ', '.join(data.keys())
    placeholders = ', '.join(['%s'] * len(data))
    query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) RETURNING id"
    
    with get_cursor() as (cursor, conn):
        cursor.execute(query, tuple(data.values()))
        return cursor.fetchone()['id']


def execute_update(table: str, data: dict, where: str, params: tuple):
    """Обновить запись"""
    set_clause = ', '.join([f"{k} = %s" for k in data.keys()])
    query = f"UPDATE {table} SET {set_clause} WHERE {where}"
    
    with get_cursor() as (cursor, conn):
        cursor.execute(query, tuple(data.values()) + params)


# ============================================
# AUTH
# ============================================

def get_current_user_id(x_telegram_id: int = Header(..., alias="X-Telegram-Id")) -> int:
    """
    Получить текущего пользователя.
    Используем Header, так как фронтенд отправляет X-Telegram-Id.
    """
    user = get_one('users', 'telegram_id = %s', (x_telegram_id,))
    
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    return user['id']


# ============================================
# PYDANTIC MODELS
# ============================================

class UserCreate(BaseModel):
    telegram_id: int
    username: Optional[str] = None
    full_name: str
    role: str = 'cashier'


class AccountCreate(BaseModel):
    name: str
    type: str
    currency: str = 'UZS'
    initial_balance: float = 0


class CategoryCreate(BaseModel):
    name: str
    type: str  # 'expense' или 'income'


class OperationCreate(BaseModel):
    date: str
    category_id: int
    amount: float
    payment_method_id: int
    description: Optional[str] = None
    location_id: Optional[int] = None


class TransferCreate(BaseModel):
    date: str
    from_account_id: int
    to_account_id: int
    amount: float
    description: Optional[str] = None


# ============================================
# ROOT
# ============================================

@app.get("/")
async def root():
    return {
        "app": "Air Waffle Finance API",
        "version": "2.0.0",
        "status": "running",
        "database": "PostgreSQL"
    }


@app.get("/health")
async def health():
    """Health check"""
    try:
        with get_cursor() as (cursor, conn):
            cursor.execute("SELECT 1")
            return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


# ============================================
# AUTH ENDPOINTS
# ============================================

@app.post("/auth/telegram")
async def auth_telegram(user_data: UserCreate):
    """Авторизация через Telegram"""
    
    # Проверить существует ли пользователь
    user = get_one('users', 'telegram_id = %s', (user_data.telegram_id,))
    
    if user:
        return {
            "user": user,
            "is_new": False
        }
    
    # Создать нового пользователя
    new_user_id = execute_insert('users', {
        'telegram_id': user_data.telegram_id,
        'username': user_data.username,
        'full_name': user_data.full_name,
        'role': user_data.role,
        'is_active': True
    })
    
    new_user = get_one('users', 'id = %s', (new_user_id,))
    
    return {
        "user": new_user,
        "is_new": True
    }


# ============================================
# USERS
# ============================================

@app.get("/users")
async def get_users(user_id: int = Depends(get_current_user_id)):
    """Получить всех пользователей"""
    users = get_all('users', 'is_active = %s', (True,), order_by='full_name')
    return users


@app.get("/users/me")
async def get_current_user(user_id: int = Depends(get_current_user_id)):
    """Получить текущего пользователя"""
    user = get_one('users', 'id = %s', (user_id,))
    return user


# ============================================
# ACCOUNTS
# ============================================

@app.get("/accounts")
async def get_accounts(user_id: int = Depends(get_current_user_id)):
    """Получить все счета"""
    accounts = get_all('accounts', 'is_active = %s', (True,), order_by='name')
    return accounts


@app.post("/accounts")
async def create_account(
    account: AccountCreate,
    user_id: int = Depends(get_current_user_id)
):
    """Создать счёт"""
    
    # Проверка прав
    user = get_one('users', 'id = %s', (user_id,))
    if user['role'] not in ['owner', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    new_account_id = execute_insert('accounts', {
        'name': account.name,
        'type': account.type,
        'currency': account.currency,
        'initial_balance': account.initial_balance,
        'current_balance': account.initial_balance,
        'is_active': True
    })
    
    return get_one('accounts', 'id = %s', (new_account_id,))


# ============================================
# CATEGORIES
# ============================================

@app.get("/categories")
async def get_categories(
    user_id: int = Depends(get_current_user_id),
    type: Optional[str] = None
):
    """Получить категории"""
    
    if type:
        categories = get_all('categories', 'type = %s AND is_active = %s', (type, True), order_by='name')
    else:
        categories = get_all('categories', 'is_active = %s', (True,), order_by='name')
    
    return categories


@app.post("/categories")
async def create_category(
    category: CategoryCreate,
    user_id: int = Depends(get_current_user_id)
):
    """Создать категорию"""
    
    user = get_one('users', 'id = %s', (user_id,))
    if user['role'] not in ['owner', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    new_category_id = execute_insert('categories', {
        'name': category.name,
        'type': category.type,
        'is_active': True
    })
    
    return get_one('categories', 'id = %s', (new_category_id,))


# ============================================
# PAYMENT METHODS
# ============================================

@app.get("/payment-methods")
async def get_payment_methods(user_id: int = Depends(get_current_user_id)):
    """Получить методы оплаты"""
    methods = get_all('payment_methods', 'is_active = %s', (True,), order_by='name')
    return methods


# ============================================
# LOCATIONS
# ============================================

@app.get("/locations")
async def get_locations(user_id: int = Depends(get_current_user_id)):
    """Получить локации"""
    locations = get_all('locations', 'is_active = %s', (True,), order_by='name')
    return locations


# ============================================
# OPERATIONS HELPERS
# ============================================

def update_account_balance(account_id: int, amount_change: Decimal, cursor):
    """Обновить баланс счёта"""
    cursor.execute(
        "SELECT current_balance FROM accounts WHERE id = %s AND is_active = true",
        (account_id,)
    )
    account = cursor.fetchone()
    
    if not account:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")
    
    current = Decimal(str(account['current_balance']))
    new_balance = current + amount_change
    
    if new_balance < 0:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient funds. Available: {current}"
        )
    
    cursor.execute(
        "UPDATE accounts SET current_balance = %s WHERE id = %s",
        (float(new_balance), account_id)
    )


def get_account_for_payment_method(payment_method_id: int, cursor) -> int:
    """Определить счёт по методу оплаты"""
    cursor.execute("SELECT name FROM payment_methods WHERE id = %s", (payment_method_id,))
    method = cursor.fetchone()
    
    if not method:
        raise HTTPException(status_code=404, detail="Payment method not found")
    
    method_name = method['name'].lower()
    account_type = 'cash' if 'наличн' in method_name or 'cash' in method_name else 'bank'
    
    cursor.execute(
        "SELECT id FROM accounts WHERE type = %s AND is_active = true ORDER BY id LIMIT 1",
        (account_type,)
    )
    account = cursor.fetchone()
    
    if not account:
        cursor.execute("SELECT id FROM accounts WHERE is_active = true ORDER BY id LIMIT 1")
        account = cursor.fetchone()
    
    if not account:
        raise HTTPException(status_code=404, detail="No active accounts")
    
    return account['id']


# ============================================
# OPERATIONS
# ============================================

@app.post("/operations/expense")
async def create_expense(
    operation: OperationCreate,
    user_id: int = Depends(get_current_user_id)
):
    """Создать расход"""
    
    if operation.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    
    with get_cursor() as (cursor, conn):
        # Проверить категорию
        cursor.execute("SELECT type FROM categories WHERE id = %s", (operation.category_id,))
        category = cursor.fetchone()
        
        if not category or category['type'] != 'expense':
            raise HTTPException(status_code=400, detail="Invalid expense category")
        
        # Определить счёт
        account_id = get_account_for_payment_method(operation.payment_method_id, cursor)
        
        # Создать операцию
        cursor.execute("""
            INSERT INTO timeline (
                date, type, category_id, category_type,
                amount, payment_method_id, description,
                location_id, user_id
            ) VALUES (%s, 'expense', %s, 'expense', %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            operation.date, operation.category_id, operation.amount,
            operation.payment_method_id, operation.description,
            operation.location_id, user_id
        ))
        
        operation_id = cursor.fetchone()['id']
        
        # Обновить баланс
        update_account_balance(account_id, -Decimal(str(operation.amount)), cursor)
        
        # Получить операцию с joined данными
        cursor.execute("""
            SELECT 
                t.*,
                c.name as category_name,
                pm.name as payment_method_name,
                l.name as location_name,
                u.full_name as created_by_name
            FROM timeline t
            LEFT JOIN categories c ON t.category_id = c.id
            LEFT JOIN payment_methods pm ON t.payment_method_id = pm.id
            LEFT JOIN locations l ON t.location_id = l.id
            LEFT JOIN users u ON t.user_id = u.id
            WHERE t.id = %s
        """, (operation_id,))
        
        return dict(cursor.fetchone())


@app.post("/operations/income")
async def create_income(
    operation: OperationCreate,
    user_id: int = Depends(get_current_user_id)
):
    """Создать доход"""
    
    if operation.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    
    with get_cursor() as (cursor, conn):
        # Проверить категорию
        cursor.execute("SELECT type FROM categories WHERE id = %s", (operation.category_id,))
        category = cursor.fetchone()
        
        if not category or category['type'] != 'income':
            raise HTTPException(status_code=400, detail="Invalid income category")
        
        # Определить счёт
        account_id = get_account_for_payment_method(operation.payment_method_id, cursor)
        
        # Создать операцию
        cursor.execute("""
            INSERT INTO timeline (
                date, type, category_id, category_type,
                amount, payment_method_id, description,
                location_id, user_id
            ) VALUES (%s, 'income', %s, 'income', %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            operation.date, operation.category_id, operation.amount,
            operation.payment_method_id, operation.description,
            operation.location_id, user_id
        ))
        
        operation_id = cursor.fetchone()['id']
        
        # Обновить баланс
        update_account_balance(account_id, Decimal(str(operation.amount)), cursor)
        
        # Получить операцию
        cursor.execute("""
            SELECT 
                t.*,
                c.name as category_name,
                pm.name as payment_method_name,
                l.name as location_name,
                u.full_name as created_by_name
            FROM timeline t
            LEFT JOIN categories c ON t.category_id = c.id
            LEFT JOIN payment_methods pm ON t.payment_method_id = pm.id
            LEFT JOIN locations l ON t.location_id = l.id
            LEFT JOIN users u ON t.user_id = u.id
            WHERE t.id = %s
        """, (operation_id,))
        
        return dict(cursor.fetchone())


@app.post("/operations/transfer")
async def create_transfer(
    transfer: TransferCreate,
    user_id: int = Depends(get_current_user_id)
):
    """Создать перевод"""
    
    if transfer.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    
    if transfer.from_account_id == transfer.to_account_id:
        raise HTTPException(status_code=400, detail="Cannot transfer to same account")
    
    with get_cursor() as (cursor, conn):
        # Создать операцию
        cursor.execute("""
            INSERT INTO timeline (
                date, type, from_account_id, to_account_id,
                amount, description, user_id
            ) VALUES (%s, 'transfer', %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            transfer.date, transfer.from_account_id, transfer.to_account_id,
            transfer.amount, transfer.description, user_id
        ))
        
        operation_id = cursor.fetchone()['id']
        
        # Обновить балансы
        amount = Decimal(str(transfer.amount))
        update_account_balance(transfer.from_account_id, -amount, cursor)
        update_account_balance(transfer.to_account_id, amount, cursor)
        
        # Получить операцию
        cursor.execute("""
            SELECT 
                t.*,
                fa.name as from_account_name,
                ta.name as to_account_name,
                u.full_name as created_by_name
            FROM timeline t
            LEFT JOIN accounts fa ON t.from_account_id = fa.id
            LEFT JOIN accounts ta ON t.to_account_id = ta.id
            LEFT JOIN users u ON t.user_id = u.id
            WHERE t.id = %s
        """, (operation_id,))
        
        return dict(cursor.fetchone())


@app.get("/operations")
async def get_operations(
    user_id: int = Depends(get_current_user_id),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    type: Optional[str] = None
):
    """Получить операции"""
    
    query = """
        SELECT 
            t.*,
            c.name as category_name,
            pm.name as payment_method_name,
            l.name as location_name,
            fa.name as from_account_name,
            ta.name as to_account_name,
            u.full_name as created_by_name
        FROM timeline t
        LEFT JOIN categories c ON t.category_id = c.id
        LEFT JOIN payment_methods pm ON t.payment_method_id = pm.id
        LEFT JOIN locations l ON t.location_id = l.id
        LEFT JOIN accounts fa ON t.from_account_id = fa.id
        LEFT JOIN accounts ta ON t.to_account_id = ta.id
        LEFT JOIN users u ON t.user_id = u.id
        WHERE 1=1
    """
    
    params = []
    
    if start_date:
        query += " AND t.date >= %s"
        params.append(start_date)
    
    if end_date:
        query += " AND t.date <= %s"
        params.append(end_date)
    
    if type:
        query += " AND t.type = %s"
        params.append(type)
    
    query += " ORDER BY t.date DESC, t.created_at DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    
    return execute_query(query, tuple(params))


@app.delete("/operations/{operation_id}")
async def delete_operation(
    operation_id: int,
    user_id: int = Depends(get_current_user_id)
):
    """Удалить операцию"""
    
    with get_cursor() as (cursor, conn):
        # Получить операцию
        cursor.execute("SELECT * FROM timeline WHERE id = %s", (operation_id,))
        operation = cursor.fetchone()
        
        if not operation:
            raise HTTPException(status_code=404, detail="Operation not found")
        
        # Проверка прав
        cursor.execute("SELECT role FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        
        if operation['user_id'] != user_id and user['role'] != 'owner':
            raise HTTPException(status_code=403, detail="Access denied")
        
        amount = Decimal(str(operation['amount']))
        
        # Откатить балансы
        if operation['type'] == 'expense':
            account_id = get_account_for_payment_method(operation['payment_method_id'], cursor)
            update_account_balance(account_id, amount, cursor)
        elif operation['type'] == 'income':
            account_id = get_account_for_payment_method(operation['payment_method_id'], cursor)
            update_account_balance(account_id, -amount, cursor)
        elif operation['type'] == 'transfer':
            update_account_balance(operation['from_account_id'], amount, cursor)
            update_account_balance(operation['to_account_id'], -amount, cursor)
        
        # Удалить
        cursor.execute("DELETE FROM timeline WHERE id = %s", (operation_id,))
        
        return {"success": True, "message": "Operation deleted"}


# ============================================
# ANALYTICS
# ============================================

@app.get("/analytics/summary")
async def get_analytics_summary(
    user_id: int = Depends(get_current_user_id),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """Общая сводка"""
    
    if not start_date or not end_date:
        today = datetime.now()
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        end_date = (next_month - timedelta(days=1)).strftime('%Y-%m-%d')
    
    with get_cursor() as (cursor, conn):
        # Доходы
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) as total
            FROM timeline
            WHERE type = 'income' AND date BETWEEN %s AND %s
        """, (start_date, end_date))
        income = float(cursor.fetchone()['total'])
        
        # Расходы
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) as total
            FROM timeline
            WHERE type = 'expense' AND date BETWEEN %s AND %s
        """, (start_date, end_date))
        expense = float(cursor.fetchone()['total'])
        
        # Счета
        cursor.execute("""
            SELECT id, name, type, current_balance, currency
            FROM accounts WHERE is_active = true ORDER BY name
        """)
        accounts = [dict(a) for a in cursor.fetchall()]
        total_balance = sum(float(a['current_balance']) for a in accounts)
        
        return {
            "period": {"start_date": start_date, "end_date": end_date},
            "totals": {
                "income": income,
                "expense": expense,
                "net_profit": income - expense
            },
            "accounts": {
                "list": accounts,
                "total_balance": total_balance
            }
        }


@app.get("/analytics/by-category")
async def get_analytics_by_category(
    user_id: int = Depends(get_current_user_id),
    type: str = Query(..., regex="^(expense|income)$"),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """По категориям"""
    
    if not start_date or not end_date:
        today = datetime.now()
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        end_date = (next_month - timedelta(days=1)).strftime('%Y-%m-%d')
    
    with get_cursor() as (cursor, conn):
        cursor.execute("""
            SELECT 
                c.id as category_id,
                c.name as category_name,
                COUNT(t.id) as operations_count,
                COALESCE(SUM(t.amount), 0) as total_amount
            FROM timeline t
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.type = %s AND t.date BETWEEN %s AND %s
            GROUP BY c.id, c.name
            ORDER BY total_amount DESC
        """, (type, start_date, end_date))
        
        categories = cursor.fetchall()
        total = sum(float(c['total_amount']) for c in categories)
        
        result = []
        for cat in categories:
            result.append({
                "category_id": cat['category_id'],
                "category_name": cat['category_name'],
                "operations_count": cat['operations_count'],
                "total_amount": float(cat['total_amount']),
                "percentage": (float(cat['total_amount']) / total * 100) if total > 0 else 0
            })
        
        return {
            "type": type,
            "period": {"start_date": start_date, "end_date": end_date},
            "total": total,
            "categories": result
        }


# ============================================
# ГОТОВО
# ============================================