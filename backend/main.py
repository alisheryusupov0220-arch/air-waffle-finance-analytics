from dotenv import load_dotenv
load_dotenv()

import os
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException, Depends, Header, Query, Body, Path
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
from datetime import datetime, date
from pydantic import BaseModel, Field

# --- Импорты Helpers (из core_endpoints инструкции) ---
from database import (
    execute_query,
    execute_insert,
    execute_update,
    execute_delete,
    get_one,
    get_all,
)
from auth import get_current_user_id

# --- Импорты из analytics.py ---
from analytics import dashboard, pivot_table, get_trend_data, get_cell_details
# -----------------------------

# ============================================
# DATABASE CONFIGURATION
# ============================================

def get_db_connection():
    """Подключение к Supabase PostgreSQL"""
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        raise Exception("DATABASE_URL not found! Check .env file or Railway environment variables")
    
    try:
        conn = psycopg2.connect(database_url)
        return conn
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print(f"DATABASE_URL: {database_url[:50]}...")
        raise


@contextmanager
def db_session():
    """
    Context manager для работы с PostgreSQL базой данных.
    Нужен для старых эндпоинтов (Timeline, Analytics), которые еще не переведены на helpers.
    """
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"❌ Database transaction error: {e}")
        raise
    finally:
        conn.close()


# ============================================
# PYDANTIC MODELS (OLD + NEW merged)
# ============================================

# --- New Models from core_endpoints.py ---
class TelegramAuth(BaseModel):
    telegram_id: int

class UserCreate(BaseModel):
    telegram_id: int
    username: Optional[str] = None
    full_name: Optional[str] = None
    role: str = 'cashier'

class UserUpdate(BaseModel):
    username: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None

class AccountCreate(BaseModel):
    name: str
    type: str  # 'cash', 'bank', 'card'
    currency: str = 'UZS'
    initial_balance: float = 0

class AccountUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    is_active: Optional[bool] = None

class ExpenseCategoryCreate(BaseModel):
    name: str
    parent_id: Optional[int] = None

class IncomeCategoryCreate(BaseModel):
    name: str

# --- Old Models (Still needed for Timeline/Operations) ---
class TimelineItem(BaseModel):
    id: int
    date: str
    type: str
    category_id: Optional[int] = None
    amount: float
    account_id: Optional[int] = None
    description: Optional[str] = None
    source: Optional[str] = None
    user_id: Optional[int] = None
    from_account_id: Optional[int] = None
    to_account_id: Optional[int] = None
    commission_amount: Optional[float] = None
    created_by_name: Optional[str] = None
    created_by_username: Optional[str] = None 

class OperationBase(BaseModel):
    date: str = Field(default_factory=lambda: date.today().isoformat())
    category_id: Optional[int] = None
    account_id: int
    amount: float = Field(gt=0)
    description: Optional[str] = None

class ExpenseCreate(OperationBase):
    category_id: int

class IncomeCreate(OperationBase):
    category_id: int

class IncasationCreate(BaseModel):
    date: str = Field(default_factory=lambda: date.today().isoformat())
    from_account_id: int
    to_account_id: int
    amount: float = Field(gt=0)
    description: Optional[str] = None

class TransferCreate(BaseModel):
    date: str = Field(default_factory=lambda: date.today().isoformat())
    from_account_id: int
    to_account_id: int
    amount: float = Field(gt=0)
    commission_amount: float = Field(default=0, ge=0)
    description: Optional[str] = None

class AnalyticsSetting(BaseModel):
    category_id: int
    analytic_type: str

class AnalyticsSettingInDB(AnalyticsSetting):
    id: int

class AnalyticBlock(BaseModel):
    code: str
    name: str
    icon: str = '📊'
    color: str = 'blue'
    threshold_good: float = 25.0
    threshold_warning: float = 35.0
    sort_order: int = 0

class AnalyticBlockInDB(AnalyticBlock):
    id: int
    is_active: int


# ============================================
# APP CONFIGURATION
# ============================================

