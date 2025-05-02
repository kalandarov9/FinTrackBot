FROM python:3.11-slim

# Обновляем систему и устанавливаем сборщик gcc (если требуется для зависимостей)
RUN apt-get update && apt-get install -y gcc

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем зависимости и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем остальной код проекта
COPY . .

# Открываем порт, если бот использует вебхуки (для polling этот шаг не обязателен)
EXPOSE 80

# Команда для запуска бота
CMD ["python", "bot.py"]