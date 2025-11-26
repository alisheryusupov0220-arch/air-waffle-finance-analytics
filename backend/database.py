"""
Air Waffle Finance - Database Helper Functions
Правильные функции для работы с PostgreSQL
"""
import os
import psycopg2
import psycopg2.extras
from typing import Optional, List, Dict, Any, Tuple


def get_db_connection():
    """Получить подключение к PostgreSQL"""
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        raise Exception("DATABASE_URL not found in environment variables")
    
    # Render fix: postgres:// -> postgresql://
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    try:
        conn = psycopg2.connect(database_url)
        return conn
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        raise


def execute_query(
    query: str,
    params: Optional[Tuple] = None,
    fetch_one: bool = False,
    fetch_all: bool = False,
    return_id: bool = False
) -> Any:
    """
    Выполнить SQL запрос с автоматическим управлением соединением
    
    Args:
        query: SQL запрос (с %s placeholders)
        params: Параметры для запроса
        fetch_one: Вернуть одну строку как dict
        fetch_all: Вернуть все строки как list[dict]
        return_id: Вернуть ID вставленной записи (для INSERT)
    
    Returns:
        dict, list[dict], int или None
    
    Examples:
        # SELECT один
        user = execute_query("SELECT * FROM users WHERE id = %s", (user_id,), fetch_one=True)
        
        # SELECT все
        users = execute_query("SELECT * FROM users WHERE is_active = %s", (True,), fetch_all=True)
        
        # INSERT с возвратом ID
        new_id = execute_query(
            "INSERT INTO users (telegram_id, full_name) VALUES (%s, %s) RETURNING id",
            (123456, "John"),
            return_id=True
        )
        
        # UPDATE/DELETE
        execute_query("UPDATE users SET is_active = %s WHERE id = %s", (False, user_id))
    """
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        result = None
        
        if return_id:
            # Для INSERT ... RETURNING id
            result = cursor.fetchone()
            result = result['id'] if result else None
        elif fetch_one:
            result = cursor.fetchone()
        elif fetch_all:
            result = cursor.fetchall()
        
        conn.commit()
        return result
        
    except Exception as e:
        conn.rollback()
        print(f"❌ SQL Error: {e}")
        print(f"Query: {query}")
        print(f"Params: {params}")
        raise
    finally:
        cursor.close()
        conn.close()


def execute_insert(
    table: str,
    data: Dict[str, Any],
    return_id: bool = True
) -> Optional[int]:
    """
    Вставить запись в таблицу (упрощённый helper)
    
    Args:
        table: Название таблицы
        data: Словарь {column: value}
        return_id: Вернуть ID новой записи
    
    Returns:
        ID новой записи или None
    
    Example:
        user_id = execute_insert('users', {
            'telegram_id': 123456,
            'full_name': 'John Doe',
            'role': 'cashier'
        })
    """
    columns = ', '.join(data.keys())
    placeholders = ', '.join(['%s'] * len(data))
    values = tuple(data.values())
    
    query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
    
    if return_id:
        query += " RETURNING id"
        return execute_query(query, values, return_id=True)
    else:
        execute_query(query, values)
        return None


def execute_update(
    table: str,
    data: Dict[str, Any],
    where: str,
    where_params: Tuple
) -> None:
    """
    Обновить записи в таблице
    
    Args:
        table: Название таблицы
        data: Словарь {column: new_value}
        where: WHERE условие с %s placeholders
        where_params: Параметры для WHERE
    
    Example:
        execute_update(
            'users',
            {'full_name': 'New Name', 'updated_at': 'NOW()'},
            'id = %s',
            (user_id,)
        )
    """
    set_clause = ', '.join([f"{col} = %s" for col in data.keys()])
    values = tuple(data.values()) + where_params
    
    query = f"UPDATE {table} SET {set_clause} WHERE {where}"
    execute_query(query, values)


def execute_delete(
    table: str,
    where: str,
    where_params: Tuple
) -> None:
    """
    Удалить записи из таблицы
    
    Args:
        table: Название таблицы
        where: WHERE условие с %s placeholders
        where_params: Параметры для WHERE
    
    Example:
        execute_delete('users', 'id = %s', (user_id,))
    """
    query = f"DELETE FROM {table} WHERE {where}"
    execute_query(query, where_params)


def get_one(table: str, where: str, where_params: Tuple) -> Optional[Dict]:
    """
    Получить одну запись
    
    Example:
        user = get_one('users', 'telegram_id = %s', (123456,))
    """
    query = f"SELECT * FROM {table} WHERE {where}"
    return execute_query(query, where_params, fetch_one=True)


def get_all(
    table: str,
    where: Optional[str] = None,
    where_params: Optional[Tuple] = None,
    order_by: Optional[str] = None,
    limit: Optional[int] = None
) -> List[Dict]:
    """
    Получить несколько записей
    
    Example:
        users = get_all('users', 'is_active = %s', (True,), order_by='created_at DESC', limit=10)
    """
    query = f"SELECT * FROM {table}"
    
    if where:
        query += f" WHERE {where}"
    
    if order_by:
        query += f" ORDER BY {order_by}"
    
    if limit:
        query += f" LIMIT {limit}"
    
    return execute_query(query, where_params, fetch_all=True)


# Для обратной совместимости
def row_to_dict(row):
    """
    Конвертировать RealDictRow в обычный dict
    (На самом деле не нужно - RealDictRow уже ведёт себя как dict)
    """
    if row is None:
        return None
    return dict(row)
