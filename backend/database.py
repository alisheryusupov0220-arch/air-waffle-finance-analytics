import os
from typing import Any, Iterable, Optional
import psycopg2
import psycopg2.extras
from contextlib import contextmanager

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def get_db_connection():
    """Создать подключение к PostgreSQL по переменной DATABASE_URL."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    return psycopg2.connect(database_url)


def _run_query(query: str, params: Optional[Iterable[Any]] = None, fetch: Optional[str] = None):
    """Внутренняя утилита выполнения SQL с управлением ресурсами."""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        pg_query = query.replace("?", "%s")
        if params is not None:
            cursor.execute(pg_query, params)
        else:
            cursor.execute(pg_query)

        if fetch == "one":
            result = cursor.fetchone()
        elif fetch == "all":
            result = cursor.fetchall()
        else:
            result = None

        conn.commit()
        cursor.close()
        conn.close()
        return result
    except Exception:
        conn.rollback()
        cursor.close()
        conn.close()
        raise


def execute_query(query: str, params: Optional[Iterable[Any]] = None, fetch_one: bool = False, fetch_all: bool = False):
    """Выполнить SQL запрос. Управляет коннектом и курсором, возвращает fetch_one/fetch_all по флагам."""
    fetch = "one" if fetch_one else "all" if fetch_all else None
    return _run_query(query, params, fetch)


def execute_insert(query: str, params: Optional[Iterable[Any]] = None):
    """Выполнить INSERT. Для получения id используйте RETURNING и get_one/execute_query(fetch_one=True)."""
    return _run_query(query, params, fetch=None)


def execute_update(query: str, params: Optional[Iterable[Any]] = None):
    """Выполнить UPDATE. Возвращаемое значение не используется; для контроля используйте RETURNING."""
    return _run_query(query, params, fetch=None)


def execute_delete(query: str, params: Optional[Iterable[Any]] = None):
    """Выполнить DELETE. Возвращаемое значение не используется; для контроля используйте RETURNING."""
    return _run_query(query, params, fetch=None)


def get_one(query: str, params: Optional[Iterable[Any]] = None):
    """Получить одну строку результата как dict или None."""
    return _run_query(query, params, fetch="one")


def get_all(query: str, params: Optional[Iterable[Any]] = None):
    """Получить все строки результата как список dict."""
    return _run_query(query, params, fetch="all")

