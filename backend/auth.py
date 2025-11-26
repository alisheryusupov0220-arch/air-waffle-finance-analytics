from fastapi import Header, HTTPException
from typing import Optional
import os
import psycopg2
import psycopg2.extras

def get_user_id_by_telegram(telegram_id: str) -> Optional[int]:
    """Получить user_id по telegram_id"""
    try:
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            return None
        
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # ИСПРАВЛЕНИЕ: Заменили 'is_active = 1' на 'is_active = TRUE'
        cursor.execute(
            "SELECT id FROM users WHERE telegram_id = %s AND is_active = TRUE",
            (int(telegram_id),)
        )
        
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        
        return user['id'] if user else None
        
    except Exception as e:
        print(f"Error getting user: {e}")
        return None

def get_current_user_id(x_telegram_id: Optional[str] = Header(None)) -> int:
    """Получить ID текущего пользователя из заголовка"""
    if not x_telegram_id:
        raise HTTPException(status_code=401, detail="X-Telegram-Id header required")
    
    user_id = get_user_id_by_telegram(x_telegram_id)
    
    if not user_id:
        raise HTTPException(status_code=403, detail="User not found or inactive")
    
    return user_id