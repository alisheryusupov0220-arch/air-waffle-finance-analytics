# AIR WAFFLE FINANCE - ТЕКУЩЕЕ СОСТОЯНИЕ ПРОЕКТА

## ДАТА АНАЛИЗА
Sunday, November 23, 2025

## ПРОБЛЕМЫ
1. Railway nixpacks не собирается (ошибка с pip)
2. Локально не запускается (ошибка с зависимостями)
3. Код переключался между SQLite и PostgreSQL
4. Несогласованность конфигурации

## BACKEND ФАЙЛЫ
Вывод `ls -la backend/`:

```text
total 376
drwxr-xr-x@ 19 alisheryusupov2002  staff    608 Nov 23 19:51 .
drwxr-xr-x@ 67 alisheryusupov2002  staff   2144 Nov 23 19:00 ..
-rw-r--r--@  1 alisheryusupov2002  staff   6148 Nov 18 15:02 .DS_Store
-rw-r--r--@  1 alisheryusupov2002  staff     81 Nov 23 18:44 .dockerignore
-rw-r--r--@  1 alisheryusupov2002  staff    150 Nov 23 19:51 .env
-rw-r--r--@  1 alisheryusupov2002  staff      6 Nov 23 19:55 .gitignore
-rw-r--r--@  1 alisheryusupov2002  staff    613 Nov 23 18:44 Dockerfile
-rw-r--r--@  1 alisheryusupov2002  staff     59 Nov 23 18:44 Procfile
drwxr-xr-x   7 alisheryusupov2002  staff    224 Nov 23 19:55 __pycache__
-rw-r--r--@  1 alisheryusupov2002  staff   8322 Nov 15 00:10 analytics.py
-rw-r--r--@  1 alisheryusupov2002  staff   1340 Nov 23 18:44 auth.py
-rw-r--r--@  1 alisheryusupov2002  staff   5357 Nov 23 18:44 database.py
-rw-r--r--   1 alisheryusupov2002  staff  57344 Nov 22 20:52 finance_v5.db
-rw-r--r--@  1 alisheryusupov2002  staff   1075 Nov 23 18:44 init_db.py
-rw-r--r--@  1 alisheryusupov2002  staff   7036 Nov 23 18:44 init_db_postgres.py
-rw-r--r--@  1 alisheryusupov2002  staff  58010 Nov 23 19:55 main.py
-rw-r--r--@  1 alisheryusupov2002  staff    168 Nov 23 18:44 nixpacks.toml
-rw-r--r--@  1 alisheryusupov2002  staff    127 Nov 23 19:55 requirements.txt
drwxr-xr-x   7 alisheryusupov2002  staff    224 Nov  8 22:06 venv
```

## ТЕКУЩИЕ ЗАВИСИМОСТИ
Содержимое `backend/requirements.txt`:

```text
fastapi==0.109.0
uvicorn[standard]==0.27.0
python-multipart==0.0.6
pydantic==2.6.0
psycopg2-binary==2.9.9
python-dotenv==1.0.0
```

## КОНФИГУРАЦИОННЫЕ ФАЙЛЫ
- nixpacks.toml: ЕСТЬ
- Procfile: ЕСТЬ
- Dockerfile: ЕСТЬ
- .env: ЕСТЬ

## ПОСЛЕДНИЕ ИЗМЕНЕНИЯ
Последние 5 коммитов:

```text
b07cf74 Configure for Supabase PostgreSQL
e8abf95 Fix nixpacks configuration for backend
ec93d4a Fix: Complete PostgreSQL integration with proper API
4d75a00 CRITICAL: Remove all SQLite code, force PostgreSQL only
545d77a Add PostgreSQL support for Railway
```

## БАЗА ДАННЫХ
- Тип на продакшне: PostgreSQL
- Тип локально: PostgreSQL
- Файлы БД:

```text
./backend/finance_v5.db
./finance_v5.db
```