app = FastAPI(title="Air Waffle Finance API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "https://air-waffle-finance.vercel.app",
        "https://air-waffle-finance-analytics.vercel.app",
        "https://*.vercel.app",
        "https://air-waffle-backend.onrender.com",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def row_to_dict(row) -> dict:
    return {key: row[key] for key in row.keys()}


# ============================================
# 1. AUTH ENDPOINTS (UPDATED)
# ============================================

@app.post("/auth/verify")
async def verify_telegram_user(auth_data: TelegramAuth):
    """
    Проверить/создать пользователя через Telegram ID
    """
    telegram_id = auth_data.telegram_id
    
    # Проверить существует ли пользователь
    user = get_one('users', 'telegram_id = %s', (telegram_id,))
    
    if user:
        # Пользователь существует
        return {
            "id": user['id'],
            "telegram_id": user['telegram_id'],
            "username": user['username'],
            "full_name": user['full_name'],
            "role": user['role'],
            "is_active": user['is_active']
        }
    else:
        # Создать нового пользователя
        new_user_id = execute_insert('users', {
            'telegram_id': telegram_id,
            'username': None,
            'full_name': f"User {telegram_id}",
            'role': 'cashier',
            'is_active': True
        })
        
        # Вернуть созданного пользователя
        new_user = get_one('users', 'id = %s', (new_user_id,))
        
        return {
            "id": new_user['id'],
            "telegram_id": new_user['telegram_id'],
            "username": new_user['username'],
            "full_name": new_user['full_name'],
            "role": new_user['role'],
            "is_active": new_user['is_active']
        }


# ============================================
# 2. USERS ENDPOINTS (UPDATED)
# ============================================

@app.get("/users")
async def get_all_users(
    user_id: int = Depends(get_current_user_id),
    is_active: Optional[bool] = None
):
    """Получить список всех пользователей"""
    # Проверить роль текущего пользователя
    current_user = get_one('users', 'id = %s', (user_id,))
    
    if not current_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if current_user['role'] not in ['owner', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Получить пользователей
    if is_active is not None:
        users = get_all('users', 'is_active = %s', (is_active,), order_by='created_at DESC')
    else:
        users = get_all('users', order_by='created_at DESC')
    
    return users


@app.get("/users/me")
async def get_current_user(user_id: int = Depends(get_current_user_id)):
    """Получить данные текущего пользователя"""
    user = get_one('users', 'id = %s', (user_id,))
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return user


@app.post("/users")
async def create_user(
    user_data: UserCreate,
    current_user_id: int = Depends(get_current_user_id)
):
    """Создать нового пользователя"""
    # Проверить права
    current_user = get_one('users', 'id = %s', (current_user_id,))
    
    if current_user['role'] != 'owner':
        raise HTTPException(status_code=403, detail="Only owner can create users")
    
    # Проверить что telegram_id уникален
    existing = get_one('users', 'telegram_id = %s', (user_data.telegram_id,))
    if existing:
        raise HTTPException(status_code=400, detail="User with this telegram_id already exists")
    
    # Создать пользователя
    new_user_id = execute_insert('users', {
        'telegram_id': user_data.telegram_id,
        'username': user_data.username,
        'full_name': user_data.full_name,
        'role': user_data.role,
        'is_active': True
    })
    
    # Вернуть созданного пользователя
    new_user = get_one('users', 'id = %s', (new_user_id,))
    return new_user


@app.put("/users/{user_id}")
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    current_user_id: int = Depends(get_current_user_id)
):
    """Обновить пользователя"""
    current_user = get_one('users', 'id = %s', (current_user_id,))
    target_user = get_one('users', 'id = %s', (user_id,))
    
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Проверка прав
    if current_user['role'] == 'owner':
        pass
    elif current_user['role'] == 'manager':
        if target_user['role'] != 'cashier':
            raise HTTPException(status_code=403, detail="Manager can only update cashiers")
    else:
        if current_user_id != user_id:
            raise HTTPException(status_code=403, detail="Can only update yourself")
        if user_data.role is not None:
            raise HTTPException(status_code=403, detail="Cannot change own role")
    
    # Подготовить данные для обновления
    update_data = {}
    if user_data.username is not None:
        update_data['username'] = user_data.username
    if user_data.full_name is not None:
        update_data['full_name'] = user_data.full_name
    if user_data.role is not None:
        update_data['role'] = user_data.role
    if user_data.is_active is not None:
        update_data['is_active'] = user_data.is_active
    
    execute_update('users', update_data, 'id = %s', (user_id,))
    updated_user = get_one('users', 'id = %s', (user_id,))
    return updated_user


@app.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user_id: int = Depends(get_current_user_id)
):
    """Удалить пользователя (soft delete)"""
    current_user = get_one('users', 'id = %s', (current_user_id,))
    
    if current_user['role'] != 'owner':
        raise HTTPException(status_code=403, detail="Only owner can delete users")
    
    target_user = get_one('users', 'id = %s', (user_id,))
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if current_user_id == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    
    execute_update('users', {'is_active': False}, 'id = %s', (user_id,))
    return {"message": "User deactivated successfully"}


# ============================================
# 3. ACCOUNTS ENDPOINTS (UPDATED)
# ============================================

@app.get("/accounts")
async def get_accounts(user_id: int = Depends(get_current_user_id)):
    """Получить список всех активных счетов"""
    accounts = get_all('accounts', 'is_active = %s', (True,), order_by='name')
    return accounts


