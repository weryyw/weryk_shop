import os
import sqlite3
import html

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
    MessageHandler,
    ContextTypes,
    filters,
)


# ============================================================
# НАСТРОЙКИ
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
SMSFAST_API_KEY = os.getenv("SMSFAST_API_KEY")

DB_PATH = os.getenv("DB_PATH", "/app/data/shop.db")


# ============================================================
# DATABASE
# ============================================================

def get_db():
    folder = os.path.dirname(DB_PATH)

    if folder:
        os.makedirs(folder, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    return conn


def add_column_if_missing(conn, table, column, definition):
    """
    Добавляет столбец в старую базу, если его ещё нет.
    """

    columns = conn.execute(
        f"PRAGMA table_info({table})"
    ).fetchall()

    existing = [row["name"] for row in columns]

    if column not in existing:
        conn.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
        )


def init_db():

    conn = get_db()

    cur = conn.cursor()

    # --------------------------------------------------------
    # USERS
    # --------------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    add_column_if_missing(
        conn,
        "users",
        "username",
        "TEXT"
    )

    # --------------------------------------------------------
    # PRODUCTS
    # --------------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL DEFAULT 'other',
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            price REAL NOT NULL DEFAULT 0,
            stock INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1
        )
    """)

    # Миграция старой таблицы products.
    # Это исправляет твою ошибку:
    # sqlite3.OperationalError:
    # table products has no column named category

    add_column_if_missing(
        conn,
        "products",
        "category",
        "TEXT DEFAULT 'other'"
    )

    add_column_if_missing(
        conn,
        "products",
        "description",
        "TEXT DEFAULT ''"
    )

    add_column_if_missing(
        conn,
        "products",
        "price",
        "REAL DEFAULT 0"
    )

    add_column_if_missing(
        conn,
        "products",
        "stock",
        "INTEGER DEFAULT 0"
    )

    add_column_if_missing(
        conn,
        "products",
        "active",
        "INTEGER DEFAULT 1"
    )

    # --------------------------------------------------------
    # ORDERS
    # --------------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER,
            price REAL NOT NULL DEFAULT 0,
            status TEXT DEFAULT 'created',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    add_column_if_missing(
        conn,
        "orders",
        "user_id",
        "INTEGER"
    )

    add_column_if_missing(
        conn,
        "orders",
        "product_id",
        "INTEGER"
    )

    add_column_if_missing(
        conn,
        "orders",
        "price",
        "REAL DEFAULT 0"
    )

    add_column_if_missing(
        conn,
        "orders",
        "status",
        "TEXT DEFAULT 'created'"
    )

    # --------------------------------------------------------
    # DEMO PRODUCTS
    # --------------------------------------------------------

    count = cur.execute(
        "SELECT COUNT(*) FROM products"
    ).fetchone()[0]

    if count == 0:

        products = [
            (
                "numbers",
                "📱 Виртуальный номер",
                "Виртуальный номер. Цена будет настроена позже.",
                50,
                0,
            ),
            (
                "funpay",
                "🎮 FunPay аккаунт",
                "Цифровой товар.",
                300,
                0,
            ),
            (
                "telegram",
                "✈️ Telegram аккаунт",
                "Цифровой товар.",
                500,
                0,
            ),
        ]

        cur.executemany("""
            INSERT INTO products
            (
                category,
                name,
                description,
                price,
                stock
            )
            VALUES (?, ?, ?, ?, ?)
        """, products)

    conn.commit()
    conn.close()


# ============================================================
# SMSFAST
# ============================================================

async def smsfast_balance():

    if not SMSFAST_API_KEY:
        return None, "SMSFAST_API_KEY не настроен."

    # ВАЖНО:
    # API-адрес/параметры лучше не угадывать.
    # Здесь используется официальный API endpoint,
    # если SMSFAST возвращает совместимый ответ.

    url = "https://api.smsfast.com/stubs/handler_api.php"

    params = {
        "api_key": SMSFAST_API_KEY,
        "action": "getBalance",
    }

    try:

        timeout = aiohttp.ClientTimeout(
            total=10
        )

        async with aiohttp.ClientSession(
            timeout=timeout
        ) as session:

            async with session.get(
                url,
                params=params
            ) as response:

                text = await response.text()

                if response.status != 200:
                    return (
                        None,
                        f"HTTP ошибка: {response.status}"
                    )

                if text.startswith("ACCESS_BALANCE:"):

                    balance = text.split(
                        ":",
                        1
                    )[1]

                    return balance, None

                return None, text

    except Exception as e:

        return None, str(e)


# ============================================================
# KEYBOARDS
# ============================================================

def main_menu():

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🛍 Каталог",
                callback_data="catalog"
            )
        ],
        [
            InlineKeyboardButton(
                "🔎 Поиск",
                callback_data="search"
            ),
            InlineKeyboardButton(
                "🛒 Корзина",
                callback_data="cart"
            )
        ],
        [
            InlineKeyboardButton(
                "📦 Мои заказы",
                callback_data="orders"
            ),
            InlineKeyboardButton(
                "👤 Профиль",
                callback_data="profile"
            )
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


# ============================================================
# START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    conn = get_db()

    conn.execute("""
        INSERT INTO users (
            id,
            username
        )
        VALUES (?, ?)
        ON CONFLICT(id)
        DO UPDATE SET username = excluded.username
    """, (
        user.id,
        user.username
    ))

    conn.commit()
    conn.close()

    text = (
        "👋 <b>Добро пожаловать в Weryk Shop!</b>\n\n"
        "Здесь можно покупать цифровые товары.\n\n"
        "Выберите раздел:"
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=main_menu()
    )


# ============================================================
# BUTTON HANDLER
# ============================================================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    data = query.data

    # --------------------------------------------------------
    # HOME
    # --------------------------------------------------------

    if data == "home":

        await query.edit_message_text(
            "🏠 <b>Главное меню</b>\n\n"
            "Выберите раздел:",
            parse_mode="HTML",
            reply_markup=main_menu()
        )

        return

    # --------------------------------------------------------
    # CATALOG
    # --------------------------------------------------------

    if data == "catalog":

        await query.edit_message_text(
            "🛍 <b>Каталог</b>\n\n"
            "Выберите категорию:",
            parse_mode="HTML",
            reply_markup=catalog_menu()
        )

        return

    # --------------------------------------------------------
    # CATEGORY
    # --------------------------------------------------------

    if data.startswith("category:"):

        category = data.split(
            ":",
            1
        )[1]

        conn = get_db()

        products = conn.execute("""
            SELECT *
            FROM products
            WHERE category = ?
            AND active = 1
            ORDER BY id DESC
        """, (
            category,
        )).fetchall()

        conn.close()

        if not products:

            await query.edit_message_text(
                "😔 В этой категории пока нет товаров.",
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
                    (
                        f"{product['name']} — "
                        f"{product['price']:.2f} ₽"
                    ),
                    callback_data=(
                        f"product:{product['id']}"
                    )
                )
            ])

        buttons.append([
            InlineKeyboardButton(
                "⬅️ Назад",
                callback_data="catalog"
            )
        ])

        await query.edit_message_text(
            "📦 <b>Товары</b>\n\n"
            "Выберите товар:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                buttons
            )
        )

        return

    # --------------------------------------------------------
    # PRODUCT
    # --------------------------------------------------------

    if data.startswith("product:"):

        product_id = int(
            data.split(
                ":",
                1
            )[1]
        )

        conn = get_db()

        product = conn.execute("""
            SELECT *
            FROM products
            WHERE id = ?
            AND active = 1
        """, (
            product_id,
        )).fetchone()

        conn.close()

        if not product:

            await query.edit_message_text(
                "❌ Товар не найден."
            )

            return

        text = (
            f"📦 <b>{html.escape(product['name'])}</b>\n\n"
            f"{html.escape(product['description'] or '')}\n\n"
            f"💰 Цена: "
            f"<b>{product['price']:.2f} ₽</b>\n"
            f"📦 Остаток: "
            f"<b>{product['stock']}</b>"
        )

        buttons = []

        if product["stock"] > 0:

            buttons.append([
                InlineKeyboardButton(
                    "🛒 Купить",
                    callback_data=(
                        f"buy:{product['id']}"
                    )
                )
            ])

        buttons.append([
            InlineKeyboardButton(
                "⬅️ Назад",
                callback_data=(
                    f"category:{product['category']}"
                )
            )
        ])

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                buttons
            )
        )

        return

    # --------------------------------------------------------
    # BUY
    # --------------------------------------------------------

    if data.startswith("buy:"):

        product_id = int(
            data.split(
                ":",
                1
            )[1]
        )

        conn = get_db()

        product = conn.execute("""
            SELECT *
            FROM products
            WHERE id = ?
            AND active = 1
        """, (
            product_id,
        )).fetchone()

        if not product:

            conn.close()

            await query.edit_message_text(
                "❌ Товар не найден."
            )

            return

        if product["stock"] <= 0:

            conn.close()

            await query.edit_message_text(
                "❌ Товар закончился."
            )

            return

        user_id = query.from_user.id

        conn.execute("""
            INSERT INTO orders (
                user_id,
                product_id,
                price,
                status
            )
            VALUES (?, ?, ?, ?)
        """, (
            user_id,
            product_id,
            product["price"],
            "created"
        ))

        order_id = conn.execute(
            "SELECT last_insert_rowid()"
        ).fetchone()[0]

        conn.commit()
        conn.close()

        await query.edit_message_text(
            (
                "🛒 <b>Заказ создан</b>\n\n"
                f"Заказ: <b>#{order_id}</b>\n"
                f"Товар: "
                f"<b>{html.escape(product['name'])}</b>\n"
                f"Цена: "
                f"<b>{product['price']:.2f} ₽</b>\n\n"
                "💳 Оплату подключим следующим этапом."
            ),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🛍 Каталог",
                        callback_data="catalog"
                    )
                ]
            ])
        )

        return

    # --------------------------------------------------------
    # PROFILE
    # --------------------------------------------------------

    if data == "profile":

        user = query.from_user

        conn = get_db()

        orders = conn.execute("""
            SELECT COUNT(*)
            FROM orders
            WHERE user_id = ?
        """, (
            user.id,
        )).fetchone()[0]

        conn.close()

        username = (
            f"@{user.username}"
            if user.username
            else "нет"
        )

        text = (
            "👤 <b>Профиль</b>\n\n"
            f"ID: <code>{user.id}</code>\n"
            f"Username: {html.escape(username)}\n"
            f"📦 Заказов: {orders}"
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

    # --------------------------------------------------------
    # ORDERS
    # --------------------------------------------------------

    if data == "orders":

        user_id = query.from_user.id

        conn = get_db()

        orders = conn.execute("""
            SELECT
                orders.*,
                products.name AS product_name
            FROM orders
            LEFT JOIN products
            ON products.id = orders.product_id
            WHERE orders.user_id = ?
            ORDER BY orders.id DESC
            LIMIT 20
        """, (
            user_id,
        )).fetchall()

        conn.close()

        if not orders:

            text = (
                "📦 <b>Мои заказы</b>\n\n"
                "У вас пока нет заказов."
            )

        else:

            lines = [
                "📦 <b>Мои заказы</b>",
                ""
            ]

            for order in orders:

                product_name = (
                    order["product_name"]
                    or "Товар"
                )

                lines.append(
                    f"#{order['id']} — "
                    f"{html.escape(product_name)} — "
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

    # --------------------------------------------------------
    # CART
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    if data == "search":

        context.user_data["search_mode"] = True

        await query.edit_message_text(
            "🔎 <b>Поиск</b>\n\n"
            "Напиши название товара:",
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


# ============================================================
# SEARCH MESSAGE
# ============================================================

async def search_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.user_data.get(
        "search_mode"
    ):
        return

    search_text = update.message.text.strip()

    context.user_data["search_mode"] = False

    conn = get_db()

    products = conn.execute("""
        SELECT *
        FROM products
        WHERE active = 1
        AND (
            name LIKE ?
            OR description LIKE ?
        )
        ORDER BY id DESC
        LIMIT 20
    """, (
        f"%{search_text}%",
        f"%{search_text}%"
    )).fetchall()

    conn.close()

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
                (
                    f"{product['name']} — "
                    f"{product['price']:.2f} ₽"
                ),
                callback_data=(
                    f"product:{product['id']}"
                )
            )
        ])

    await update.message.reply_text(
        "🔎 <b>Результаты поиска:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            buttons
        )
    )


# ============================================================
# SMSFAST TEST
# ============================================================

async def smsfast_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "🔄 Проверяю подключение SMSFAST..."
    )

    balance, error = await smsfast_balance()

    if error:

        await update.message.reply_text(
            (
                "❌ Не удалось получить баланс SMSFAST.\n\n"
                f"<code>{html.escape(str(error))}</code>"
            ),
            parse_mode="HTML"
        )

        return

    await update.message.reply_text(
        (
            "✅ <b>SMSFAST ответил</b>\n\n"
            f"💰 Баланс: <b>{html.escape(str(balance))}</b>"
        ),
        parse_mode="HTML"
    )


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    print(
        "BOT ERROR:",
        repr(context.error)
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("================================")
    print("Starting Weryk Shop...")
    print("================================")

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN не найден в переменных окружения."
        )

    init_db()

    print("Database initialized.")

    if SMSFAST_API_KEY:

        print(
            "SMSFAST_API_KEY найден."
        )

    else:

        print(
            "WARNING: SMSFAST_API_KEY не найден."
        )

    application = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        CommandHandler(
            "smsfast",
            smsfast_command
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            button_handler
        )
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            search_message
        )
    )

    application.add_error_handler(
        error_handler
    )

    print("Weryk Shop is running!")

    application.run_polling()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