## ЧТО РАБОТАЛО РАНЬШЕ
Исторически локально использовалась SQLite (в т.ч. Railway Volume для прод), затем проект переведён на PostgreSQL (Supabase/Railway). Следы SQLite (файлы .db, `backend/database.py`) ещё присутствуют, но основной API переведён на PostgreSQL.

## РЕКОМЕНДАЦИИ
- Убедиться, что `backend/.env` содержит корректный Supabase `DATABASE_URL`.
- Мигрировать исторические данные из SQLite в PostgreSQL (при необходимости).
- Постепенно удалить/законсервировать устаревший код SQLite (`backend/database.py`) или оставить как совместимость, но не использовать в API.
- Проверить деплой на Railway/Vercel: nixpacks/Dockerfile синхронизированы, зависимости фиксированы.
- Добавить простые миграции/скрипты и healthchecks для стабильного старта.

---

## Приложение: Полные выводы команд

### 1) СТРУКТУРА ПРОЕКТА / BACKEND / FRONTEND

```text
=== СТРУКТУРА ПРОЕКТА ===
(tree не установлен, используем find)
.
./telegram_bot.py
./timeline_ui.py
./sync_poster.py
./ФИНАЛЬНАЯ_ВЕРСИЯ.txt
./.DS_Store
./permissions_ui.py
./migration_transfers.sql
./Instructions test
./Instructions test/CURSOR_QUICK_ADD.md
./Instructions test/CURSOR_FIX_DESIGN.md
./Instructions test/CURSOR_FIX_AUTH.md
./Instructions test/CURSOR_TIMELINE_READONLY.md
./CURSOR_MINIAPP_FULL.md
./requirements.txt
./TELEGRAM_БОТ.txt
./poster_integration
./poster_integration/POSTER_README.md
./poster_integration/POSTER_DOCUMENTATION.md
./poster_integration/sync_poster.py
./poster_integration/CURSOR_POSTER_PROMPT.txt
./poster_integration/poster_scheduler.py
./poster_integration/poster_settings_ui.py
./poster_integration/api_categories_poster.py
./poster_integration/migration_poster.sql
./poster_integration/FINAL_README.md
./miniapp-starter
./miniapp-starter/index.html
./miniapp-starter/tailwind.config.js
./miniapp-starter/vite.config.js
./miniapp-starter/package.json
./miniapp-starter/src
./miniapp-starter/src/index.css
./miniapp-starter/src/components
./miniapp-starter/src/hooks
./miniapp-starter/src/services
./config.json
./settings_gui.py
./timeline_window.py
./permissions_manager.py
./quick_add_window.py
./bot_db.py
./backup_before_balance_fix_20251031_151732.zip
./migration.sql
./migration_permissions.sql
./integration_package
./integration_package/add_categories.sql
./integration_package/ИНСТРУКЦИЯ_ВНЕДРЕНИЕ.md
./integration_package/CURSOR_INSTRUCTIONS.md
./integration_package/README.md
./integration_package/migration_hierarchy.sql
./integration_package/analytics.py
./integration_package/CURSOR_PROMPT.txt
./integration_package/add_categories_from_sheets.py
./integration_package/FINAL_README.md
./integration_package/category_manager.py
./backend
./backend/auth.py
./backend/nixpacks.toml
./backend/.DS_Store
./backend/requirements.txt
./backend/Dockerfile
./backend/database.py
./backend/init_db_postgres.py
./backend/.dockerignore
./backend/.gitignore
./backend/.env
./backend/analytics.py
./backend/Procfile
./backend/main.py
./backend/finance_v5.db
./backend/init_db.py
./ИНСТРУКЦИЯ_V5.txt
./telegram_bot_mini_app.py
./poster_scheduler.py
./run.sh
./login_window.py
./README.md
./database_v5.py
./migration_timeline.sql
./diagnose.py
./api_server.py
./.gitignore
./package-lock.json
./package.json
./cashier_daily_report.py
./AIR_WAFFLE_PROJECT_EXPORT.md
./poster_settings_ui.py
./GUI_ИНСТРУКЦИЯ.txt
./fix_categories_tables.py
./.gitattributes
./poster_integration_fixed
./poster_integration_fixed/UPDATE_INSTRUCTIONS.md
./poster_integration_fixed/POSTER_README.md
./poster_integration_fixed/POSTER_DOCUMENTATION.md
./poster_integration_fixed/sync_poster.py
./poster_integration_fixed/POSTER_FIXES.md
./poster_integration_fixed/CURSOR_POSTER_PROMPT.txt
./poster_integration_fixed/poster_scheduler.py
./poster_integration_fixed/poster_settings_ui.py
./poster_integration_fixed/api_categories_poster.py
./poster_integration_fixed/migration_poster.sql
./poster_integration_fixed/FINAL_README.md
./settings.py
./api_categories_poster.py
./telegram_bot_simple.py
./mini_app.html
./miniapp
./miniapp/.DS_Store
./miniapp/frontend
./miniapp/frontend/.vercel
./miniapp/frontend/nixpacks.toml
./miniapp/frontend/.env.production
./miniapp/frontend/index.html
./miniapp/frontend/tailwind.config.js
./miniapp/frontend/.DS_Store
./miniapp/frontend/vercel.json
./miniapp/frontend/Dockerfile
./miniapp/frontend/vite.config.js
./miniapp/frontend/.dockerignore
./miniapp/frontend/public
./miniapp/frontend/.gitignore
./miniapp/frontend/package-lock.json
./miniapp/frontend/package.json
./miniapp/frontend/.env
./miniapp/frontend/postcss.config.js
./miniapp/frontend/src
./analytics.py
./Procfile
./setup_v5.py
./test_api.py
./.vscode
./.vscode/settings.json
./finance_v5.db
./category_manager.py
./migrate_to_timeline.py
./manager_view.py
./main_app.py
./finance_v5.d
./validation.py

=== BACKEND ФАЙЛЫ ===
total 376
drwxr-xr-x@ 19 alisheryusupov2002  staff    608 Nov 23 19:51 .
drwxr-xr-x@ 67 alisheryusupov2002  staff   2144 Nov 23 19:00 ..
-rw-r--r--@  1 alisheryusupov2002  staff   6148 Nov 18 15:02 .DS_Store
-rw-r--r--@  1 alisheryusupov2002  staff     81 Nov 23 18:44 .dockerignore
-rw-r--r--@  1 alisheryusupov2002  staff    150 Nov 23 19:51 .env
-rw-r--r--@  1 alisheryusupov2002  staff      6 Nov 23 19:55 .gitignore
-rw-r--r--@  1 alisheryusupov2002  staff    613 Nov 23 18:44 Dockerfile
-rw-r--r--@  1 alisheryusupov2002  staff     59 Nov 23 18:44 Procfile
drwxr-xr-x   7 alisheryusupov2002  staff    224 Nov 23 19:55 __pycache__
-rw-r--r--@  1 alisheryusupov2002  staff   8322 Nov 15 00:10 analytics.py
-rw-r--r--@  1 alisheryusupov2002  staff   1340 Nov 23 18:44 auth.py
-rw-r--r--@  1 alisheryusupov2002  staff   5357 Nov 23 18:44 database.py
-rw-r--r--   1 alisheryusupov2002  staff  57344 Nov 22 20:52 finance_v5.db
-rw-r--r--@  1 alisheryusupov2002  staff   1075 Nov 23 18:44 init_db.py
-rw-r--r--@  1 alisheryusupov2002  staff   7036 Nov 23 18:44 init_db_postgres.py
-rw-r--r--@  1 alisheryusupov2002  staff  58010 Nov 23 19:55 main.py
-rw-r--r--@  1 alisheryusupov2002  staff    168 Nov 23 18:44 nixpacks.toml
-rw-r--r--@  1 alisheryusupov2002  staff    127 Nov 23 19:55 requirements.txt
drwxr-xr-x   7 alisheryusupov2002  staff    224 Nov  8 22:06 venv

=== FRONTEND ФАЙЛЫ ===
total 408
drwxr-xr-x@  21 alisheryusupov2002  staff     672 Nov 22 19:46 .
drwxr-xr-x@   4 alisheryusupov2002  staff     128 Nov 11 21:41 ..
-rw-r--r--@   1 alisheryusupov2002  staff    6148 Nov 15 19:46 .DS_Store
-rw-r--r--@   1 alisheryusupov2002  staff     163 Nov 23 18:44 .dockerignore
-rw-r--r--@   1 alisheryusupov2002  staff      35 Nov  8 21:28 .env
-rw-r--r--@   1 alisheryusupov2002  staff      60 Nov 23 18:44 .env.production
-rw-r--r--    1 alisheryusupov2002  staff       8 Nov 22 19:42 .gitignore
drwxr-xr-x    4 alisheryusupov2002  staff     128 Nov 22 19:42 .vercel
-rw-r--r--@   1 alisheryusupov2002  staff     747 Nov 23 18:44 Dockerfile
drwxr-xr-x@   4 alisheryusupov2002  staff     128 Nov 22 19:46 dist
-rw-r--r--@   1 alisheryusupov2002  staff     390 Nov  8 15:42 index.html
-rw-r--r--@   1 alisheryusupov2002  staff     162 Nov 23 18:44 nixpacks.toml
drwxr-xr-x@ 231 alisheryusupov2002  staff    7392 Nov 22 19:46 node_modules
-rw-r--r--@   1 alisheryusupov2002  staff  150657 Nov 22 19:46 package-lock.json
-rw-r--r--@   1 alisheryusupov2002  staff     566 Nov 23 18:44 package.json
-rw-r--r--@   1 alisheryusupov2002  staff      81 Nov  8 16:49 postcss.config.js
drwxr-xr-x@   2 alisheryusupov2002  staff      64 Nov  8 15:42 public
drwxr-xr-x@  11 alisheryusupov2002  staff     352 Nov 11 22:18 src
-rw-r--r--@   1 alisheryusupov2002  staff     322 Nov  8 15:42 tailwind.config.js
-rw-r--r--@   1 alisheryusupov2002  staff     184 Nov 23 18:44 vercel.json
-rw-r--r--@   1 alisheryusupov2002  staff     180 Nov  8 15:42 vite.config.js
```

