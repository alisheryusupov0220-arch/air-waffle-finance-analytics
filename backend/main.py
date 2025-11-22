from datetime import date
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Body
from auth import get_current_user_id
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# --- Импорты из analytics.py ---
from analytics import dashboard, pivot_table, get_trend_data, get_cell_details
# -----------------------------

from database import db_session, get_connection
import sqlite3


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
    created_by_name: Optional[str] = None  # Имя создателя
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


# Analytics settings models
class AnalyticsSetting(BaseModel):
    category_id: int
    analytic_type: str  # e.g., 'food_cost', 'labor_cost'


class AnalyticsSettingInDB(AnalyticsSetting):
    id: int


class TelegramAuthRequest(BaseModel):
    telegram_id: str
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    telegram_id: int
    username: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[str] = "owner"  # По умолчанию owner
    is_active: int = 1


app = FastAPI(title="Air Waffle Finance API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "*"],  # Разрешаем с 5173 (Vite) и все
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def row_to_dict(row) -> dict:
    return {key: row[key] for key in row.keys()}


@app.post("/auth/verify")
async def verify_user(request: dict):
    """Регистрация/вход через Telegram ID"""
    try:
        telegram_id = request.get('telegram_id')
        
        if not telegram_id:
            raise HTTPException(status_code=400, detail="telegram_id is required")
        
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        
        # Проверяем существует ли пользователь
        user = conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?",
            (telegram_id,)
        ).fetchone()
        
        if user:
            conn.close()
            return dict(user)
        
        # Создаём нового пользователя
        username = request.get('username', '')
        first_name = request.get('first_name', '')
        last_name = request.get('last_name', '')
        full_name = f"{first_name} {last_name}".strip() or username or f"User_{telegram_id}"
        
        cursor = conn.execute("""
            INSERT INTO users (telegram_id, username, full_name, role, is_active)
            VALUES (?, ?, ?, 'owner', 1)
        """, (telegram_id, username, full_name))
        
        user_id = cursor.lastrowid
        conn.commit()
        
        # Получаем созданного пользователя
        new_user = conn.execute(
            "SELECT * FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()
        
        conn.close()
        return dict(new_user)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/users")
async def get_all_users(current_user_id: int = Depends(get_current_user_id)):
    """Получить список всех пользователей (только для owner/manager)"""
    with db_session() as conn:
        # Проверяем роль текущего пользователя
        current_user = conn.execute(
            "SELECT role FROM users WHERE id = ?",
            (current_user_id,)
        ).fetchone()

        if not current_user or current_user['role'] not in ['owner', 'manager']:
            raise HTTPException(status_code=403, detail="Access denied. Owner or Manager role required")

        # Получаем всех пользователей
        users = conn.execute("""
            SELECT 
                id,
                telegram_id,
                username,
                full_name,
                role,
                is_active,
                created_at
            FROM users
            ORDER BY created_at DESC
        """
        ).fetchall()

        return [row_to_dict(user) for user in users]


@app.put("/users/{user_id}/role")
async def update_user_role(
    user_id: int,
    role: str,
    current_user_id: int = Depends(get_current_user_id)
):
    """Изменить роль пользователя (только owner)"""
    if role not in ['owner', 'manager', 'accountant', 'cashier']:
        raise HTTPException(status_code=400, detail="Invalid role")

    with db_session() as conn:
        # Проверяем что текущий пользователь - owner
        current_user = conn.execute(
            "SELECT role FROM users WHERE id = ?",
            (current_user_id,)
        ).fetchone()

        if not current_user or current_user['role'] != 'owner':
            raise HTTPException(status_code=403, detail="Access denied. Owner role required")

        # Обновляем роль
        conn.execute(
            "UPDATE users SET role = ? WHERE id = ?",
            (role, user_id)
        )

        return {"success": True, "message": "Role updated"}


@app.put("/users/{user_id}/status")
async def toggle_user_status(
    user_id: int,
    is_active: bool,
    current_user_id: int = Depends(get_current_user_id)
):
    """Активировать/деактивировать пользователя (только owner)"""
    with db_session() as conn:
        # Проверяем что текущий пользователь - owner
        current_user = conn.execute(
            "SELECT role FROM users WHERE id = ?",
            (current_user_id,)
        ).fetchone()

        if not current_user or current_user['role'] != 'owner':
            raise HTTPException(status_code=403, detail="Access denied. Owner role required")

        # Проверяем что не деактивируем самого себя
        if user_id == current_user_id and not is_active:
            raise HTTPException(status_code=400, detail="Cannot deactivate yourself")

        # Обновляем статус
        conn.execute(
            "UPDATE users SET is_active = ? WHERE id = ?",
            (1 if is_active else 0, user_id)
        )

        return {"success": True, "message": "Status updated"}


@app.get("/timeline", response_model=List[TimelineItem])
async def get_timeline(
    limit: int = Query(50, gt=0, le=200),
    start_date: str = None,
    end_date: str = None,
    user_id: int = Depends(get_current_user_id),
):
    with db_session() as conn:
        if start_date and end_date:
            cursor = conn.execute(
                """
                SELECT 
                    t.*,
                    u.full_name as created_by_name,
                    u.username as created_by_username
                FROM timeline t
                LEFT JOIN users u ON t.user_id = u.id
                WHERE t.date >= ? AND t.date <= ?
                ORDER BY t.date DESC, t.id DESC
                LIMIT ?
                """,
                (start_date, end_date, limit),
            )
        else:
            cursor = conn.execute(
                """
                SELECT 
                    t.*,
                    u.full_name as created_by_name,
                    u.username as created_by_username
                FROM timeline t
                LEFT JOIN users u ON t.user_id = u.id
                ORDER BY t.date DESC, t.id DESC
                LIMIT ?
                """,
                (limit,),
            )
        rows = cursor.fetchall()
        return [row_to_dict(row) for row in rows]


@app.post("/operations/expense", response_model=TimelineItem)
async def create_expense(
    payload: ExpenseCreate,
    user_id: int = Depends(get_current_user_id),
):
    # --- PRINT ДЛЯ ДЕБАГА ---
    print("Попытка создать expense:", payload.dict())
    # -----------------------
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO timeline (
                date,
                type,
                category_id,
                amount,
                account_id,
                description,
                source,
                user_id
            )
            VALUES (?, 'expense', ?, ?, ?, ?, 'miniapp', ?)
            """,
            (
                str(payload.date),
                payload.category_id,
                payload.amount,
                payload.account_id,
                payload.description,
                user_id,
            ),
        )
        timeline_id = cursor.lastrowid
        # --- PRINT ДЛЯ ДЕБАГА ---
        print("Создано expense ID:", timeline_id)
        # -----------------------
        row = conn.execute(
            "SELECT * FROM timeline WHERE id = ?", (timeline_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="Failed to create expense")
        return row_to_dict(row)


@app.post("/operations/income", response_model=TimelineItem)
async def create_income(
    payload: IncomeCreate,
    user_id: int = Depends(get_current_user_id),
):
    # --- PRINT ДЛЯ ДЕБАГА ---
    print("Попытка создать income:", payload.dict())
    # -----------------------
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO timeline (
                date,
                type,
                category_id,
                amount,
                account_id,
                description,
                source,
                user_id
            )
            VALUES (?, 'income', ?, ?, ?, ?, 'miniapp', ?)
            """,
            (
                str(payload.date),
                payload.category_id,
                payload.amount,
                payload.account_id,
                payload.description,
                user_id,
            ),
        )
        timeline_id = cursor.lastrowid
        # --- PRINT ДЛЯ ДЕБАГА ---
        print("Создано income ID:", timeline_id)
        # -----------------------
        row = conn.execute(
            "SELECT * FROM timeline WHERE id = ?", (timeline_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="Failed to create income")
        return row_to_dict(row)


@app.post("/transfers/incasation", response_model=TimelineItem)
async def create_incasation(
    payload: IncasationCreate,
    user_id: int = Depends(get_current_user_id),
):
    # --- PRINT ДЛЯ ДЕБАГА ---
    print("Попытка создать incasation:", payload.dict())
    # -----------------------
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO timeline (
                date,
                type,
                amount,
                description,
                source,
                user_id,
                from_account_id,
                to_account_id
            )
            VALUES (?, 'incasation', ?, ?, 'miniapp', ?, ?, ?)
            """,
            (
                str(payload.date),
                payload.amount,
                payload.description,
                user_id,
                payload.from_account_id,
                payload.to_account_id,
            ),
        )
        timeline_id = cursor.lastrowid
        # --- PRINT ДЛЯ ДЕБАГА ---
        print("Создано incasation ID:", timeline_id)
        # -----------------------
        row = conn.execute(
            "SELECT * FROM timeline WHERE id = ?", (timeline_id,)
        ).fetchone()
        if not row:
            raise HTTPException(
                status_code=500, detail="Failed to create incasation record"
            )
        return row_to_dict(row)


@app.post("/transfers/transfer", response_model=TimelineItem)
async def create_transfer(
    payload: TransferCreate,
    user_id: int = Depends(get_current_user_id),
):
    # --- PRINT ДЛЯ ДЕБАГА ---
    print("Попытка создать transfer:", payload.dict())
    # -----------------------
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO timeline (
                date,
                type,
                amount,
                description,
                source,
                user_id,
                from_account_id,
                to_account_id,
                commission_amount
            )
            VALUES (?, 'transfer', ?, ?, 'miniapp', ?, ?, ?, ?)
            """,
            (
                str(payload.date),
                payload.amount,
                payload.description,
                user_id,
                payload.from_account_id,
                payload.to_account_id,
                payload.commission_amount,
            ),
        )
        timeline_id = cursor.lastrowid
        # --- PRINT ДЛЯ ДЕБАГА ---
        print("Создано transfer ID:", timeline_id)
        # -----------------------
        row = conn.execute(
            "SELECT * FROM timeline WHERE id = ?", (timeline_id,)
        ).fetchone()
        if not row:
            raise HTTPException(
                status_code=500, detail="Failed to create transfer record"
            )
        return row_to_dict(row)