@app.get("/accounts/{account_id}")
async def get_account(
    account_id: int,
    user_id: int = Depends(get_current_user_id)
):
    """Получить один счёт по ID"""
    account = get_one('accounts', 'id = %s AND is_active = %s', (account_id, True))
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@app.post("/accounts")
async def create_account(
    account_data: AccountCreate,
    user_id: int = Depends(get_current_user_id)
):
    """Создать новый счёт"""
    current_user = get_one('users', 'id = %s', (user_id,))
    if current_user['role'] not in ['owner', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if account_data.type not in ['cash', 'bank', 'card']:
        raise HTTPException(status_code=400, detail="Invalid account type")
    
    new_account_id = execute_insert('accounts', {
        'name': account_data.name,
        'type': account_data.type,
        'currency': account_data.currency,
        'initial_balance': account_data.initial_balance,
        'current_balance': account_data.initial_balance,
        'is_active': True
    })
    
    new_account = get_one('accounts', 'id = %s', (new_account_id,))
    return new_account


@app.put("/accounts/{account_id}")
async def update_account(
    account_id: int,
    account_data: AccountUpdate,
    user_id: int = Depends(get_current_user_id)
):
    """Обновить счёт"""
    current_user = get_one('users', 'id = %s', (user_id,))
    if current_user['role'] not in ['owner', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    account = get_one('accounts', 'id = %s', (account_id,))
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    update_data = {}
    if account_data.name is not None:
        update_data['name'] = account_data.name
    if account_data.type is not None:
        if account_data.type not in ['cash', 'bank', 'card']:
            raise HTTPException(status_code=400, detail="Invalid account type")
        update_data['type'] = account_data.type
    if account_data.is_active is not None:
        update_data['is_active'] = account_data.is_active
    
    execute_update('accounts', update_data, 'id = %s', (account_id,))
    updated_account = get_one('accounts', 'id = %s', (account_id,))
    return updated_account


@app.delete("/accounts/{account_id}")
async def delete_account(
    account_id: int,
    user_id: int = Depends(get_current_user_id)
):
    """Удалить счёт (soft delete)"""
    current_user = get_one('users', 'id = %s', (user_id,))
    if current_user['role'] != 'owner':
        raise HTTPException(status_code=403, detail="Only owner can delete accounts")
    
    account = get_one('accounts', 'id = %s', (account_id,))
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    execute_update('accounts', {'is_active': False}, 'id = %s', (account_id,))
    return {"message": "Account deleted successfully"}


# ============================================
# 4. EXPENSE CATEGORIES ENDPOINTS (UPDATED)
# ============================================

@app.get("/categories/expense")
async def get_expense_categories(user_id: int = Depends(get_current_user_id)):
    """Получить все категории расходов с иерархией"""
    categories = get_all(
        'expense_categories',
        'is_active = %s',
        (True,),
        order_by='parent_id NULLS FIRST, name'
    )
    return categories


@app.post("/categories/expense")
async def create_expense_category(
    category_data: ExpenseCategoryCreate,
    user_id: int = Depends(get_current_user_id)
):
    """Создать категорию расходов"""
    current_user = get_one('users', 'id = %s', (user_id,))
    if current_user['role'] not in ['owner', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if category_data.parent_id is not None:
        parent = get_one('expense_categories', 'id = %s', (category_data.parent_id,))
        if not parent:
            raise HTTPException(status_code=404, detail="Parent category not found")
    
    new_category_id = execute_insert('expense_categories', {
        'name': category_data.name,
        'parent_id': category_data.parent_id,
        'is_active': True
    })
    
    new_category = get_one('expense_categories', 'id = %s', (new_category_id,))
    return new_category


@app.put("/categories/expense/{category_id}")
async def update_expense_category(
    category_id: int,
    name: str = Body(...),
    parent_id: Optional[int] = Body(None),
    user_id: int = Depends(get_current_user_id),
):
    with db_session() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            "UPDATE expense_categories SET name = %s, parent_id = %s WHERE id = %s",
            (name, parent_id, category_id),
        )
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            "SELECT id, name, parent_id, is_active FROM expense_categories WHERE id = %s",
            (category_id,),
        )
        row = cursor.fetchone()
        return row_to_dict(row)


@app.delete("/categories/expense/{category_id}")
async def archive_expense_category(category_id: int, user_id: int = Depends(get_current_user_id)):
    with db_session() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            "UPDATE expense_categories SET is_active = 0 WHERE id = %s",
            (category_id,),
        )
        return {"success": True}


# ============================================
# 5. INCOME CATEGORIES ENDPOINTS (UPDATED)
# ============================================

@app.get("/categories/income")
async def get_income_categories(user_id: int = Depends(get_current_user_id)):
    """Получить все категории доходов"""
    categories = get_all(
        'income_categories',
        'is_active = %s',
        (True,),
        order_by='name'
    )
    return categories


@app.post("/categories/income")
async def create_income_category(
    category_data: IncomeCategoryCreate,
    user_id: int = Depends(get_current_user_id)
):
    """Создать категорию доходов"""
    current_user = get_one('users', 'id = %s', (user_id,))
    if current_user['role'] not in ['owner', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    new_category_id = execute_insert('income_categories', {
        'name': category_data.name,
        'is_active': True
    })
    
    new_category = get_one('income_categories', 'id = %s', (new_category_id,))
    return new_category


# ============================================
# UNIFIED CATEGORIES (NEW from core_endpoints context)
# ============================================

@app.get("/categories/unified/all")
async def get_all_unified_categories(user_id: int = Depends(get_current_user_id)):
    """Получить ОБЪЕДИНЁННЫЙ список наименований"""
    categories = get_all(
        'expense_categories',
        'is_active = %s',
        (True,),
        order_by='parent_id NULLS FIRST, name'
    )
    return categories


@app.post("/categories/unified")
async def create_unified_category(
    name: str = Body(...),
    parent_id: Optional[int] = Body(None),
    user_id: int = Depends(get_current_user_id),
):
    """Создать наименование в ОБЕИХ таблицах одновременно"""
    with db_session() as conn:
        # 1. Создать в expense_categories
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            "INSERT INTO expense_categories (name, parent_id, is_active) VALUES (%s, %s, 1)",
            (name, parent_id),
        )
        expense_id = cursor.lastrowid
        
        # 2. Создать в income_categories (БЕЗ parent_id)
        try:
            cursor.execute(
                "INSERT INTO income_categories (name, is_active) VALUES (%s, 1)",
                (name,),
            )
        except Exception as e:
            print(f"Не удалось создать в income_categories: {e}")
        
        # 3. Вернуть созданную категорию
        cursor.execute(
            "SELECT id, name, parent_id, is_active FROM expense_categories WHERE id = %s",
            (expense_id,),
        )
        row = cursor.fetchone()
        return row_to_dict(row)


