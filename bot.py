import datetime
import logging
import os
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler,
    CallbackQueryHandler,
)

# Загружаем переменные окружения из файла .env (и .env.db, если используется)
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError(
        "Не найден токен бота. Проверьте, что в .env определена переменная BOT_TOKEN.")

# Параметры подключения к базе берутся из переменных окружения
# Например, в .env или .env.db могут быть:
# DB_HOST=db
# DB_PORT=5432
# DB_USER=postgres
# DB_PASSWORD=postgres
# DB_NAME=fintrackdb

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для разговора с пользователем
AMOUNT, CATEGORY = range(2)

# Временное хранение данных (не в базе, а только для сессии разговора)
user_temp_data = {}

# Список категорий по умолчанию
default_categories = ["Еда", "Транспорт", "Жильё",
                      "Развлечения", "Покупки", "Здоровье", "Другое"]

# Функция для получения подключения к базе


def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "postgres"),
        dbname=os.getenv("DB_NAME", "fintrackdb")
    )

# Инициализация базы: создание таблиц, если их нет


def initialize_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            amount REAL,
            category TEXT,
            date TEXT,
            username TEXT
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            category TEXT
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

# Получение категорий пользователя из базы; если их нет, вставляем категории по умолчанию


def get_user_categories(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT category FROM categories WHERE user_id = %s", (user_id,))
    rows = cur.fetchall()
    if not rows:
        for cat in default_categories:
            cur.execute(
                "INSERT INTO categories (user_id, category) VALUES (%s, %s)", (user_id, cat))
        conn.commit()
        categories = default_categories.copy()
    else:
        categories = [row[0] for row in rows]
    cur.close()
    conn.close()
    return categories

# Функция вставки расхода в таблицу


def insert_expense(user_id, amount, category, date, username):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO expenses (user_id, amount, category, date, username) VALUES (%s, %s, %s, %s, %s)",
        (user_id, amount, category, date, username)
    )
    conn.commit()
    cur.close()
    conn.close()

# Получение всех расходов


def get_expenses():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT amount, category, date, username FROM expenses ORDER BY id DESC"
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

# Очистка расходов для пользователя


def clear_expenses(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM expenses WHERE user_id = %s", (user_id,))
    conn.commit()
    cur.close()
    conn.close()

# Очистка всех расходов


def clear_all_expenses():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM expenses")
    conn.commit()
    cur.close()
    conn.close()

# Вставка новой категории для пользователя


def insert_category(user_id, category):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO categories (user_id, category) VALUES (%s, %s)", (user_id, category))
    conn.commit()
    cur.close()
    conn.close()

# Удаление категории для пользователя


def delete_category(user_id, category):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM categories WHERE user_id = %s AND category = %s", (user_id, category))
    conn.commit()
    cur.close()
    conn.close()

# Получение расходов за конкретный месяц (используется формат даты MM/DD/YYYY)


def get_monthly_expenses(month, year):
    conn = get_db_connection()
    cur = conn.cursor()
    pattern = f"{month:02d}/%/{year}"
    cur.execute(
        "SELECT amount, category, date, username FROM expenses WHERE date LIKE %s",
        (pattern,)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

# Получение всех уникальных категорий


def get_categories():
    # Получаем все уникальные категории вместо категорий одного пользователя
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT category FROM categories")
    rows = cur.fetchall()
    if not rows:
        # Если категорий нет, создаем категории по умолчанию
        for cat in default_categories:
            cur.execute(
                "INSERT INTO categories (user_id, category) VALUES (%s, %s)", (0, cat))
        conn.commit()
        categories = default_categories.copy()
    else:
        categories = [row[0] for row in rows]
    cur.close()
    conn.close()
    return categories

# Обработчики команд и разговоров


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # Обеспечиваем, чтобы для пользователя были созданы категории по умолчанию
    get_user_categories(user_id)
    await update.message.reply_text("Привет! Для добавления расхода используй /add\nДля справки используй /help.")
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "Доступные команды:\n"
        "/start - начать работу с ботом\n"
        "/add - добавить новый расход\n"
        "/report - получить подробный отчёт о расходах\n"
        "/clear - очистить все записи о расходах\n"
        "/categories - управление категориями\n"
        "/add_category - добавить новую категорию\n"
        "/delete_category - удалить категорию\n"
        "/month - отчёт за конкретный месяц, формат: /month MM/YYYY"
    )
    await update.message.reply_text(help_text)
    return ConversationHandler.END

# Начало ввода расхода


async def add_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите сумму расхода:")
    return AMOUNT

# Обработка суммы и показ клавиатуры с категориями


async def amount_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        amount = float(update.message.text)
        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}
        user_temp_data[user_id]["amount"] = amount

        # Получаем общие категории вместо категорий пользователя
        categories = get_categories()
        keyboard = [[InlineKeyboardButton(
            cat, callback_data=f"cat_{cat}")] for cat in categories]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Выберите категорию:", reply_markup=reply_markup)
        return CATEGORY
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите корректное число. Попробуйте снова:")
        return AMOUNT

