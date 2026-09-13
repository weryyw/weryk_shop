import os
import sqlite3
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# =========================
# НАСТРОЙКИ
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден")

DB_PATH = "/app/data/shop.db"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# =========================
# БАЗА ДАННЫХ
# =========================

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            photo_id TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT
        )
    """)

    conn.commit()
    conn.close()


def save_user(user):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO users
        (user_id, username, first_name)
        VALUES (?, ?, ?)
    """, (
        user.id,
        user.username,
        user.first_name
    ))

    conn.commit()
    conn.close()


# =========================
# ГЛАВНОЕ МЕНЮ
# =========================

def main_menu():
    keyboard = [
        [
            InlineKeyboardButton("🛍 Каталог", callback_data="catalog"),
            InlineKeyboardButton("🔎 Поиск", callback_data="search"),
        ],
        [
            InlineKeyboardButton("➕ Продать товар", callback_data="sell"),
        ],
        [
            InlineKeyboardButton("🛒 Корзина", callback_data="cart"),
            InlineKeyboardButton("📦 Мои заказы", callback_data="orders"),
        ],
        [
            InlineKeyboardButton("👤 Профиль", callback_data="profile"),
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


# =========================
# /START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user)

    text = (
        f"👋 Привет, {user.first_name}!\n\n"
        "🛍 Добро пожаловать в Weryk Shop!\n\n"
        "Здесь можно покупать и продавать товары."
    )

    await update.message.reply_text(
        text,
        reply_markup=main_menu()
    )


# =========================
# КНОПКИ
# =========================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    if query.data == "catalog":
        await show_catalog(query)

    elif query.data == "search":
        await query.message.reply_text(
            "🔎 Поиск товаров\n\n"
            "Функция поиска будет добавлена следующим этапом."
        )

    elif query.data == "sell":
        await query.message.reply_text(
            "➕ Продажа товара\n\n"
            "Следующим этапом здесь появится форма:\n"
            "📸 Фото\n"
            "📝 Название\n"
            "📄 Описание\n"
            "💰 Цена"
        )

    elif query.data == "cart":
        await query.message.reply_text(
            "🛒 Корзина пока пустая."
        )

    elif query.data == "orders":
        await query.message.reply_text(
            "📦 У вас пока нет заказов."
        )

    elif query.data == "profile":
        user = query.from_user

        username = (
            f"@{user.username}"
            if user.username
            else "не указан"
        )

        await query.message.reply_text(
            "👤 Профиль\n\n"
            f"Имя: {user.first_name}\n"
            f"Username: {username}\n"
            f"Telegram ID: {user.id}"
        )


# =========================
# КАТАЛОГ
# =========================

async def show_catalog(query):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, name, description, price, photo_id
        FROM products
        ORDER BY id DESC
    """)

    products = cursor.fetchall()
    conn.close()

    if not products:
        await query.message.reply_text(
            "🛍 Каталог пока пуст.\n\n"
            "Добавьте первый товар через «➕ Продать товар»."
        )
        return

    for product in products:
        product_id, name, description, price, photo_id = product

        text = (
            f"🛍 {name}\n\n"
            f"{description or 'Описание отсутствует'}\n\n"
            f"💰 Цена: {price:.2f} ₽"
        )

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🛒 Купить",
                    callback_data=f"buy_{product_id}"
                )
            ]
        ])

        if photo_id:
            await query.message.reply_photo(
                photo=photo_id,
                caption=text,
                reply_markup=keyboard
            )
        else:
            await query.message.reply_text(
                text,
                reply_markup=keyboard
            )


# =========================
# ПОКУПКА
# =========================

async def buy_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    product_id = query.data.replace("buy_", "")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT name, price FROM products WHERE id = ?",
        (product_id,)
    )

    product = cursor.fetchone()
    conn.close()

    if not product:
        await query.message.reply_text(
            "❌ Товар не найден."
        )
        return

    name, price = product

    await query.message.reply_text(
        f"🛒 Вы выбрали:\n\n"
        f"**{name}**\n"
        f"💰 {price:.2f} ₽\n\n"
        "💳 Система оплаты будет подключена следующим этапом.",
        parse_mode="Markdown"
    )


# =========================
# ОБРАБОТКА ТЕКСТА
# =========================

async def text_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "Используй кнопки меню 👇",
        reply_markup=main_menu()
    )


# =========================
# ЗАПУСК
# =========================

def main():
    init_db()

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CallbackQueryHandler(
            buy_handler,
            pattern=r"^buy_"
        )
    )

    application.add_handler(
        CallbackQueryHandler(button_handler)
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_handler
        )
    )

    print("✅ Weryk Shop запущен!")

    application.run_polling()


if __name__ == "__main__":
    main()