@app.put("/categories/unified/{category_id}")
async def update_unified_category(
    category_id: int,
    name: str = Body(...),
    parent_id: Optional[int] = Body(None),
    user_id: int = Depends(get_current_user_id),
):
    with db_session() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            "SELECT name FROM expense_categories WHERE id = %s",
            (category_id,),
        )
        old_row = cursor.fetchone()
        if not old_row:
            raise HTTPException(status_code=404, detail="Category not found")
        old_name = old_row['name']
        
        cursor.execute(
            "UPDATE expense_categories SET name = %s, parent_id = %s WHERE id = %s",
            (name, parent_id, category_id),
        )
        try:
            cursor.execute(
                "UPDATE income_categories SET name = %s WHERE name = %s",
                (name, old_name),
            )
        except Exception as e:
            print(f"Не удалось обновить в income_categories: {e}")
        
        cursor.execute(
            "SELECT id, name, parent_id, is_active FROM expense_categories WHERE id = %s",
            (category_id,),
        )
        row = cursor.fetchone()
        return row_to_dict(row)


@app.delete("/categories/unified/{category_id}")
async def archive_unified_category(
    category_id: int,
    user_id: int = Depends(get_current_user_id)
):
    with db_session() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            "SELECT name FROM expense_categories WHERE id = %s",
            (category_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Category not found")
        category_name = row['name']
        
        cursor.execute(
            "UPDATE expense_categories SET is_active = 0 WHERE id = %s",
            (category_id,),
        )
        try:
            cursor.execute(
                "UPDATE income_categories SET is_active = 0 WHERE name = %s",
                (category_name,),
            )
        except Exception as e:
            print(f"Не удалось архивировать в income_categories: {e}")
        
        return {"success": True, "message": f"Archived '{category_name}' in both tables"}


# ============================================
# LEGACY ENDPOINTS (TIMELINE, OPERATIONS, ETC)
# ============================================

@app.get("/timeline", response_model=List[TimelineItem])
async def get_timeline(
    limit: int = Query(50, gt=0, le=200),
    start_date: str = None,
    end_date: str = None,
    user_id: int = Depends(get_current_user_id),
):
    if start_date and end_date:
        rows = execute_query(
            """
            SELECT 
                t.*,
                u.full_name as created_by_name,
                u.username as created_by_username
            FROM timeline t
            LEFT JOIN users u ON t.user_id = u.id
            WHERE t.date BETWEEN %s AND %s
            ORDER BY t.date DESC, t.id DESC
            LIMIT %s
            """,
            params=(start_date, end_date, limit),
            fetch_all=True,
        )
    else:
        rows = execute_query(
            """
            SELECT 
                t.*,
                u.full_name as created_by_name,
                u.username as created_by_username
            FROM timeline t
            LEFT JOIN users u ON t.user_id = u.id
            ORDER BY t.date DESC, t.id DESC
            LIMIT %s
            """,
            params=(limit,),
            fetch_all=True,
        )
    return rows if rows else []


@app.post("/operations/expense", response_model=TimelineItem)
async def create_expense(
    payload: ExpenseCreate,
    user_id: int = Depends(get_current_user_id),
):
    print("Попытка создать expense:", payload.dict())
    with db_session() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            """
            INSERT INTO timeline (
                date, type, category_id, amount, account_id, description, source, user_id
            ) VALUES (%s, 'expense', %s, %s, %s, %s, 'miniapp', %s)
            """,
            (str(payload.date), payload.category_id, payload.amount, payload.account_id, payload.description, user_id),
        )
        timeline_id = cursor.lastrowid
        cursor.execute("SELECT * FROM timeline WHERE id = %s", (timeline_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="Failed to create expense")
        return row_to_dict(row)


@app.post("/operations/income", response_model=TimelineItem)
async def create_income(
    payload: IncomeCreate,
    user_id: int = Depends(get_current_user_id),
):
    print("Попытка создать income:", payload.dict())
    with db_session() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            """
            INSERT INTO timeline (
                date, type, category_id, amount, account_id, description, source, user_id
            ) VALUES (%s, 'income', %s, %s, %s, %s, 'miniapp', %s)
            """,
            (str(payload.date), payload.category_id, payload.amount, payload.account_id, payload.description, user_id),
        )
        timeline_id = cursor.lastrowid
        cursor.execute("SELECT * FROM timeline WHERE id = %s", (timeline_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="Failed to create income")
        return row_to_dict(row)


@app.post("/transfers/incasation", response_model=TimelineItem)
async def create_incasation(
    payload: IncasationCreate,
    user_id: int = Depends(get_current_user_id),
):
    print("Попытка создать incasation:", payload.dict())
    with db_session() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            """
            INSERT INTO timeline (
                date, type, amount, description, source, user_id, from_account_id, to_account_id
            ) VALUES (%s, 'incasation', %s, %s, 'miniapp', %s, %s, %s)
            """,
            (str(payload.date), payload.amount, payload.description, user_id, payload.from_account_id, payload.to_account_id),
        )
        timeline_id = cursor.lastrowid
        cursor.execute("SELECT * FROM timeline WHERE id = %s", (timeline_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="Failed to create incasation record")
        return row_to_dict(row)


@app.post("/transfers/transfer", response_model=TimelineItem)
async def create_transfer(
    payload: TransferCreate,
    user_id: int = Depends(get_current_user_id),
):
    print("Попытка создать transfer:", payload.dict())
    with db_session() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            """
            INSERT INTO timeline (
                date, type, amount, description, source, user_id, from_account_id, to_account_id, commission_amount
            ) VALUES (%s, 'transfer', %s, %s, 'miniapp', %s, %s, %s, %s)
            """,
            (str(payload.date), payload.amount, payload.description, user_id, payload.from_account_id, payload.to_account_id, payload.commission_amount),
        )
        timeline_id = cursor.lastrowid
        cursor.execute("SELECT * FROM timeline WHERE id = %s", (timeline_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="Failed to create transfer record")
        return row_to_dict(row)


@app.put("/timeline/{timeline_id}", response_model=TimelineItem)
async def update_timeline_item(
    timeline_id: int,
    payload: dict = Body(...),
    user_id: int = Depends(get_current_user_id),
):
    with db_session() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("SELECT user_id FROM timeline WHERE id = %s", (timeline_id,))
        check = cursor.fetchone()
        
        if not check:
            raise HTTPException(status_code=404, detail="Operation not found")
        if check['user_id'] != user_id:
            raise HTTPException(status_code=403, detail="You can only edit your own operations")
        
        set_clause = ", ".join([f"{k} = %s" for k in payload.keys()])
        values = list(payload.values()) + [timeline_id]
        
        cursor.execute(f"UPDATE timeline SET {set_clause} WHERE id = %s", values)
        cursor.execute(
            """
            SELECT t.*, u.full_name as created_by_name, u.username as created_by_username
            FROM timeline t LEFT JOIN users u ON t.user_id = u.id
            WHERE t.id = %s
            """,
            (timeline_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="Failed to update operation")
        return row_to_dict(row)


@app.delete("/timeline/{timeline_id}")
async def delete_timeline_item(
    timeline_id: int,
    user_id: int = Depends(get_current_user_id)
):
    with db_session() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("SELECT user_id FROM timeline WHERE id = %s", (timeline_id,))
        check = cursor.fetchone()
        if not check:
            raise HTTPException(status_code=404, detail="Operation not found")
        if check['user_id'] != user_id:
            raise HTTPException(status_code=403, detail="You can only delete your own operations")
        cursor.execute("DELETE FROM timeline WHERE id = %s", (timeline_id,))
        return {"success": True}


# ==============================
# ANALYTICS ENDPOINTS
# ==============================

@app.get("/analytics/dashboard")
async def get_dashboard(
    days: int = 30,
    start_date: str = None,
    end_date: str = None,
    user_id: int = Depends(get_current_user_id),
):
    print("Запрос dashboard: days=", days, "start=", start_date, "end=", end_date)
    result = dashboard(days=days, start_date=start_date, end_date=end_date)
    print("Результат dashboard:", result)
    return result


@app.get("/analytics/pivot")
async def get_pivot(
    days: int = 30,
    start_date: str = None,
    end_date: str = None,
    group_by: str = 'month',
    user_id: int = Depends(get_current_user_id),
):
    print("Запрос pivot: days=", days, "start=", start_date, "end=", end_date, "group_by=", group_by)
    result = pivot_table(days=days, start_date=start_date, end_date=end_date, group_by=group_by)
    print("Результат pivot:", result)
    return result


@app.get("/analytics/trend")
async def trend_data(days: int = 30, user_id: int = Depends(get_current_user_id)):
    print(f"Запрос trend: days={days}")
    result = get_trend_data(days)
    print(f"Результат trend (count): {len(result)}")
    return result


@app.get("/analytics/cell-details")
async def get_cell_details_endpoint(
    period: str,
    category_name: str,
    group_by: str = 'month',
    user_id: int = Depends(get_current_user_id),
):
    result = get_cell_details(period, category_name, group_by)
    print(f"Cell details for {period}/{category_name}: {len(result)} operations")
    return result


@app.get("/analytics/settings", response_model=List[AnalyticsSettingInDB])
async def get_analytics_settings(user_id: int = Depends(get_current_user_id)):
    with db_session() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("SELECT id, category_id, analytic_type FROM analytics_settings")
        rows = cursor.fetchall()
        return [AnalyticsSettingInDB(id=row["id"], category_id=row["category_id"], analytic_type=row["analytic_type"]) for row in rows]


@app.post("/analytics/settings", response_model=AnalyticsSettingInDB)
async def create_analytics_setting(setting: AnalyticsSetting, user_id: int = Depends(get_current_user_id)):
    with db_session() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            "INSERT INTO analytics_settings (category_id, analytic_type) VALUES (%s, %s)",
            (setting.category_id, setting.analytic_type),
        )
        new_id = cursor.lastrowid
        return AnalyticsSettingInDB(id=new_id, **setting.dict())


@app.put("/analytics/settings/{setting_id}", response_model=AnalyticsSettingInDB)
async def update_analytics_setting(setting_id: int, setting: AnalyticsSetting, user_id: int = Depends(get_current_user_id)):
    with db_session() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            "UPDATE analytics_settings SET category_id = %s, analytic_type = %s WHERE id = %s",
            (setting.category_id, setting.analytic_type, setting_id),
        )
        return AnalyticsSettingInDB(id=setting_id, **setting.dict())