# Обработка выбора категории и запись расхода в базу


async def category_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    user = query.from_user
    username = user.username if user.username else user.first_name
    category = query.data[4:]  # Убираем префикс 'cat_'
    amount = user_temp_data.get(user_id, {}).get("amount", 0)
    date = datetime.datetime.now().strftime("%m/%d/%Y")
    insert_expense(user_id, amount, category, date, username)
    if user_id in user_temp_data:
        del user_temp_data[user_id]
    await query.edit_message_text(f"Сохранил: {amount}$ — {category}")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_temp_data:
        del user_temp_data[user_id]
    await update.message.reply_text("Операция отменена.")
    return ConversationHandler.END

# Вывод списка категорий


async def list_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Получаем все категории вместо категорий конкретного пользователя
    categories = get_categories()
    categories_text = "Все доступные категории:\n\n"
    for i, category in enumerate(categories, 1):
        categories_text += f"{i}. {category}\n"
    categories_text += "\nИспользуйте /add_category для добавления или /delete_category для удаления категории."
    await update.message.reply_text(categories_text)
    return ConversationHandler.END

# Отчёт по расходам (группировка по месяцам)


async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Вместо получения расходов конкретного пользователя, получаем все расходы
    rows = get_expenses()
    if not rows:
        await update.message.reply_text("Пока нет записей. Попробуй добавить расходы!")
        return ConversationHandler.END

    current_date = datetime.datetime.now()
    current_month = current_date.month
    current_year = current_date.year
    current_month_total = 0
    current_year_total = 0
    expenses_by_month = {}

    for row in rows:
        amount, category, date, username = row
        try:
            month, day, year = date.split('/')
            month = int(month)
            year = int(year)
            month_key = f"{month:02d}/{year}"
            if month == current_month and year == current_year:
                current_month_total += amount
            if year == current_year:
                current_year_total += amount
        except Exception:
            month_key = "Неизвестно"
        if month_key not in expenses_by_month:
            expenses_by_month[month_key] = []
        expenses_by_month[month_key].append((amount, category, date, username))

    report_text = "Ваши расходы:\n\n"
    month_names = {
        1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель", 5: "Май",
        6: "Июнь", 7: "Июль", 8: "Август", 9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
    }
    current_month_name = month_names.get(current_month, str(current_month))
    report_text += f"💰 Расходы за {current_month_name} {current_year}: {current_month_total:.2f}$\n"
    report_text += f"💰 Общие расходы за {current_year} год: {current_year_total:.2f}$\n\n"
    grand_total = 0
    sorted_months = sorted(expenses_by_month.keys(),
                           key=lambda x: (int(x.split('/')[1]) if '/' in x and x != "Неизвестно" else 0,
                                          int(x.split('/')[0]) if '/' in x and x != "Неизвестно" else 0))
    for month_key in sorted_months:
        month_entries = expenses_by_month[month_key]
        month_total = sum(entry[0] for entry in month_entries)
        grand_total += month_total
        report_text += f"== {month_key} — {month_total:.2f}$ ==\n"
        for amount, category, date, username in month_entries:
            report_text += f"{date}: {amount}$ — {category} (добавил: @{username})\n"
        report_text += "\n"
    report_text += f"Общая сумма всех расходов: {grand_total:.2f}$\n"
    await update.message.reply_text(report_text)
    return ConversationHandler.END

# Очистка расходов (удаление записей в базе)


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    # Вы можете добавить проверку на администратора или предупреждение
    # что будут удалены все расходы для всех пользователей
    await update.message.reply_text("⚠️ Внимание! Эта команда удалит все расходы для всех пользователей. Продолжить? /confirmclear для подтверждения")
    return ConversationHandler.END


async def confirm_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Очищаем все расходы
    clear_all_expenses()
    await update.message.reply_text("Все расходы очищены.")
    return ConversationHandler.END