### 2) BACKEND КОНФИГУРАЦИЯ

```text
=== REQUIREMENTS.TXT ===
fastapi==0.109.0
uvicorn[standard]==0.27.0
python-multipart==0.0.6
pydantic==2.6.0
psycopg2-binary==2.9.9
python-dotenv==1.0.0

=== MAIN.PY (первые 100 строк) ===
from dotenv import load_dotenv
load_dotenv()

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
from datetime import datetime, date
from pydantic import BaseModel, Field

# НЕ ИМПОРТИРУЕМ sqlite3! (PostgreSQL-only)

from auth import get_current_user_id

# --- Импорты из analytics.py ---
from analytics import dashboard, pivot_table, get_trend_data, get_cell_details
# -----------------------------


def get_db_connection():
    \"\"\"Подключение к Supabase PostgreSQL\"\"\"
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        raise Exception(\"DATABASE_URL not found! Check .env file or Railway environment variables\")
    
    try:
        conn = psycopg2.connect(database_url)
        return conn
    except Exception as e:
        print(f\"❌ Database connection failed: {e}\")
        print(f\"DATABASE_URL: {database_url[:50]}...\")
        raise


def execute_query(query, params=None, fetch_one=False, fetch_all=False):
    \"\"\"Выполнить SQL запрос в PostgreSQL\"\"\"
    import psycopg2.extras
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
        # PostgreSQL использует %s вместо ?
        pg_query = query.replace('?', '%s')
        
        if params:
            cursor.execute(pg_query, params)
        else:
            cursor.execute(pg_query)
        
        if fetch_one:
            result = cursor.fetchone()
        elif fetch_all:
            result = cursor.fetchall()
        else:
            result = None
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return result
        
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        print(f\"SQL Error: {e}\")
        print(f\"Query: {pg_query}\")
        raise e


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



=== NIXPACKS.TOML (если есть) ===
[phases.setup]
nixPkgs = [\"python311\", \"pip\"]

[phases.install]
cmds = [\"pip install -r requirements.txt\"]

[start]
cmd = \"uvicorn main:app --host 0.0.0.0 --port $PORT\"
=== PROCFILE (если есть) ===

web: uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}

=== DOCKERFILE (если есть) ===
FROM python:3.11-slim

WORKDIR /app

# Копируем requirements
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir --upgrade pip && \\
    pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY . .

# Railway передаёт PORT через переменную окружения
# Используем shell форму CMD для подстановки переменных
CMD uvicorn main:app --host 0.0.0.0 --port $PORT
# ВАЖНО: Убрал EXPOSE и ${PORT:-8000} — Railway сам управляет портами

=== .ENV (проверка наличия) ===
-rw-r--r--@ 1 alisheryusupov2002  staff  150 Nov 23 19:51 .env
ЕСТЬ (не показываем содержимое)
```