@app.delete("/analytics/settings/{setting_id}")
async def delete_analytics_setting(setting_id: int, user_id: int = Depends(get_current_user_id)):
    with db_session() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("DELETE FROM analytics_settings WHERE id = %s", (setting_id,))
        return {"message": "Deleted"}


@app.get("/analytics/blocks", response_model=List[AnalyticBlockInDB])
async def get_analytic_blocks(user_id: int = Depends(get_current_user_id)):
    with db_session() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            "SELECT * FROM analytic_blocks WHERE is_active = TRUE ORDER BY sort_order, name"
        )
        rows = cursor.fetchall()
        return [row_to_dict(row) for row in rows]


@app.post("/analytics/blocks", response_model=AnalyticBlockInDB)
async def create_analytic_block(block: AnalyticBlock, user_id: int = Depends(get_current_user_id)):
    with db_session() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            """
            INSERT INTO analytic_blocks 
             (code, name, icon, color, threshold_good, threshold_warning, sort_order, is_active) 
             VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE)
            """,
            (block.code, block.name, block.icon, block.color, 
             block.threshold_good, block.threshold_warning, block.sort_order),
        )
        new_id = cursor.lastrowid
        cursor.execute("SELECT * FROM analytic_blocks WHERE id = %s", (new_id,))
        row = cursor.fetchone()
        return row_to_dict(row)


