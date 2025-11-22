FROM python:3.11-slim

WORKDIR /app

# Копируем requirements
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY . .

# Railway передаёт PORT через переменную окружения
# Используем shell форму CMD для подстановки переменных
CMD uvicorn main:app --host 0.0.0.0 --port $PORT
# ВАЖНО: Убрал EXPOSE и ${PORT:-8000} — Railway сам управляет портами