@app.put("/timeline/{timeline_id}", response_model=TimelineItem)
async def update_timeline_item(
    timeline_id: int,
    payload: dict = Body(...),
    user_id: int = Depends(get_current_user_id),
):
    with db_session() as conn:
        # ПРОВЕРКА: может ли пользователь редактировать эту операцию
        check = conn.execute(
            "SELECT user_id FROM timeline WHERE id = ?",
            (timeline_id,)
        ).fetchone()
        
        if not check:
            raise HTTPException(status_code=404, detail="Operation not found")
        
        if check['user_id'] != user_id:
            raise HTTPException(
                status_code=403, 
                detail="You can only edit your own operations"
            )
        
        # Обновляем операцию
        set_clause = ", ".join([f"{k} = ?" for k in payload.keys()])
        values = list(payload.values()) + [timeline_id]
        
        conn.execute(
            f"UPDATE timeline SET {set_clause} WHERE id = ?",
            values
        )
        
        # Возвращаем обновленную операцию с информацией о создателе
        cursor = conn.execute(
            """
            SELECT 
                t.*,
                u.full_name as created_by_name,
                u.username as created_by_username
            FROM timeline t
            LEFT JOIN users u ON t.user_id = u.id
            WHERE t.id = ?
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
        # ПРОВЕРКА: может ли пользователь удалить эту операцию
        check = conn.execute(
            "SELECT user_id FROM timeline WHERE id = ?",
            (timeline_id,)
        ).fetchone()
        
        if not check:
            raise HTTPException(status_code=404, detail="Operation not found")
        
        if check['user_id'] != user_id:
            raise HTTPException(
                status_code=403,
                detail="You can only delete your own operations"
            )
        
        conn.execute("DELETE FROM timeline WHERE id = ?", (timeline_id,))
        return {"success": True}


@app.get("/accounts")
async def get_accounts(user_id: int = Depends(get_current_user_id)):
    with db_session() as conn:
        # УБРАНА фильтрация по user_id
        cursor = conn.execute(
            """
            SELECT *
            FROM accounts
            WHERE is_active = 1
            ORDER BY name
            """
        )
        rows = cursor.fetchall()
        return [row_to_dict(row) for row in rows]


@app.get("/categories/expense")
async def get_expense_categories(user_id: int = Depends(get_current_user_id)):
    with db_session() as conn:
        # УБРАНА фильтрация по user_id
        cursor = conn.execute(
            """
            SELECT *
            FROM expense_categories
            WHERE is_active = 1
            ORDER BY name
            """
        )
        rows = cursor.fetchall()
        return [row_to_dict(row) for row in rows]


@app.get("/categories/income")
async def get_income_categories(user_id: int = Depends(get_current_user_id)):
    with db_session() as conn:
        cursor = conn.execute(
            """
            SELECT *
            FROM income_categories
            ORDER BY name
            """
        )
        rows = cursor.fetchall()
        return [row_to_dict(row) for row in rows]


@app.get("/analytics/dashboard")
async def get_dashboard(
    days: int = 30,
    start_date: str = None,
    end_date: str = None,
    user_id: int = Depends(get_current_user_id),
):
    # --- PRINT ДЛЯ ДЕБАГА ---
    print("Запрос dashboard: days=", days, "start=", start_date, "end=", end_date)
    # -----------------------
    result = dashboard(days=days, start_date=start_date, end_date=end_date)
    # --- PRINT ДЛЯ ДЕБАГА ---
    print("Результат dashboard:", result)
    # -----------------------
    return result


@app.get("/analytics/pivot")
async def get_pivot(
    days: int = 30,
    start_date: str = None,
    end_date: str = None,
    group_by: str = 'month',
    user_id: int = Depends(get_current_user_id),
):
    # --- PRINT ДЛЯ ДЕБАГА ---
    print("Запрос pivot: days=", days, "start=", start_date, "end=", end_date, "group_by=", group_by)
    # -----------------------
    result = pivot_table(days=days, start_date=start_date, end_date=end_date, group_by=group_by)
    # --- PRINT ДЛЯ ДЕБАГА ---
    print("Результат pivot:", result)
    # -----------------------
    return result


@app.get("/analytics/trend")
async def trend_data(days: int = 30, user_id: int = Depends(get_current_user_id)):
    # --- PRINT ДЛЯ ДЕБАГА ---
    print(f"Запрос trend: days={days}")
    # -----------------------
    result = get_trend_data(days)
    # --- PRINT ДЛЯ ДЕБАГА ---
    print(f"Результат trend (count): {len(result)}")
    # -----------------------
    return result


@app.get("/analytics/cell-details")
async def get_cell_details_endpoint(
    period: str,
    category_name: str,
    group_by: str = 'month',
    user_id: int = Depends(get_current_user_id),
):
    """
    Получить детали операций для конкретной ячейки таблицы
    """
    result = get_cell_details(period, category_name, group_by)
    print(f"Cell details for {period}/{category_name}: {len(result)} operations")
    return result


# ==============================
# Analytics settings (mapping категорий к типам аналитики)
# ==============================
@app.get("/analytics/settings", response_model=List[AnalyticsSettingInDB])
async def get_analytics_settings(user_id: int = Depends(get_current_user_id)):
    with db_session() as conn:
        cursor = conn.execute("SELECT id, category_id, analytic_type FROM analytics_settings")
        rows = cursor.fetchall()
        return [AnalyticsSettingInDB(id=row["id"], category_id=row["category_id"], analytic_type=row["analytic_type"]) for row in rows]


@app.post("/analytics/settings", response_model=AnalyticsSettingInDB)
async def create_analytics_setting(setting: AnalyticsSetting, user_id: int = Depends(get_current_user_id)):
    with db_session() as conn:
        cursor = conn.execute(
            "INSERT INTO analytics_settings (category_id, analytic_type) VALUES (?, ?)",
            (setting.category_id, setting.analytic_type),
        )
        new_id = cursor.lastrowid
        return AnalyticsSettingInDB(id=new_id, **setting.dict())


@app.put("/analytics/settings/{setting_id}", response_model=AnalyticsSettingInDB)
async def update_analytics_setting(setting_id: int, setting: AnalyticsSetting, user_id: int = Depends(get_current_user_id)):
    with db_session() as conn:
        conn.execute(
            "UPDATE analytics_settings SET category_id = ?, analytic_type = ? WHERE id = ?",
            (setting.category_id, setting.analytic_type, setting_id),
        )
        return AnalyticsSettingInDB(id=setting_id, **setting.dict())


@app.delete("/analytics/settings/{setting_id}")
async def delete_analytics_setting(setting_id: int, user_id: int = Depends(get_current_user_id)):
    with db_session() as conn:
        conn.execute("DELETE FROM analytics_settings WHERE id = ?", (setting_id,))
        return {"message": "Deleted"}


# ==============================
# Управление категориями расходов
# ==============================
@app.get("/categories/expense/all")
async def get_all_expense_categories(user_id: int = Depends(get_current_user_id)):
    with db_session() as conn:
        # SQLite не поддерживает NULLS FIRST, эквивалентная сортировка ниже
        cursor = conn.execute(
            """
            SELECT id, name, parent_id, is_active
            FROM expense_categories
            ORDER BY (parent_id IS NOT NULL), parent_id, name
            """
        )
        rows = cursor.fetchall()
        return [row_to_dict(row) for row in rows]


@app.post("/categories/expense")
async def create_expense_category(
    name: str = Body(...),
    parent_id: Optional[int] = Body(None),
    user_id: int = Depends(get_current_user_id),
):
    with db_session() as conn:
        cursor = conn.execute(
            "INSERT INTO expense_categories (name, parent_id, is_active) VALUES (?, ?, 1)",
            (name, parent_id),
        )
        new_id = cursor.lastrowid
        row = conn.execute(
            "SELECT id, name, parent_id, is_active FROM expense_categories WHERE id = ?",
            (new_id,),
        ).fetchone()
        return row_to_dict(row)


@app.put("/categories/expense/{category_id}")
async def update_expense_category(
    category_id: int,
    name: str = Body(...),
    parent_id: Optional[int] = Body(None),
    user_id: int = Depends(get_current_user_id),
):
    with db_session() as conn:
        conn.execute(
            "UPDATE expense_categories SET name = ?, parent_id = ? WHERE id = ?",
            (name, parent_id, category_id),
        )
        row = conn.execute(
            "SELECT id, name, parent_id, is_active FROM expense_categories WHERE id = ?",
            (category_id,),
        ).fetchone()
        return row_to_dict(row)


@app.delete("/categories/expense/{category_id}")
async def archive_expense_category(category_id: int, user_id: int = Depends(get_current_user_id)):
    with db_session() as conn:
        conn.execute(
            "UPDATE expense_categories SET is_active = 0 WHERE id = ?",
            (category_id,),
        )
        return {"success": True}


# ==============================
# СИНХРОНИЗИРОВАННОЕ управление наименованиями
# (обновляет ОБЕ таблицы: expense_categories И income_categories)
# ==============================

@app.get("/categories/unified/all")
async def get_all_unified_categories(user_id: int = Depends(get_current_user_id)):
    """
    Получить ОБЪЕДИНЁННЫЙ список наименований (без дублей)
    Берём из expense_categories, т.к. там больше данных
    """
    with db_session() as conn:
        # УБРАНА фильтрация по user_id
        cursor = conn.execute(
            """
            SELECT id, name, parent_id, is_active
            FROM expense_categories
            WHERE is_active = 1
            ORDER BY (parent_id IS NOT NULL), parent_id, name
            """
        )
        rows = cursor.fetchall()
        return [row_to_dict(row) for row in rows]


@app.post("/categories/unified")
async def create_unified_category(
    name: str = Body(...),
    parent_id: Optional[int] = Body(None),
    user_id: int = Depends(get_current_user_id),
):
    """
    Создать наименование в ОБЕИХ таблицах одновременно
    """
    with db_session() as conn:
        # 1. Создать в expense_categories
        cursor = conn.execute(
            "INSERT INTO expense_categories (name, parent_id, is_active) VALUES (?, ?, 1)",
            (name, parent_id),
        )
        expense_id = cursor.lastrowid
        
        # 2. Создать в income_categories (БЕЗ parent_id, если его нет в таблице)
        try:
            conn.execute(
                "INSERT INTO income_categories (name, is_active) VALUES (?, 1)",
                (name,),
            )
        except Exception as e:
            print(f"Не удалось создать в income_categories: {e}")
        
        # 3. Вернуть созданную категорию из expense_categories
        row = conn.execute(
            "SELECT id, name, parent_id, is_active FROM expense_categories WHERE id = ?",
            (expense_id,),
        ).fetchone()
        
        return row_to_dict(row)


@app.put("/categories/unified/{category_id}")
async def update_unified_category(
    category_id: int,
    name: str = Body(...),
    parent_id: Optional[int] = Body(None),
    user_id: int = Depends(get_current_user_id),
):
    """
    Обновить наименование в ОБЕИХ таблицах одновременно
    Обновляем по ID в expense_categories и по ИМЕНИ в income_categories
    """
    with db_session() as conn:
        # 1. Получить старое имя из expense_categories
        old_row = conn.execute(
            "SELECT name FROM expense_categories WHERE id = ?",
            (category_id,),
        ).fetchone()
        
        if not old_row:
            raise HTTPException(status_code=404, detail="Category not found")
        
        old_name = old_row['name']
        
        # 2. Обновить в expense_categories по ID
        conn.execute(
            "UPDATE expense_categories SET name = ?, parent_id = ? WHERE id = ?",
            (name, parent_id, category_id),
        )
        
        # 3. Обновить в income_categories по СТАРОМУ ИМЕНИ
        try:
            conn.execute(
                "UPDATE income_categories SET name = ? WHERE name = ?",
                (name, old_name),
            )
        except Exception as e:
            print(f"Не удалось обновить в income_categories: {e}")
        
        # 4. Вернуть обновлённую категорию
        row = conn.execute(
            "SELECT id, name, parent_id, is_active FROM expense_categories WHERE id = ?",
            (category_id,),
        ).fetchone()
        
        return row_to_dict(row)


@app.delete("/categories/unified/{category_id}")
async def archive_unified_category(
    category_id: int,
    user_id: int = Depends(get_current_user_id)
):
    """
    Архивировать наименование в ОБЕИХ таблицах одновременно
    """
    with db_session() as conn:
        # 1. Получить имя категории
        row = conn.execute(
            "SELECT name FROM expense_categories WHERE id = ?",
            (category_id,),
        ).fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Category not found")
        
        category_name = row['name']
        
        # 2. Архивировать в expense_categories по ID
        conn.execute(
            "UPDATE expense_categories SET is_active = 0 WHERE id = ?",
            (category_id,),
        )
        
        # 3. Архивировать в income_categories по ИМЕНИ
        try:
            conn.execute(
                "UPDATE income_categories SET is_active = 0 WHERE name = ?",
                (category_name,),
            )
        except Exception as e:
            print(f"Не удалось архивировать в income_categories: {e}")
        
        return {"success": True, "message": f"Archived '{category_name}' in both tables"}


# ==================
# Управление счетами
# ==================
@app.get("/accounts/all")
async def get_all_accounts(user_id: int = Depends(get_current_user_id)):
    with db_session() as conn:
        # УБРАНА фильтрация по user_id
        cursor = conn.execute(
            """
            SELECT id, name, type, is_active 
            FROM accounts
            WHERE is_active = 1 
            ORDER BY name
            """
        )
        rows = cursor.fetchall()
        return [row_to_dict(row) for row in rows]


@app.post("/accounts")
async def create_account(
    name: str = Body(...),
    type: str = Body(...),
    user_id: int = Depends(get_current_user_id),
):
    with db_session() as conn:
        cursor = conn.execute(
            "INSERT INTO accounts (name, type, is_active) VALUES (?, ?, 1)",
            (name, type),
        )
        new_id = cursor.lastrowid
        row = conn.execute(
            "SELECT id, name, type, is_active FROM accounts WHERE id = ?",
            (new_id,),
        ).fetchone()
        return row_to_dict(row)


@app.put("/accounts/{account_id}")
async def update_account(
    account_id: int,
    name: str = Body(...),
    type: str = Body(...),
    user_id: int = Depends(get_current_user_id),
):
    with db_session() as conn:
        conn.execute(
            "UPDATE accounts SET name = ?, type = ? WHERE id = ?",
            (name, type, account_id),
        )
        row = conn.execute(
            "SELECT id, name, type, is_active FROM accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
        return row_to_dict(row)


@app.delete("/accounts/{account_id}")
async def archive_account(account_id: int, user_id: int = Depends(get_current_user_id)):
    with db_session() as conn:
        conn.execute(
            "UPDATE accounts SET is_active = 0 WHERE id = ?",
            (account_id,),
        )
        return {"success": True}


# ==============================
# Управление блоками аналитики
# ==============================
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

@app.get("/analytics/blocks", response_model=List[AnalyticBlockInDB])
async def get_analytic_blocks(user_id: int = Depends(get_current_user_id)):
    with db_session() as conn:
        cursor = conn.execute(
            "SELECT * FROM analytic_blocks WHERE is_active = 1 ORDER BY sort_order, name"
        )
        rows = cursor.fetchall()
        return [row_to_dict(row) for row in rows]

@app.post("/analytics/blocks", response_model=AnalyticBlockInDB)
async def create_analytic_block(block: AnalyticBlock, user_id: int = Depends(get_current_user_id)):
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO analytic_blocks 
             (code, name, icon, color, threshold_good, threshold_warning, sort_order, is_active) 
             VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (block.code, block.name, block.icon, block.color, 
             block.threshold_good, block.threshold_warning, block.sort_order),
        )
        new_id = cursor.lastrowid
        row = conn.execute(
            "SELECT * FROM analytic_blocks WHERE id = ?", (new_id,)
        ).fetchone()
        return row_to_dict(row)

@app.put("/analytics/blocks/{block_id}", response_model=AnalyticBlockInDB)
async def update_analytic_block(
    block_id: int, 
    block: AnalyticBlock, 
    user_id: int = Depends(get_current_user_id)):
    with db_session() as conn:
        conn.execute(
            """
            UPDATE analytic_blocks 
             SET code = ?, name = ?, icon = ?, color = ?, 
                 threshold_good = ?, threshold_warning = ?, sort_order = ?
            WHERE id = ?
            """,
            (block.code, block.name, block.icon, block.color, 
             block.threshold_good, block.threshold_warning, block.sort_order, block_id),
        )
        row = conn.execute(
            "SELECT * FROM analytic_blocks WHERE id = ?", (block_id,)
        ).fetchone()
        return row_to_dict(row)

@app.delete("/analytics/blocks/{block_id}")
async def delete_analytic_block(block_id: int, user_id: int = Depends(get_current_user_id)):
    with db_session() as conn:
        conn.execute(
            "UPDATE analytic_blocks SET is_active = 0 WHERE id = ?", (block_id,)
        )
        return {"success": True}

@app.get("/analytics/accounts/{account_id}/balance")
async def get_account_balance(account_id: int, user_id: int = Depends(get_current_user_id)):
    """
    Получить текущий баланс счёта в реальном времени
    """
    with db_session() as conn:
        # Получить сумму всех приходов на счёт
        income_cursor = conn.execute("""
            SELECT COALESCE(SUM(amount), 0) as total
            FROM timeline
            WHERE type = 'income' AND account_id = ?
        """, (account_id,))
        total_income = income_cursor.fetchone()[0]
        
        # Получить сумму всех расходов со счёта
        expense_cursor = conn.execute("""
            SELECT COALESCE(SUM(amount), 0) as total
            FROM timeline
            WHERE type = 'expense' AND account_id = ?
        """, (account_id,))
        total_expense = expense_cursor.fetchone()[0]
        
        # Получить входящие переводы (to_account_id)
        transfer_in_cursor = conn.execute("""
            SELECT COALESCE(SUM(amount), 0) as total
            FROM timeline
            WHERE type IN ('transfer', 'incasation') AND to_account_id = ?
        """, (account_id,))
        transfer_in = transfer_in_cursor.fetchone()[0]
        
        # Получить исходящие переводы (from_account_id)
        transfer_out_cursor = conn.execute("""
            SELECT COALESCE(SUM(amount), 0) as total
            FROM timeline
            WHERE type IN ('transfer', 'incasation') AND from_account_id = ?
        """, (account_id,))
        transfer_out = transfer_out_cursor.fetchone()[0]
        
        # Баланс = приходы + входящие переводы - расходы - исходящие переводы
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
    """
    Получить движения по счёту за период
    """
    with db_session() as conn:
        # Формируем WHERE clause в зависимости от параметров
        if start_date and end_date:
            date_filter = "AND date >= ? AND date <= ?"
            date_params = (start_date, end_date)
        elif days:
            date_filter = "AND date >= date('now', ?)"
            date_params = (f'-{days} days',)
        else:
            date_filter = ""
            date_params = ()
        
        # Получить все операции связанные со счётом
        query = f"""
            SELECT 
                id, date, type, amount, description, category_id,
                from_account_id, to_account_id, commission_amount
            FROM timeline
            WHERE (
                (type = 'income' AND account_id = ?)
                OR (type = 'expense' AND account_id = ?)
                OR (type IN ('transfer', 'incasation') AND (from_account_id = ? OR to_account_id = ?))
            )
            {date_filter}
            ORDER BY date DESC, id DESC
        """
        
        params = (account_id, account_id, account_id, account_id) + date_params
        cursor = conn.execute(query, params)
        
        operations = []
        for row in cursor.fetchall():
            op = row_to_dict(row)
            
            # Определить влияние на баланс
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
        
        # Статистика за период
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
    """
    Получить данные для графика динамики баланса счёта
    """
    with db_session() as conn:
        # Формируем WHERE clause
        if start_date and end_date:
            date_filter = "AND date >= ? AND date <= ?"
            date_params = (start_date, end_date)
        elif days:
            date_filter = "AND date >= date('now', ?)"
            date_params = (f'-{days} days',)
        else:
            date_filter = ""
            date_params = ()
        
        # Получить операции
        query = f"""
            SELECT date, type, amount, from_account_id, to_account_id, commission_amount
            FROM timeline
            WHERE (
                (type = 'income' AND account_id = ?)
                OR (type = 'expense' AND account_id = ?)
                OR (type IN ('transfer', 'incasation') AND (from_account_id = ? OR to_account_id = ?))
            )
            {date_filter}
            ORDER BY date ASC, id ASC
        """
        
        params = (account_id, account_id, account_id, account_id) + date_params
        cursor = conn.execute(query, params)
        
        # Группировка по дням
        daily_data = {}
        for row in cursor.fetchall():
            date = row['date']
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
        
        # Формируем массив с накопительным балансом
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


# --- Health endpoints (useful for Railway healthchecks) ---
@app.get("/")
def root():
    return {"status": "ok", "message": "Finance API v1.0"}


@app.get("/health")
def health():
    return {"status": "healthy"}



# ========== КАССИРСКИЕ ОТЧЁТЫ ==========

@app.get("/cashier/locations")
async def get_locations():
    """Получить список точек продаж"""
    with db_session() as conn:
        cursor = conn.execute(
            """
            SELECT id, name, address, is_active 
            FROM locations 
            WHERE is_active = 1
            ORDER BY name
            """
        )
        locations = cursor.fetchall()
        return [row_to_dict(loc) for loc in locations]


@app.get("/cashier/payment-methods")
async def get_payment_methods():
    """Получить методы оплаты"""
    with db_session() as conn:
        cursor = conn.execute(
            """
            SELECT id, name, method_type, commission_percent, is_active 
            FROM payment_methods 
            WHERE is_active = 1
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
        # Проверяем существование отчёта
        existing = conn.execute(
            """
            SELECT id FROM cashier_reports 
            WHERE report_date = ? AND location_id = ?
            """,
            (report_data['report_date'], report_data['location_id'])
        ).fetchone()

        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Отчёт за {report_data['report_date']} для этой точки уже существует"
            )

        # Создаём отчёт
        cursor = conn.execute(
            """
            INSERT INTO cashier_reports (
                report_date, location_id, user_id, total_sales,
                cash_actual, status, closed_at
            ) VALUES (?, ?, ?, ?, ?, 'closed', CURRENT_TIMESTAMP)
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

        # Добавляем платежи
        for payment in report_data.get('payments', []):
            if payment['amount'] > 0:
                # Получаем процент комиссии
                method = conn.execute(
                    "SELECT commission_percent FROM payment_methods WHERE id = ?",
                    (payment['payment_method_id'],)
                ).fetchone()

                commission_percent = method['commission_percent'] if method else 0
                commission_amount = payment['amount'] * commission_percent / 100
                net_amount = payment['amount'] - commission_amount

                conn.execute(
                    """
                    INSERT INTO cashier_report_payments (
                        report_id, payment_method_id, amount, 
                        commission_amount, net_amount
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (report_id, payment['payment_method_id'], 
                      payment['amount'], commission_amount, net_amount)
                )

                # Создаём income операцию в timeline (если метод не "наличные")
                method_info = conn.execute(
                    "SELECT name, method_type FROM payment_methods WHERE id = ?",
                    (payment['payment_method_id'],)
                ).fetchone()

                if method_info and method_info['method_type'] != 'cash':
                    # Находим категорию "Выручка" или создаём
                    income_cat = conn.execute(
                        "SELECT id FROM income_categories WHERE name = 'Выручка' LIMIT 1"
                    ).fetchone()

                    if not income_cat:
                        cur = conn.execute(
                            "INSERT INTO income_categories (name, is_active) VALUES ('Выручка', 1)"
                        )
                        income_cat_id = cur.lastrowid
                    else:
                        income_cat_id = income_cat['id']

                    # Находим счёт или создаём по типу метода
                    account = conn.execute(
                        "SELECT id FROM accounts WHERE name LIKE ? LIMIT 1",
                        (f"%{method_info['name']}%",)
                    ).fetchone()

                    if not account:
                        # Создаём базовый банковский счёт
                        cur = conn.execute(
                            "INSERT INTO accounts (name, type, account_type, is_active) VALUES (?, 'bank', 'bank', 1)",
                            (method_info['name'],)
                        )
                        account_id = cur.lastrowid
                    else:
                        account_id = account['id']

                    # Создаём income операцию
                    conn.execute("""
                        INSERT INTO timeline (
                            date, type, category_id, account_id,
                            amount, description, user_id
                        ) VALUES (?, 'income', ?, ?, ?, ?, ?)
                    """, (
                        report_data['report_date'],
                        income_cat_id,
                        account_id,
                        net_amount,
                        f"Выручка ({method_info['name']}) - Отчёт кассира",
                        current_user_id
                    ))

        # Добавляем расходы
        for expense in report_data.get('expenses', []):
            if expense['amount'] > 0:
                conn.execute("""
                    INSERT INTO cashier_report_expenses (
                        report_id, category_id, amount, description
                    ) VALUES (?, ?, ?, ?)
                """, (report_id, expense.get('category_id'), 
                      expense['amount'], expense.get('description', '')))

                # Создаём expense операцию в timeline
                if expense.get('category_id'):
                    cash_account = conn.execute(
                        "SELECT id FROM accounts WHERE type = 'cash' LIMIT 1"
                    ).fetchone()

                    if cash_account:
                        conn.execute("""
                            INSERT INTO timeline (
                                date, type, category_id, account_id,
                                amount, description, user_id
                            ) VALUES (?, 'expense', ?, ?, ?, ?, ?)
                        """, (
                            report_data['report_date'],
                            expense['category_id'],
                            cash_account['id'],
                            expense['amount'],
                            expense.get('description', 'Расход из отчёта кассира'),
                            current_user_id
                        ))

        # Добавляем прочие приходы
        for income in report_data.get('incomes', []):
            if income['amount'] > 0:
                conn.execute("""
                    INSERT INTO cashier_report_income (
                        report_id, category_id, amount, description
                    ) VALUES (?, ?, ?, ?)
                """, (report_id, income.get('category_id'), 
                      income['amount'], income.get('description', '')))

                # Создаём income операцию в timeline
                if income.get('category_id'):
                    cash_account = conn.execute(
                        "SELECT id FROM accounts WHERE type = 'cash' LIMIT 1"
                    ).fetchone()

                    if cash_account:
                        conn.execute("""
                            INSERT INTO timeline (
                                date, type, category_id, account_id,
                                amount, description, user_id
                            ) VALUES (?, 'income', ?, ?, ?, ?, ?)
                        """, (
                            report_data['report_date'],
                            income['category_id'],
                            cash_account['id'],
                            income['amount'],
                            income.get('description', 'Приход из отчёта кассира'),
                            current_user_id
                        ))

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
            query += " AND cr.report_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND cr.report_date <= ?"
            params.append(end_date)
        if location_id:
            query += " AND cr.location_id = ?"
            params.append(location_id)
        query += " ORDER BY cr.report_date DESC, cr.created_at DESC"

        reports = conn.execute(query, params).fetchall()
        return [row_to_dict(r) for r in reports]


@app.get("/cashier/reports/{report_id}")
async def get_cashier_report_details(
    report_id: int,
    current_user_id: int = Depends(get_current_user_id)
):
    """Получить детали отчёта"""
    with db_session() as conn:
        report = conn.execute("""
            SELECT 
                cr.*,
                l.name as location_name,
                u.full_name as cashier_name,
                u.username as cashier_username
            FROM cashier_reports cr
            LEFT JOIN locations l ON cr.location_id = l.id
            LEFT JOIN users u ON cr.user_id = u.id
            WHERE cr.id = ?
        """, (report_id,)).fetchone()

        if not report:
            raise HTTPException(status_code=404, detail="Отчёт не найден")

        result = row_to_dict(report)

        payments = conn.execute("""
            SELECT 
                crp.*,
                pm.name as payment_method_name,
                pm.method_type
            FROM cashier_report_payments crp
            LEFT JOIN payment_methods pm ON crp.payment_method_id = pm.id
            WHERE crp.report_id = ?
        """, (report_id,)).fetchall()
        result['payments'] = [row_to_dict(p) for p in payments]

        expenses = conn.execute("""
            SELECT 
                cre.*,
                ec.name as category_name
            FROM cashier_report_expenses cre
            LEFT JOIN expense_categories ec ON cre.category_id = ec.id
            WHERE cre.report_id = ?
        """, (report_id,)).fetchall()
        result['expenses'] = [row_to_dict(e) for e in expenses]

        incomes = conn.execute("""
            SELECT 
                cri.*,
                ic.name as category_name
            FROM cashier_report_income cri
            LEFT JOIN income_categories ic ON cri.category_id = ic.id
            WHERE cri.report_id = ?
        """, (report_id,)).fetchall()
        result['incomes'] = [row_to_dict(i) for i in incomes]

        return result