@app.put("/analytics/blocks/{block_id}", response_model=AnalyticBlockInDB)
async def update_analytic_block(
    block_id: int, 
    block: AnalyticBlock, 
    user_id: int = Depends(get_current_user_id)):
    with db_session() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            """
            UPDATE analytic_blocks 
             SET code = %s, name = %s, icon = %s, color = %s, 
                 threshold_good = %s, threshold_warning = %s, sort_order = %s
            WHERE id = %s
            """,
            (block.code, block.name, block.icon, block.color, 
             block.threshold_good, block.threshold_warning, block.sort_order, block_id),
        )
        cursor.execute("SELECT * FROM analytic_blocks WHERE id = %s", (block_id,))
        row = cursor.fetchone()
        return row_to_dict(row)


@app.delete("/analytics/blocks/{block_id}")
async def delete_analytic_block(block_id: int, user_id: int = Depends(get_current_user_id)):
    with db_session() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("UPDATE analytic_blocks SET is_active = FALSE WHERE id = %s", (block_id,))
        return {"success": True}


@app.get("/analytics/accounts/{account_id}/balance")
async def get_account_balance(account_id: int, user_id: int = Depends(get_current_user_id)):
    with db_session() as conn:
        income_cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        income_cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) as total
            FROM timeline
            WHERE type = 'income' AND account_id = %s
        """, (account_id,))
        total_income = income_cursor.fetchone()[0]
        
        expense_cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        expense_cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) as total
            FROM timeline
            WHERE type = 'expense' AND account_id = %s
        """, (account_id,))
        total_expense = expense_cursor.fetchone()[0]
        
        transfer_in_cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        transfer_in_cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) as total
            FROM timeline
            WHERE type IN ('transfer', 'incasation') AND to_account_id = %s
        """, (account_id,))
        transfer_in = transfer_in_cursor.fetchone()[0]
        
        transfer_out_cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        transfer_out_cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) as total
            FROM timeline
            WHERE type IN ('transfer', 'incasation') AND from_account_id = %s
        """, (account_id,))
        transfer_out = transfer_out_cursor.fetchone()[0]
        
        balance = total_income + transfer_in - total_expense - transfer_out
        
        return {
            'balance': balance,
            'total_income': total_income,
            'total_expense': total_expense,
            'transfer_in': transfer_in,
            'transfer_out': transfer_out
        }