# Добавление новой категории


async def add_category_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите название новой категории:")
    return "WAITING_CATEGORY_NAME"


async def new_category_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    new_category = update.message.text.strip()
    if not new_category:
        await update.message.reply_text("Название категории не может быть пустым. Попробуйте снова.")
        return "WAITING_CATEGORY_NAME"

    # Проверяем среди всех категорий, а не только пользователя
    categories = get_categories()
    if new_category in categories:
        await update.message.reply_text(f"Категория '{new_category}' уже существует.")
    else:
        # Используем user_id = 0 для общих категорий
        insert_category(0, new_category)
        await update.message.reply_text(f"Категория '{new_category}' добавлена для всех пользователей!")
    return ConversationHandler.END

# Удаление категории


async def delete_category_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Получаем все категории
    categories = get_categories()
    if not categories:
        await update.message.reply_text("Нет категорий для удаления.")
        return ConversationHandler.END
    keyboard = [[InlineKeyboardButton(
        f"Удалить: {cat}", callback_data=f"del_{cat}")] for cat in categories]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите категорию для удаления:", reply_markup=reply_markup)
    return "CONFIRM_DELETE"


async def confirm_delete_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category = query.data[4:]

    # Удаляем категорию для всех пользователей (user_id = 0)
    delete_category(0, category)
    await query.edit_message_text(f"Категория '{category}' удалена для всех пользователей.")
    return ConversationHandler.END

# Отчет за конкретный месяц


async def monthly_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Используйте формат: /month MM/YYYY (например, /month 04/2025)")
        return ConversationHandler.END

    try:
        month_year = context.args[0]
        month, year = month_year.split('/')
        month = int(month)
        year = int(year)
    except (ValueError, IndexError):
        await update.message.reply_text("Неверный формат. Используйте: /month MM/YYYY")
        return ConversationHandler.END

    # Получаем расходы всех пользователей за месяц
    # Эту функцию тоже нужно изменить!
    rows = get_monthly_expenses(month, year)
    if not rows:
        await update.message.reply_text(f"За {month:02d}/{year} расходов не найдено.")
        return ConversationHandler.END

    month_names = {
        1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель", 5: "Май",
        6: "Июнь", 7: "Июль", 8: "Август", 9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
    }
    report_text = f"Отчет за {month_names.get(month, str(month))} {year}:\n\n"
    total = 0
    category_totals = {}
    user_totals = {}

    for amount, category, date, username in rows:
        report_text += f"{date}: {amount:.2f}$ — {category} (добавил: @{username})\n"
        total += amount
        category_totals[category] = category_totals.get(category, 0) + amount
        user_totals[username] = user_totals.get(username, 0) + amount

    report_text += f"\nВсего за месяц: {total:.2f}$\n\n"
    report_text += "Расходы по категориям:\n"
    for cat, cat_total in category_totals.items():
        report_text += f"{cat}: {cat_total}$\n"
    report_text += "\nРасходы по пользователям:\n"
    for user, user_total in user_totals.items():
        report_text += f"@{user}: {user_total}$\n"

    await update.message.reply_text(report_text)
    return ConversationHandler.END


def main():
    initialize_db()  # Создаем таблицы, если их нет
    app = ApplicationBuilder().token(TOKEN).build()

    add_expense_handler = ConversationHandler(
        entry_points=[CommandHandler("add", add_expense)],
        states={
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, amount_entered)],
            CATEGORY: [CallbackQueryHandler(category_selected, pattern="^cat_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True  # добавлено, чтобы разговор можно было запускать повторно
    )

    add_category_handler = ConversationHandler(
        entry_points=[CommandHandler("add_category", add_category_command)],
        states={
            "WAITING_CATEGORY_NAME": [MessageHandler(filters.TEXT & ~filters.COMMAND, new_category_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    delete_category_handler = ConversationHandler(
        entry_points=[CommandHandler(
            "delete_category", delete_category_command)],
        states={
            "CONFIRM_DELETE": [CallbackQueryHandler(confirm_delete_category, pattern="^del_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("confirmclear", confirm_clear))
    app.add_handler(CommandHandler("categories", list_categories))
    app.add_handler(add_expense_handler)
    app.add_handler(add_category_handler)
    app.add_handler(delete_category_handler)
    app.add_handler(CommandHandler("month", monthly_report))

    print("Starting bot polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