### 3) GIT ИСТОРИЯ

```text
=== ПОСЛЕДНИЕ 10 КОММИТОВ ===
b07cf74 Configure for Supabase PostgreSQL
e8abf95 Fix nixpacks configuration for backend
ec93d4a Fix: Complete PostgreSQL integration with proper API
4d75a00 CRITICAL: Remove all SQLite code, force PostgreSQL only
545d77a Add PostgreSQL support for Railway
5dd0cac Fix: Use correct database path in production
02af39c Use Railway Volume for SQLite database
fee8807 Update CORS for Vercel frontend
35f1ef9 Add react-datepicker and other dependencies
65c8325 Add vercel.json for Vite frontend deployment

=== ТЕКУЩИЙ СТАТУС ===
On branch main
Your branch is up to date with 'origin/main'.

Changes not staged for commit:
  (use \"git add <file>...\" to update what will be committed)
  (use \"git restore <file>...\" to discard changes in working directory)
	modified:   .DS_Store
	modified:   backend/__pycache__/database.cpython-313.pyc
	modified:   backend/__pycache__/main.cpython-313.pyc

Untracked files:
  (use \"git add <file>...\" to include in what will be committed)
	miniapp/frontend/.gitignore

no changes added to commit (use \"git add\" and/or \"git commit -a\")

=== ИЗМЕНЁННЫЕ ФАЙЛЫ (не закоммиченные) ===
.DS_Store
backend/__pycache__/database.cpython-313.pyc
backend/__pycache__/main.cpython-313.pyc
```

### 4) БАЗА ДАННЫХ

```text
=== SQLITE ФАЙЛЫ ===
./backend/finance_v5.db
./finance_v5.db

=== DATABASE.PY (если есть) ===
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
_dev_path = Path(\"/Users/alisheryusupov2002/Desktop/finance_system_v5/finance_v5.db\")
_railway_path = Path(\"/data/finance_v5.db\")
DEFAULT_DB_PATH = _railway_path if Path(\"/data\").exists() else _dev_path
DB_PATH = Path(os.getenv(\"FINANCE_DB_PATH\", DEFAULT_DB_PATH))


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
    \"\"\"Инициализация таблиц для кассирских отчётов\"\"\"
    import os

    # ПРАВИЛЬНЫЙ ПУТЬ К БД
    if os.path.exists('/data'):
        DB_PATH = '/data/finance_v5.db'

=== INIT_DB.PY ===
-rw-r--r--@ 1 alisheryusupov2002  staff  1075 Nov 23 18:44 backend/init_db.py
-rw-r--r--@ 1 alisheryusupov2002  staff  7036 Nov 23 18:44 backend/init_db_postgres.py
```

--- 

✅ Файл PROJECT_STATE.md создан и заполнен актуальными данными