@app.get("/analytics/accounts/{account_id}/movements")
async def get_account_movements(
    account_id: int,
    start_date: str = None,
    end_date: str = None,
    days: int = None,
    user_id: int = Depends(get_current_user_id)
):
    with db_session() as conn:
        if start_date and end_date:
            date_filter = "AND date >= %s AND date <= %s"
            date_params = (start_date, end_date)
        elif days:
            date_filter = "AND date >= (CURRENT_DATE - INTERVAL '%s days')"
            date_params = (days,)
        else:
            date_filter = ""
            date_params = ()
        
        query = f"""
            SELECT 
                id, date, type, amount, description, category_id,
                from_account_id, to_account_id, commission_amount
            FROM timeline
            WHERE (
                (type = 'income' AND account_id = %s)
                OR (type = 'expense' AND account_id = %s)
                OR (type IN ('transfer', 'incasation') AND (from_account_id = %s OR to_account_id = %s))
            )
            {date_filter}
            ORDER BY date DESC, id DESC
        """
        
        params = (account_id, account_id, account_id, account_id) + date_params
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(query, params)
        
        operations = []
        for row in cursor.fetchall():
            op = row_to_dict(row)
            if op['type'] == 'income':
                op['balance_change'] = op['amount']
                op['direction'] = 'in'
            elif op['type'] == 'expense':
                op['balance_change'] = -op['amount']
                op['direction'] = 'out'
            elif op['type'] in ('transfer', 'incasation'):
                if op['to_account_id'] == account_id:
                    op['balance_change'] = op['amount']
                    op['direction'] = 'in'
                else:
                    op['balance_change'] = -(op['amount'] + (op['commission_amount'] or 0))
                    op['direction'] = 'out'
            operations.append(op)
        
        total_in = sum(op['balance_change'] for op in operations if op['balance_change'] > 0)
        total_out = abs(sum(op['balance_change'] for op in operations if op['balance_change'] < 0))
        
        return {
            'operations': operations,
            'total_income': total_in,
            'total_expense': total_out,
            'net_change': total_in - total_out
        }


@app.get("/analytics/accounts/{account_id}/chart")
async def get_account_chart(
    account_id: int,
    start_date: str = None,
    end_date: str = None,
    days: int = None,
    user_id: int = Depends(get_current_user_id)
):
    with db_session() as conn:
        if start_date and end_date:
            date_filter = "AND date >= %s AND date <= %s"
            date_params = (start_date, end_date)
        elif days:
            date_filter = "AND date >= (CURRENT_DATE - INTERVAL '%s days')"
            date_params = (days,)
        else:
            date_filter = ""
            date_params = ()
        
        query = f"""
            SELECT date, type, amount, from_account_id, to_account_id, commission_amount
            FROM timeline
            WHERE (
                (type = 'income' AND account_id = %s)
                OR (type = 'expense' AND account_id = %s)
                OR (type IN ('transfer', 'incasation') AND (from_account_id = %s OR to_account_id = %s))
            )
            {date_filter}
            ORDER BY date ASC, id ASC
        """
        params = (account_id, account_id, account_id, account_id) + date_params
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(query, params)
        
        daily_data = {}
        for row in cursor.fetchall():
            date = str(row['date'])
            if date not in daily_data:
                daily_data[date] = {'income': 0, 'expense': 0}
            
            if row['type'] == 'income':
                daily_data[date]['income'] += row['amount']
            elif row['type'] == 'expense':
                daily_data[date]['expense'] += row['amount']
            elif row['type'] in ('transfer', 'incasation'):
                if row['to_account_id'] == account_id:
                    daily_data[date]['income'] += row['amount']
                else:
                    daily_data[date]['expense'] += row['amount'] + (row['commission_amount'] or 0)
        
        result = []
        cumulative_balance = 0
        for date in sorted(daily_data.keys()):
            day_income = daily_data[date]['income']
            day_expense = daily_data[date]['expense']
            cumulative_balance += (day_income - day_expense)
            result.append({
                'date': date,
                'income': day_income,
                'expense': day_expense,
                'balance': cumulative_balance
            })
        return result


# ============================================
# STARTUP / HEALTH / CASHIER
# ============================================

@app.get("/")
def root():
    return {"status": "ok", "message": "Finance API v1.0"}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.on_event("startup")
