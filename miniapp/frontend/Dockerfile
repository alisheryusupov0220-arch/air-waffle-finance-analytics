# Этап 1: Сборка
FROM node:18-alpine AS builder

WORKDIR /app

# Копируем package files
COPY package.json package-lock.json ./

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

# Указываем порт (Railway передаст через переменную PORT)
ENV PORT=3000

# Копируем собранное приложение
COPY --from=builder /app/dist ./dist

# Открываем порт
EXPOSE 3000

# Запускаем
CMD ["sh", "-c", "serve -s dist -l ${PORT:-3000}"]
