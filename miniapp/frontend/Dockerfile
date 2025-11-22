# Этап 1: Сборка
FROM node:18-alpine AS builder

WORKDIR /app

# Копируем package files
COPY package*.json ./

# Устанавливаем зависимости
RUN npm ci

# Копируем код
COPY . .

# Собираем приложение
RUN npm run build

# Этап 2: Production
FROM node:18-alpine

WORKDIR /app

# Устанавливаем serve
RUN npm install -g serve

# Копируем собранное приложение
COPY --from=builder /app/dist ./dist

# Запускаем
CMD serve -s dist -p $PORT
