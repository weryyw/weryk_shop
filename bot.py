import os
import sqlite3
import asyncio
from html import escape

import aiohttp
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
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
SMSFAST_API_KEY = os.getenv("SMSFAST_API_KEY")

DB_PATH = os.getenv("DB_PATH", "/app/data/shop.db")

# =========================
# БАЗА ДАННЫХ
# =========================

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            price REAL NOT NULL,
            stock INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER,
            price REAL NOT NULL,
            status TEXT DEFAULT 'created',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()

    # Добавляем демо-категории только если товаров ещё нет
    cur.execute("SELECT COUNT(*) FROM products")
    count = cur.fetchone()[0]

    if count == 0:
        demo_products = [
            (
                "numbers",
                "Виртуальный номер",
                "Временный виртуальный номер.",
                50.0,
                0,
            ),
            (
                "funpay",
                "FunPay аккаунт",
                "Цифровой товар. Выдача после оплаты.",
                300.0,
                0,
            ),
            (
                "telegram",
                "Telegram аккаунт",
                "Цифровой товар. Выдача после оплаты.",
                500.0,
                0,
            ),
        ]

        cur.executemany("""
            INSERT INTO products
            (category, name, description, price, stock)
            VALUES (?, ?, ?, ?, ?)
        """, demo_products)

        conn.commit()

    conn.close()


# =========================
# SMSFAST API
# =========================

SMSFAST_URL = "https://api.smsfast.com/stubs/handler_api.php"


async def smsfast_balance():
    """
    Получает баланс SMSFAST.
    API-ключ берётся из переменной окружения.
    """

    if not SMSFAST_API_KEY:
        return None, "SMSFAST_API_KEY не настроен."

    params = {
        "api_key": SMSFAST_API_KEY,
        "action": "getBalance",
    }

    try:
        timeout = aiohttp.ClientTimeout(total=10)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(SMSFAST_URL, params=params) as response:
                text = await response.text()

                if response.status != 200:
                    return None, f"HTTP ошибка: {response.status}"

                if text.startswith("ACCESS_BALANCE:"):
                    balance = text.split(":", 1)[1]
                    return balance, None

                return None, text

    except Exception as e:
        return None, str(e)


# =========================
# КЛАВИАТУРЫ
# =========================

def main_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🛍 Каталог", callback_data="catalog")
        ],
        [
            InlineKeyboardButton("🔎 Поиск", callback_data="search"),
            InlineKeyboardButton("🛒 Корзина", callback_data="cart")
        ],
        [
            InlineKeyboardButton("📦 Мои заказы", callback_data="orders"),
            InlineKeyboardButton("👤 Профиль", callback_data="profile")
        ],
    ])


def catalog_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📱 Виртуальные номера",
                callback_data="category:numbers"
            )
        ],
        [
            InlineKeyboardButton(
                "🎮 FunPay аккаунты",
                callback_data="category:funpay"
            )
        ],
        [
            InlineKeyboardButton(
                "✈️ Telegram аккаунты",
                callback_data="category:telegram"
            )
        ],
        [
            InlineKeyboardButton(
                "⬅️ Назад",
                callback_data="home"
            )
        ],
    ])


# =========================
# /start
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    conn = get_db()
    conn.execute("""
        INSERT OR IGNORE INTO users (id, username)
        VALUES (?, ?)
    """, (user.id, user.username))

    conn.commit()
    conn.close()

    text = (
        f"👋 <b>Добро пожаловать в Weryk Shop!</b>\n\n"
        f"Здесь можно покупать цифровые товары.\n\n"
        f"Выберите раздел:"
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=main_menu()
    )


