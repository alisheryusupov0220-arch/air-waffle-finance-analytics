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
from datetime import datetime, date, timedelta
from pydantic import BaseModel, Field
from decimal import Decimal

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
# CORE PYDANTIC MODELS
# ============================================

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
# 1. AUTH ENDPOINTS
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
# 2. USERS ENDPOINTS
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
# 3. ACCOUNTS ENDPOINTS
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
# 4. EXPENSE CATEGORIES ENDPOINTS
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
# 5. INCOME CATEGORIES ENDPOINTS
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
# UNIFIED CATEGORIES
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
# PAYMENT METHODS & LOCATIONS ENDPOINTS
# ============================================

# --- PYDANTIC MODELS FOR PAYMENT/LOCATIONS ---

class PaymentMethodCreate(BaseModel):
    name: str
    commission_percent: float = 0

class PaymentMethodUpdate(BaseModel):
    name: Optional[str] = None
    commission_percent: Optional[float] = None
    is_active: Optional[bool] = None

class LocationCreate(BaseModel):
    name: str
    address: Optional[str] = None

class LocationUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    is_active: Optional[bool] = None

# --- PAYMENT METHODS ENDPOINTS ---

@app.post("/payment-methods")
async def create_payment_method(
    method_data: PaymentMethodCreate,
    user_id: int = Depends(get_current_user_id)
):
    """
    Создать метод оплаты
    
    Только owner и manager
    """
    current_user = get_one('users', 'id = %s', (user_id,))
    
    if current_user['role'] not in ['owner', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    new_method_id = execute_insert('payment_methods', {
        'name': method_data.name,
        'commission_percent': method_data.commission_percent,
        'is_active': True
    })
    
    new_method = get_one('payment_methods', 'id = %s', (new_method_id,))
    return new_method


@app.put("/payment-methods/{method_id}")
async def update_payment_method(
    method_id: int,
    method_data: PaymentMethodUpdate,
    user_id: int = Depends(get_current_user_id)
):
    """
    Обновить метод оплаты
    
    Только owner и manager
    """
    current_user = get_one('users', 'id = %s', (user_id,))
    
    if current_user['role'] not in ['owner', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    method = get_one('payment_methods', 'id = %s', (method_id,))
    if not method:
        raise HTTPException(status_code=404, detail="Payment method not found")
    
    update_data = {}
    if method_data.name is not None:
        update_data['name'] = method_data.name
    if method_data.commission_percent is not None:
        update_data['commission_percent'] = method_data.commission_percent
    if method_data.is_active is not None:
        update_data['is_active'] = method_data.is_active
    
    execute_update('payment_methods', update_data, 'id = %s', (method_id,))
    
    updated_method = get_one('payment_methods', 'id = %s', (method_id,))
    return updated_method


@app.delete("/payment-methods/{method_id}")
async def delete_payment_method(
    method_id: int,
    user_id: int = Depends(get_current_user_id)
):
    """
    Удалить метод оплаты (soft delete)
    
    Только owner
    """
    current_user = get_one('users', 'id = %s', (user_id,))
    
    if current_user['role'] != 'owner':
        raise HTTPException(status_code=403, detail="Only owner can delete payment methods")
    
    method = get_one('payment_methods', 'id = %s', (method_id,))
    if not method:
        raise HTTPException(status_code=404, detail="Payment method not found")
    
    execute_update('payment_methods', {'is_active': False}, 'id = %s', (method_id,))
    
    return {"message": "Payment method deleted successfully"}


# --- LOCATIONS ENDPOINTS ---

@app.post("/locations")
async def create_location(
    location_data: LocationCreate,
    user_id: int = Depends(get_current_user_id)
):
    """
    Создать локацию
    
    Только owner и manager
    """
    current_user = get_one('users', 'id = %s', (user_id,))
    
    if current_user['role'] not in ['owner', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    new_location_id = execute_insert('locations', {
        'name': location_data.name,
        'address': location_data.address,
        'is_active': True
    })
    
    new_location = get_one('locations', 'id = %s', (new_location_id,))
    return new_location


@app.put("/locations/{location_id}")
async def update_location(
    location_id: int,
    location_data: LocationUpdate,
    user_id: int = Depends(get_current_user_id)
):
    """
    Обновить локацию
    
    Только owner и manager
    """
    current_user = get_one('users', 'id = %s', (user_id,))
    
    if current_user['role'] not in ['owner', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    location = get_one('locations', 'id = %s', (location_id,))
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    
    update_data = {}
    if location_data.name is not None:
        update_data['name'] = location_data.name
    if location_data.address is not None:
        update_data['address'] = location_data.address
    if location_data.is_active is not None:
        update_data['is_active'] = location_data.is_active
    
    execute_update('locations', update_data, 'id = %s', (location_id,))
    
    updated_location = get_one('locations', 'id = %s', (location_id,))
    return updated_location


@app.delete("/locations/{location_id}")
async def delete_location(
    location_id: int,
    user_id: int = Depends(get_current_user_id)
):
    """
    Удалить локацию (soft delete)
    
    Только owner
    """
    current_user = get_one('users', 'id = %s', (user_id,))
    
    if current_user['role'] != 'owner':
        raise HTTPException(status_code=403, detail="Only owner can delete locations")
    
    location = get_one('locations', 'id = %s', (location_id,))
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    
    execute_update('locations', {'is_active': False}, 'id = %s', (location_id,))
    
    return {"message": "Location deleted successfully"}


# ============================================
# NEW OPERATIONS & ANALYTICS
# ============================================

# --- MODELS ---
# ============================================
# ПРАВИЛЬНЫЙ КОД ДЛЯ ОПЕРАЦИЙ
# Замени в main.py начиная со строки 853
# ============================================

class OperationCreate(BaseModel):
    """Модель для создания расхода/дохода"""
    date: str  # YYYY-MM-DD
    category_id: int
    account_id: int  # Счет для операции
    amount: float
    description: Optional[str] = None
    location_id: Optional[int] = None


# ============================================
# POST /operations/expense
# ============================================

@app.post("/operations/expense")
async def create_expense(
    operation: OperationCreate,
    user_id: int = Depends(get_current_user_id)
):
    """Создать расход"""
    
    if operation.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
        # 1. Проверить категорию
        cursor.execute("SELECT type FROM categories WHERE id = %s AND is_active = TRUE", 
                      (operation.category_id,))
        category = cursor.fetchone()
        
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")
        if category['type'] != 'expense':
            raise HTTPException(status_code=400, detail="Category must be expense type")
        
        # 2. Проверить счет
        cursor.execute("SELECT id, balance FROM accounts WHERE id = %s", 
                      (operation.account_id,))
        account = cursor.fetchone()
        
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        
        # 3. Создать операцию
        cursor.execute("""
            INSERT INTO timeline (
                date, type, category_id,
                amount, from_account_id,
                description, location_id, user_id,
                created_at
            ) VALUES (
                %s, 'expense', %s,
                %s, %s,
                %s, %s, %s,
                NOW()
            )
            RETURNING id
        """, (
            operation.date,
            operation.category_id,
            operation.amount,
            operation.account_id,
            operation.description,
            operation.location_id,
            user_id
        ))
        
        operation_id = cursor.fetchone()['id']
        
        # 4. Обновить баланс счета (вычесть)
        cursor.execute("""
            UPDATE accounts 
            SET balance = balance - %s
            WHERE id = %s
        """, (operation.amount, operation.account_id))
        
        conn.commit()
        
        # 5. Вернуть созданную операцию с joined данными
        cursor.execute("""
            SELECT 
                t.id,
                t.date,
                t.type,
                t.amount,
                t.description,
                t.category_id,
                t.from_account_id,
                t.location_id,
                t.user_id,
                t.created_at,
                c.name as category_name,
                a.name as account_name,
                l.name as location_name,
                u.full_name as created_by_name,
                u.username as created_by_username
            FROM timeline t
            LEFT JOIN categories c ON t.category_id = c.id
            LEFT JOIN accounts a ON t.from_account_id = a.id
            LEFT JOIN locations l ON t.location_id = l.id
            LEFT JOIN users u ON t.user_id = u.id
            WHERE t.id = %s
        """, (operation_id,))
        
        result = cursor.fetchone()
        return dict(result)
        
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        print(f"❌ Error creating expense: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()


# ============================================
# POST /operations/income
# ============================================

@app.post("/operations/income")
async def create_income(
    operation: OperationCreate,
    user_id: int = Depends(get_current_user_id)
):
    """Создать доход"""
    
    if operation.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
        # 1. Проверить категорию
        cursor.execute("SELECT type FROM categories WHERE id = %s AND is_active = TRUE", 
                      (operation.category_id,))
        category = cursor.fetchone()
        
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")
        if category['type'] != 'income':
            raise HTTPException(status_code=400, detail="Category must be income type")
        
        # 2. Проверить счет
        cursor.execute("SELECT id, balance FROM accounts WHERE id = %s", 
                      (operation.account_id,))
        account = cursor.fetchone()
        
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        
        # 3. Создать операцию
        cursor.execute("""
            INSERT INTO timeline (
                date, type, category_id,
                amount, to_account_id,
                description, location_id, user_id,
                created_at
            ) VALUES (
                %s, 'income', %s,
                %s, %s,
                %s, %s, %s,
                NOW()
            )
            RETURNING id
        """, (
            operation.date,
            operation.category_id,
            operation.amount,
            operation.account_id,
            operation.description,
            operation.location_id,
            user_id
        ))
        
        operation_id = cursor.fetchone()['id']
        
        # 4. Обновить баланс счета (добавить)
        cursor.execute("""
            UPDATE accounts 
            SET balance = balance + %s
            WHERE id = %s
        """, (operation.amount, operation.account_id))
        
        conn.commit()
        
        # 5. Вернуть созданную операцию с joined данными
        cursor.execute("""
            SELECT 
                t.id,
                t.date,
                t.type,
                t.amount,
                t.description,
                t.category_id,
                t.to_account_id,
                t.location_id,
                t.user_id,
                t.created_at,
                c.name as category_name,
                a.name as account_name,
                l.name as location_name,
                u.full_name as created_by_name,
                u.username as created_by_username
            FROM timeline t
            LEFT JOIN categories c ON t.category_id = c.id
            LEFT JOIN accounts a ON t.to_account_id = a.id
            LEFT JOIN locations l ON t.location_id = l.id
            LEFT JOIN users u ON t.user_id = u.id
            WHERE t.id = %s
        """, (operation_id,))
        
        result = cursor.fetchone()
        return dict(result)
        
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        print(f"❌ Error creating income: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()


@app.get("/operations")
async def get_operations(
    user_id: int = Depends(get_current_user_id),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    type: Optional[str] = None,
    location_id: Optional[int] = None
):
    """Получить список операций"""
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
        query = """
            SELECT 
                t.id,
                t.date,
                t.type,
                t.amount,
                t.description,
                t.category_id,
                t.payment_method_id,
                t.location_id,
                t.from_account_id,
                t.to_account_id,
                t.user_id,
                t.created_at,
                c.name as category_name,
                pm.name as payment_method_name,
                l.name as location_name,
                fa.name as from_account_name,
                ta.name as to_account_name,
                u.full_name as created_by_name,
                u.username as created_by_username
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
        
        if location_id:
            query += " AND t.location_id = %s"
            params.append(location_id)
        
        query += " ORDER BY t.date DESC, t.created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        cursor.execute(query, tuple(params))
        operations = cursor.fetchall()
        
        return [dict(op) for op in operations]
        
    finally:
        cursor.close()
        conn.close()


@app.delete("/operations/{operation_id}")
async def delete_operation(
    operation_id: int,
    user_id: int = Depends(get_current_user_id)
):
    """Удалить операцию"""
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
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
        
        # Откатить изменения балансов
        if operation['type'] == 'expense':
            cursor.execute(
                "SELECT payment_method_id FROM timeline WHERE id = %s",
                (operation_id,)
            )
            account_id = get_account_for_payment_method_cursor(operation['payment_method_id'], cursor)
            update_account_balance_cursor(account_id, amount, cursor)
            
        elif operation['type'] == 'income':
            account_id = get_account_for_payment_method_cursor(operation['payment_method_id'], cursor)
            update_account_balance_cursor(account_id, -amount, cursor)
            
        elif operation['type'] == 'transfer':
            update_account_balance_cursor(operation['from_account_id'], amount, cursor)
            update_account_balance_cursor(operation['to_account_id'], -amount, cursor)
        
        # Удалить операцию
        cursor.execute("DELETE FROM timeline WHERE id = %s", (operation_id,))
        
        conn.commit()
        
        return {"success": True, "message": "Operation deleted"}
        
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()


@app.get("/payment-methods")
async def get_payment_methods_new(user_id: int = Depends(get_current_user_id)):
    """Получить методы оплаты"""
    methods = get_all('payment_methods', 'is_active = %s', (True,), order_by='name')
    return methods


@app.get("/locations")
async def get_locations_new(user_id: int = Depends(get_current_user_id)):
    """Получить локации"""
    locations = get_all('locations', 'is_active = %s', (True,), order_by='name')
    return locations


# --- ANALYTICS ---

@app.get("/analytics/summary")
async def get_analytics_summary(
    user_id: int = Depends(get_current_user_id),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """Общая сводка"""
    
    # По умолчанию - текущий месяц
    if not start_date or not end_date:
        today = datetime.now()
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        end_date = (next_month - timedelta(days=1)).strftime('%Y-%m-%d')
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
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
        
        # Балансы счетов
        cursor.execute("""
            SELECT id, name, type, current_balance, currency
            FROM accounts
            WHERE is_active = true
            ORDER BY name
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
        
    finally:
        cursor.close()
        conn.close()


@app.get("/analytics/by-category")
async def get_analytics_by_category(
    user_id: int = Depends(get_current_user_id),
    type: str = Query(..., regex="^(expense|income)$"),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """Аналитика по категориям"""
    
    if not start_date or not end_date:
        today = datetime.now()
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        end_date = (next_month - timedelta(days=1)).strftime('%Y-%m-%d')
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
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
        
    finally:
        cursor.close()
        conn.close()


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