async def startup_event():
    """Инициализация базы данных при запуске"""
    import os
    try:
        print("=" * 60)
        print("🚀 STARTING AIR WAFFLE FINANCE")
        print("=" * 60)
        
        database_url = os.getenv('DATABASE_URL')
        
        if not database_url:
            print("❌ CRITICAL: DATABASE_URL environment variable not found!")
            raise Exception("DATABASE_URL not configured")
        
        print(f"✅ DATABASE_URL found: {database_url[:60]}...")
        print("📊 Initializing PostgreSQL database...")
        
        # Инициализация БД только при отсутствии базовых таблиц
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                SELECT COUNT(*) 
                FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'users'
            """)
            table_exists = cur.fetchone()[0] > 0
            cur.close()
            conn.close()
            if not table_exists:
                print("📊 Initializing database (first run)...")
                from init_db_postgres import init_database
                init_database()
            else:
                print("✅ Database already initialized")
        except Exception as e:
            print(f"⚠️  Database check failed: {e}")
        
        print("=" * 60)
        print("✅ APPLICATION STARTED SUCCESSFULLY")
        print("✅ Database: PostgreSQL")
        print("=" * 60)
        
    except Exception as e:
        print("=" * 60)
        print(f"❌ STARTUP FAILED: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        raise


@app.get("/cashier/locations")
async def get_locations():
    """Получить список точек продаж"""
    with db_session() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            """
            SELECT id, name, address, is_active 
            FROM locations 
            WHERE is_active = TRUE
            ORDER BY name
            """
        )
        locations = cursor.fetchall()
        return [row_to_dict(loc) for loc in locations]


@app.get("/cashier/payment-methods")
async def get_payment_methods():
    """Получить методы оплаты"""
    with db_session() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            """
            SELECT id, name, commission_percent, is_active 
            FROM payment_methods 
            WHERE is_active = TRUE
            ORDER BY name
            """
        )
        methods = cursor.fetchall()
        return [row_to_dict(m) for m in methods]


@app.post("/cashier/reports")
async def create_cashier_report(
    report_data: dict,
    current_user_id: int = Depends(get_current_user_id)
):
    """
    ГЛАВНЫЙ ENDPOINT: Получить отчёт от кассирского приложения
    """
    with db_session() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            """
            SELECT id FROM cashier_reports 
            WHERE report_date = %s AND location_id = %s
            """,
            (report_data['report_date'], report_data['location_id'])
        )
        existing = cursor.fetchone()

        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Отчёт за {report_data['report_date']} для этой точки уже существует"
            )

        cursor.execute(
            """
            INSERT INTO cashier_reports (
                report_date, location_id, user_id, total_sales,
                closing_balance, status, updated_at
            ) VALUES (%s, %s, %s, %s, %s, 'draft', CURRENT_TIMESTAMP)
            """,
            (
                report_data['report_date'],
                report_data['location_id'],
                current_user_id,
                report_data['total_sales'],
                report_data.get('cash_actual', 0)
            )
        )
        report_id = cursor.lastrowid

        for payment in report_data.get('payments', []):
            if payment['amount'] > 0:
                cursor.execute(
                    "SELECT commission_percent FROM payment_methods WHERE id = %s",
                    (payment['payment_method_id'],)
                )
                method = cursor.fetchone()
                commission_percent = method['commission_percent'] if method else 0
                
                cursor.execute(
                    """
                    INSERT INTO cashier_report_payments (
                        report_id, payment_method_id, amount
                    ) VALUES (%s, %s, %s)
                    """,
                    (report_id, payment['payment_method_id'], payment['amount'])
                )

        for expense in report_data.get('expenses', []):
            if expense['amount'] > 0:
                cursor.execute("""
                    INSERT INTO cashier_report_expenses (
                        report_id, category_id, amount, notes
                    ) VALUES (%s, %s, %s, %s)
                """, (report_id, expense.get('category_id'), 
                      expense['amount'], expense.get('description', '')))

        for income in report_data.get('incomes', []):
            if income['amount'] > 0:
                cursor.execute("""
                    INSERT INTO cashier_report_income (
                        report_id, category_id, amount, notes
                    ) VALUES (%s, %s, %s, %s)
                """, (report_id, income.get('category_id'), 
                      income['amount'], income.get('description', '')))

        return {
            "success": True,
            "message": "Отчёт успешно сохранён",
            "report_id": report_id
        }


@app.get("/cashier/reports")
async def get_cashier_reports(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    location_id: Optional[int] = None,
    current_user_id: int = Depends(get_current_user_id)
):
    """Получить список кассирских отчётов"""
    with db_session() as conn:
        query = """
            SELECT 
                cr.*,
                l.name as location_name,
                u.full_name as cashier_name,
                u.username as cashier_username
            FROM cashier_reports cr
            LEFT JOIN locations l ON cr.location_id = l.id
            LEFT JOIN users u ON cr.user_id = u.id
            WHERE 1=1
        """
        params = []
        if start_date:
            query += " AND cr.report_date >= %s"
            params.append(start_date)
        if end_date:
            query += " AND cr.report_date <= %s"
            params.append(end_date)
        if location_id:
            query += " AND cr.location_id = %s"
            params.append(location_id)
        query += " ORDER BY cr.report_date DESC, cr.created_at DESC"

        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(query, params)
        reports = cursor.fetchall()
        return [row_to_dict(r) for r in reports]


@app.get("/cashier/reports/{report_id}")
async def get_cashier_report_details(
    report_id: int,
    current_user_id: int = Depends(get_current_user_id)
):
    """Получить детали отчёта"""
    with db_session() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("""
            SELECT 
                cr.*,
                l.name as location_name,
                u.full_name as cashier_name,
                u.username as cashier_username
            FROM cashier_reports cr
            LEFT JOIN locations l ON cr.location_id = l.id
            LEFT JOIN users u ON cr.user_id = u.id
            WHERE cr.id = %s
        """, (report_id,))
        report = cursor.fetchone()

        if not report:
            raise HTTPException(status_code=404, detail="Отчёт не найден")

        result = row_to_dict(report)

        cursor.execute("""
            SELECT 
                crp.*,
                pm.name as payment_method_name
            FROM cashier_report_payments crp
            LEFT JOIN payment_methods pm ON crp.payment_method_id = pm.id
            WHERE crp.report_id = %s
        """, (report_id,))
        payments = cursor.fetchall()
        result['payments'] = [row_to_dict(p) for p in payments]

        cursor.execute("""
            SELECT 
                cre.*,
                ec.name as category_name
            FROM cashier_report_expenses cre
            LEFT JOIN expense_categories ec ON cre.category_id = ec.id
            WHERE cre.report_id = %s
        """, (report_id,))
        expenses = cursor.fetchall()
        result['expenses'] = [row_to_dict(e) for e in expenses]

        cursor.execute("""
            SELECT 
                cri.*,
                ic.name as category_name
            FROM cashier_report_income cri
            LEFT JOIN income_categories ic ON cri.category_id = ic.id
            WHERE cri.report_id = %s
        """, (report_id,))
        incomes = cursor.fetchall()
        result['incomes'] = [row_to_dict(i) for i in incomes]

        return result