# =========================
# КНОПКИ
# =========================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    # Главная
    if data == "home":
        await query.edit_message_text(
            "🏠 <b>Главное меню</b>\n\nВыберите раздел:",
            parse_mode="HTML",
            reply_markup=main_menu()
        )
        return

    # Каталог
    if data == "catalog":
        await query.edit_message_text(
            "🛍 <b>Каталог</b>\n\nВыберите категорию:",
            parse_mode="HTML",
            reply_markup=catalog_menu()
        )
        return

    # Категория
    if data.startswith("category:"):
        category = data.split(":", 1)[1]

        conn = get_db()

        products = conn.execute("""
            SELECT *
            FROM products
            WHERE category = ?
            AND active = 1
            ORDER BY id DESC
        """, (category,)).fetchall()

        conn.close()

        if not products:
            await query.edit_message_text(
                "😔 В этой категории пока ничего нет.",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "⬅️ Назад",
                            callback_data="catalog"
                        )
                    ]
                ])
            )
            return

        buttons = []

        for product in products:
            buttons.append([
                InlineKeyboardButton(
                    f"{product['name']} — {product['price']:.2f} ₽",
                    callback_data=f"product:{product['id']}"
                )
            ])

        buttons.append([
            InlineKeyboardButton(
                "⬅️ Назад",
                callback_data="catalog"
            )
        ])

        await query.edit_message_text(
            "📦 <b>Товары</b>\n\nВыберите товар:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    # Товар
    if data.startswith("product:"):
        product_id = int(data.split(":", 1)[1])

        conn = get_db()

        product = conn.execute("""
            SELECT *
            FROM products
            WHERE id = ?
            AND active = 1
        """, (product_id,)).fetchone()

        conn.close()

        if not product:
            await query.edit_message_text(
                "❌ Товар не найден."
            )
            return

        text = (
            f"📦 <b>{escape(product['name'])}</b>\n\n"
            f"{escape(product['description'])}\n\n"
            f"💰 Цена: <b>{product['price']:.2f} ₽</b>\n"
            f"📦 Остаток: <b>{product['stock']}</b>\n"
        )

        keyboard = []

        if product["stock"] > 0:
            keyboard.append([
                InlineKeyboardButton(
                    "🛒 Купить",
                    callback_data=f"buy:{product['id']}"
                )
            ])

        keyboard.append([
            InlineKeyboardButton(
                "⬅️ Назад",
                callback_data=f"category:{product['category']}"
            )
        ])

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Покупка
    if data.startswith("buy:"):
        product_id = int(data.split(":", 1)[1])

        conn = get_db()

        product = conn.execute("""
            SELECT *
            FROM products
            WHERE id = ?
            AND active = 1
        """, (product_id,)).fetchone()

        conn.close()

        if not product:
            await query.edit_message_text("❌ Товар не найден.")
            return

        if product["stock"] <= 0:
            await query.edit_message_text(
                "❌ К сожалению, товар закончился."
            )
            return

        await query.edit_message_text(
            f"🛒 <b>Заказ создан</b>\n\n"
            f"Товар: {escape(product['name'])}\n"
            f"Цена: <b>{product['price']:.2f} ₽</b>\n\n"
            f"💳 Систему оплаты подключим следующим шагом.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ В каталог",
                        callback_data="catalog"
                    )
                ]
            ])
        )
        return

    # Профиль
    if data == "profile":
        user = query.from_user

        conn = get_db()

        orders = conn.execute("""
            SELECT COUNT(*)
            FROM orders
            WHERE user_id = ?
        """, (user.id,)).fetchone()[0]

        conn.close()

        text = (
            "👤 <b>Профиль</b>\n\n"
            f"ID: <code>{user.id}</code>\n"
            f"Username: @{escape(user.username or 'нет')}\n"
            f"📦 Заказов: {orders}\n"
        )

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Назад",
                        callback_data="home"
                    )
                ]
            ])
        )
        return

    # Заказы
    if data == "orders":
        user_id = query.from_user.id

        conn = get_db()

        orders = conn.execute("""
            SELECT *
            FROM orders
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 10
        """, (user_id,)).fetchall()

        conn.close()

        if not orders:
            text = "📦 <b>Мои заказы</b>\n\nУ вас пока нет заказов."
        else:
            lines = ["📦 <b>Мои заказы</b>\n"]

            for order in orders:
                lines.append(
                    f"#{order['id']} — "
                    f"{order['price']:.2f} ₽ — "
                    f"{order['status']}"
                )

            text = "\n".join(lines)

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Назад",
                        callback_data="home"
                    )
                ]
            ])
        )
        return

    # Корзина
    if data == "cart":
        await query.edit_message_text(
            "🛒 <b>Корзина</b>\n\n"
            "Корзина пока пустая.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🛍 Каталог",
                        callback_data="catalog"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "⬅️ Назад",
                        callback_data="home"
                    )
                ]
            ])
        )
        return

    # Поиск
    if data == "search":
        await query.edit_message_text(
            "🔎 <b>Поиск</b>\n\n"
            "Напиши название товара сообщением.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Назад",
                        callback_data="home"
                    )
                ]
            ])
        )

        context.user_data["search_mode"] = True
        return


# =========================
# ПОИСК
# =========================

async def search_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("search_mode"):
        return

    query_text = update.message.text.strip()

    conn = get_db()

    products = conn.execute("""
        SELECT *
        FROM products
        WHERE active = 1
        AND (
            name LIKE ?
            OR description LIKE ?
        )
        LIMIT 20
    """, (
        f"%{query_text}%",
        f"%{query_text}%"
    )).fetchall()

    conn.close()

    context.user_data["search_mode"] = False

    if not products:
        await update.message.reply_text(
            "❌ Ничего не найдено.",
            reply_markup=main_menu()
        )
        return

    buttons = []

    for product in products:
        buttons.append([
            InlineKeyboardButton(
                f"{product['name']} — {product['price']:.2f} ₽",
                callback_data=f"product:{product['id']}"
            )
        ])

    await update.message.reply_text(
        "🔎 <b>Результаты поиска:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


# =========================
# /smsfast
# =========================

async def smsfast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Проверка подключения SMSFAST.
    API-ключ пользователю не показываем.
    """

    await update.message.reply_text(
        "🔄 Проверяю подключение SMSFAST..."
    )

    balance, error = await smsfast_balance()

    if error:
        await update.message.reply_text(
            f"❌ SMSFAST не ответил.\n\n"
            f"<code>{escape(str(error))}</code>",
            parse_mode="HTML"
        )
        return

    await update.message.reply_text(
        f"✅ <b>SMSFAST подключён</b>\n\n"
        f"💰 Баланс: <b>{escape(str(balance))}</b>",
        parse_mode="HTML"
    )


# =========================
# ОШИБКИ
# =========================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    print("ERROR:", context.error)


# =========================
# ЗАПУСК
# =========================

def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "Не найдена переменная BOT_TOKEN"
        )

    init_db()

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("smsfast", smsfast_command))

    app.add_handler(
        CallbackQueryHandler(button_handler)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            search_message
        )
    )

    app.add_error_handler(error_handler)

    print("Weryk Shop запущен!")

    app.run_polling()


if __name__ == "__main__":
    main()
