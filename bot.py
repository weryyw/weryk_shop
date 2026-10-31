import os
import sqlite3
import logging
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

# ============================================================
# НАСТРОЙКИ
# ============================================================
# ЗАМЕНИ слово "тарелка" на настоящий токен от @BotFather.
TOKEN = os.getenv("9138228373:AAF_DUbsqHcHViLq0J-1JD8nhr7uydxdcC4", "").strip()

# Числовой Telegram ID администратора задаётся в переменных окружения Bothost.
try:
    ADMIN_ID = int(os.getenv("5203432796", "0"))
except ValueError:
    ADMIN_ID = 0

# База данных хранится в папке data.
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "grace_store.db"
PHOTO_DIR = Path("photos")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("grace_store")

# Временные состояния диалогов. При перезапуске бота они сбрасываются.
user_states = {}
carts = {}


# ============================================================
# БАЗА ДАННЫХ
# ============================================================
def connect_db():
    return sqlite3.connect(DB_PATH)

def init_db():
    with connect_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                price INTEGER NOT NULL,
                sizes TEXT DEFAULT '',
                photo TEXT DEFAULT ''
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT DEFAULT '',
                customer TEXT NOT NULL,
                phone TEXT NOT NULL,
                delivery TEXT NOT NULL,
                address TEXT NOT NULL,
                items TEXT NOT NULL,
                total INTEGER NOT NULL,
                status TEXT DEFAULT 'Новый',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT DEFAULT '',
                subject TEXT DEFAULT 'Вопрос в поддержку',
                status TEXT DEFAULT 'open',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS ticket_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                sender_id INTEGER NOT NULL,
                sender_role TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(ticket_id) REFERENCES tickets(id)
            )
        """)
        db.commit()

def is_admin(user_id):
    return ADMIN_ID > 0 and user_id == ADMIN_ID

def money(amount):
    return f"{amount:,}".replace(",", " ") + " ₽"

def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛍 Каталог", callback_data="catalog")],
        [InlineKeyboardButton("🛒 Корзина", callback_data="cart")],
        [InlineKeyboardButton("📦 Мои заказы", callback_data="orders")],
        [InlineKeyboardButton("🎫 Техническая поддержка", callback_data="support")],
        [InlineKeyboardButton("👤 Профиль", callback_data="profile")],
        [InlineKeyboardButton("⭐ Отзывы", url="https://t.me/fjgrtgkk3krkger5hjgsjrtl5gl")]
    ])

def back_button(destination="home"):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Назад", callback_data=destination)]
    ])

CATEGORIES = ["Обувь", "Одежда", "Ремни", "Рюкзаки", "Головные уборы", "Куртки"]


# ============================================================
# СТАРТ И КАТАЛОГ
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"Добро пожаловать в GRACE STORE, {user.first_name}! 👑\n\n"
        "Выбирай товары, оформляй заказ или обращайся в поддержку.",
        reply_markup=main_menu()
    )

async def show_catalog(query):
    keyboard = [
        [InlineKeyboardButton(category, callback_data=f"cat:{category}")]
        for category in CATEGORIES
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Главное меню", callback_data="home")])
    await query.edit_message_text(
        "🛍 КАТАЛОГ GRACE STORE\n\nВыбери категорию:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_category(query, category):
    if category == "Куртки":
        await query.edit_message_text(
            "🧥 КУРТКИ\n\nСкоро здесь появятся новинки. Категория ожидает пополнения!",
            reply_markup=back_button("catalog")
        )
        return
    with connect_db() as db:
        products = db.execute(
            "SELECT id, name, price FROM products WHERE category=? ORDER BY id DESC",
            (category,)
        ).fetchall()

    keyboard = [
        [InlineKeyboardButton(f"{name} — {money(price)}", callback_data=f"product:{pid}")]
        for pid, name, price in products
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Категории", callback_data="catalog")])

    text = f"📂 {category}\n\n"
    text += "Товары пока не добавлены." if not products else "Выбери товар:"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_product(query, product_id):
    with connect_db() as db:
        product = db.execute(
            "SELECT category,name,description,price,sizes,photo FROM products WHERE id=?",
            (product_id,)
        ).fetchone()

    if not product:
        await query.answer("Товар не найден.", show_alert=True)
        return

    category, name, description, price, sizes, photo = product
    text = (
        f"👑 {name}\n\n{description}\n\n"
        f"💰 Цена: {money(price)}\n"
        f"📏 Размеры: {sizes or 'Уточняйте у поддержки'}"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить в корзину", callback_data=f"add:{product_id}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data=f"cat:{category}")]
    ])

    if photo:
        try:
            if photo.startswith("local:"):
                image_path = PHOTO_DIR / photo.split(":", 1)[1]
                with image_path.open("rb") as image_file:
                    await query.message.reply_photo(
                        photo=image_file, caption=text, reply_markup=keyboard
                    )
            else:
                await query.message.reply_photo(
                    photo=photo, caption=text, reply_markup=keyboard
                )
            await query.delete_message()
        except Exception:
            await query.edit_message_text(text, reply_markup=keyboard)
    else:
        await query.edit_message_text(text, reply_markup=keyboard)


# ============================================================
# КОРЗИНА И ЗАКАЗЫ
# ============================================================
async def show_cart(query, user_id):
    cart = carts.get(user_id, [])
    if not cart:
        await query.edit_message_text(
            "🛒 Корзина пока пуста.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛍 В каталог", callback_data="catalog")],
                [InlineKeyboardButton("⬅️ Меню", callback_data="home")]
            ])
        )
        return

    lines, keyboard, total = [], [], 0
    for index, (product_id, size) in enumerate(cart):
        with connect_db() as db:
            row = db.execute(
                "SELECT name,price FROM products WHERE id=?", (product_id,)
            ).fetchone()
        if not row:
            continue
        name, price = row
        total += price
        lines.append(f"• {name} / размер {size} — {money(price)}")
        keyboard.append([
            InlineKeyboardButton(f"❌ Удалить {name}", callback_data=f"remove:{index}")
        ])

    lines.append(f"\nИтого: {money(total)}")
    keyboard.extend([
        [InlineKeyboardButton("✅ Оформить заказ", callback_data="checkout")],
        [InlineKeyboardButton("⬅️ Меню", callback_data="home")]
    ])
    await query.edit_message_text(
        "🛒 ТВОЯ КОРЗИНА\n\n" + "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def begin_checkout(query, user_id):
    if not carts.get(user_id):
        await query.answer("Корзина пуста.", show_alert=True)
        return
    user_states[user_id] = {"step": "order_name"}
    await query.edit_message_text("Напиши имя и фамилию для заказа:")

async def save_order(update, context, user_id, state):
    cart = carts.get(user_id, [])
    items, total = [], 0
    with connect_db() as db:
        for product_id, size in cart:
            row = db.execute(
                "SELECT name,price FROM products WHERE id=?", (product_id,)
            ).fetchone()
            if row:
                items.append(f"{row[0]} (размер {size})")
                total += row[1]

        if not items:
            await update.message.reply_text("Корзина пуста или товары больше недоступны.")
            user_states.pop(user_id, None)
            return

        cursor = db.execute("""
            INSERT INTO orders
            (user_id,username,customer,phone,delivery,address,items,total)
            VALUES (?,?,?,?,?,?,?,?)
        """, (
            user_id,
            update.effective_user.username or "",
            state["customer"],
            state["phone"],
            state["delivery"],
            state["address"],
            ", ".join(items),
            total
        ))
        order_id = cursor.lastrowid
        db.commit()

    await update.message.reply_text(
        f"✅ Заказ #{order_id} принят!\n"
        f"Сумма: {money(total)}\n\n"
        "Администратор свяжется с тобой для подтверждения заказа.",
        reply_markup=main_menu()
    )

    if ADMIN_ID != 123456789:
        try:
            await context.bot.send_message(
                ADMIN_ID,
                f"🛎 НОВЫЙ ЗАКАЗ #{order_id}\n\n"
                f"Покупатель: {state['customer']}\n"
                f"Telegram ID: {user_id}\n"
                f"Телефон: {state['phone']}\n"
                f"Доставка: {state['delivery']}\n"
                f"Адрес: {state['address']}\n"
                f"Товары: {', '.join(items)}\n"
                f"Сумма: {money(total)}"
            )
        except Exception:
            logger.exception("Не удалось отправить уведомление о заказе")

    carts[user_id] = []
    user_states.pop(user_id, None)


# ============================================================
# ТЕХНИЧЕСКАЯ ПОДДЕРЖКА / ТИКЕТЫ
# ============================================================
async def create_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    with connect_db() as db:
        cursor = db.execute(
            "INSERT INTO tickets (user_id,username) VALUES (?,?)",
            (user_id, update.effective_user.username or "")
        )
        ticket_id = cursor.lastrowid
        db.commit()

    user_states[user_id] = {"step": "ticket_message", "ticket_id": ticket_id}
    await update.message.reply_text(
        f"🎫 Обращение #{ticket_id} создано.\n\n"
        "Опиши проблему одним сообщением. Администратор ответит здесь, в боте.\n"
        "Для отмены напиши /cancel."
    )

async def send_ticket_message(update: Update, context: ContextTypes.DEFAULT_TYPE,
                              ticket_id: int, sender_role: str):
    user_id = update.effective_user.id
    message = update.message.text.strip()
    if not message:
        await update.message.reply_text("Отправь текстовое сообщение.")
        return

    with connect_db() as db:
        ticket = db.execute(
            "SELECT user_id,status FROM tickets WHERE id=?", (ticket_id,)
        ).fetchone()
        if not ticket:
            await update.message.reply_text("Обращение не найдено.")
            return
        if ticket[1] != "open":
            await update.message.reply_text("Это обращение закрыто. Создай новое через поддержку.")
            return

        db.execute(
            "INSERT INTO ticket_messages (ticket_id,sender_id,sender_role,message) VALUES (?,?,?,?)",
            (ticket_id, user_id, sender_role, message)
        )
        db.commit()

    if sender_role == "user":
        await update.message.reply_text(
            f"✅ Сообщение добавлено в обращение #{ticket_id}. Ожидай ответа администратора."
        )
        if ADMIN_ID != 123456789:
            try:
                await context.bot.send_message(
                    ADMIN_ID,
                    f"🎫 ОБРАЩЕНИЕ #{ticket_id}\n"
                    f"От: {update.effective_user.full_name}\n"
                    f"Telegram ID: {user_id}\n\n"
                    f"{message}\n\n"
                    f"Ответить: /reply {ticket_id} текст ответа\n"
                    f"Закрыть: /close_ticket {ticket_id}"
                )
            except Exception:
                logger.exception("Не удалось уведомить администратора о тикете")
    else:
        await update.message.reply_text(f"Ответ отправлен пользователю по обращению #{ticket_id}.")

async def reply_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Эта команда доступна только администратору.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Использование: /reply НОМЕР_ТИКЕТА текст ответа")
        return
    try:
        ticket_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Номер обращения должен быть числом.")
        return

    answer = " ".join(context.args[1:])
    with connect_db() as db:
        ticket = db.execute(
            "SELECT user_id,status FROM tickets WHERE id=?", (ticket_id,)
        ).fetchone()

    if not ticket:
        await update.message.reply_text("Обращение не найдено.")
        return
    if ticket[1] != "open":
        await update.message.reply_text("Обращение уже закрыто.")
        return

    target_user_id = ticket[0]
    with connect_db() as db:
        db.execute(
            "INSERT INTO ticket_messages (ticket_id,sender_id,sender_role,message) VALUES (?,?,?,?)",
            (ticket_id, update.effective_user.id, "admin", answer)
        )
        db.commit()

    try:
        await context.bot.send_message(
            target_user_id,
            f"💬 Ответ поддержки по обращению #{ticket_id}:\n\n{answer}\n\n"
            "Можешь ответить следующим сообщением, чтобы продолжить обращение."
        )
        await update.message.reply_text(f"✅ Ответ по обращению #{ticket_id} отправлен.")
    except Exception:
        await update.message.reply_text(
            "Не удалось отправить ответ. Пользователь должен сначала запустить бота командой /start."
        )

async def close_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Эта команда доступна только администратору.")
        return
    if not context.args:
        await update.message.reply_text("Использование: /close_ticket НОМЕР_ТИКЕТА")
        return
    try:
        ticket_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Номер обращения должен быть числом.")
        return

    with connect_db() as db:
        ticket = db.execute(
            "SELECT user_id FROM tickets WHERE id=?", (ticket_id,)
        ).fetchone()
        if not ticket:
            await update.message.reply_text("Обращение не найдено.")
            return
        db.execute("UPDATE tickets SET status='closed' WHERE id=?", (ticket_id,))
        db.commit()

    try:
        await context.bot.send_message(
            ticket[0], f"🔒 Обращение #{ticket_id} закрыто администратором."
        )
    except Exception:
        pass
    await update.message.reply_text(f"Обращение #{ticket_id} закрыто.")

async def my_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    with connect_db() as db:
        rows = db.execute(
            "SELECT id,status,created_at FROM tickets WHERE user_id=? ORDER BY id DESC LIMIT 10",
            (user_id,)
        ).fetchall()
    if not rows:
        await update.message.reply_text("У тебя пока нет обращений в поддержку.")
        return
    lines = [
        f"#{ticket_id} — {'Открыто' if status == 'open' else 'Закрыто'} — {created}"
        for ticket_id, status, created in rows
    ]
    await update.message.reply_text("🎫 Твои обращения:\n\n" + "\n".join(lines))

async def admin_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Команда доступна только администратору.")
        return
    with connect_db() as db:
        rows = db.execute(
            "SELECT id,user_id,username,created_at FROM tickets WHERE status='open' ORDER BY id DESC"
        ).fetchall()
    if not rows:
        await update.message.reply_text("Открытых обращений нет.")
        return
    lines = [
        f"#{r[0]} — ID пользователя {r[1]} — @{r[2] or 'без_username'} — {r[3]}"
        for r in rows
    ]
    await update.message.reply_text(
        "🎫 ОТКРЫТЫЕ ОБРАЩЕНИЯ\n\n" + "\n".join(lines) +
        "\n\nОтвет: /reply НОМЕР текст\nЗакрыть: /close_ticket НОМЕР"
    )


# ============================================================
# ДОБАВЛЕНИЕ ТОВАРОВ АДМИНИСТРАТОРОМ
# ============================================================
async def add_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Команда доступна только администратору.")
        return
    user_states[update.effective_user.id] = {"step": "product_category"}
    await update.message.reply_text(
        "Добавление товара.\n\nНапиши категорию: Обувь, Одежда, Ремни или Рюкзаки."
    )

async def admin_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Команда доступна только администратору.")
        return
    with connect_db() as db:
        rows = db.execute(
            "SELECT id,customer,phone,total,status FROM orders ORDER BY id DESC LIMIT 20"
        ).fetchall()
    if not rows:
        await update.message.reply_text("Заказов пока нет.")
        return
    text = "\n\n".join(
        f"Заказ #{r[0]}\nПокупатель: {r[1]}\nТелефон: {r[2]}\n"
        f"Сумма: {money(r[3])}\nСтатус: {r[4]}"
        for r in rows
    )
    await update.message.reply_text("📦 Последние заказы:\n\n" + text)


# ============================================================
# ОБРАБОТКА КНОПОК
# ============================================================
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "home":
        await query.edit_message_text("👑 GRACE STORE\n\nГлавное меню:", reply_markup=main_menu())
    elif data == "catalog":
        await show_catalog(query)
    elif data.startswith("cat:"):
        await show_category(query, data.split(":", 1)[1])
    elif data.startswith("product:"):
        await show_product(query, int(data.split(":", 1)[1]))
    elif data.startswith("add:"):
        product_id = int(data.split(":", 1)[1])
        with connect_db() as db:
            row = db.execute("SELECT name,sizes FROM products WHERE id=?", (product_id,)).fetchone()
        if not row:
            await query.answer("Товар не найден.", show_alert=True)
            return
        sizes = [s.strip() for s in row[1].split(",") if s.strip()]
        if not sizes:
            sizes = ["Без размера"]
        keyboard = [
            [InlineKeyboardButton(size, callback_data=f"size:{product_id}:{size}")]
            for size in sizes
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"product:{product_id}")])
        await query.edit_message_text(
            f"📏 Выбери размер для товара «{row[0]}»:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif data.startswith("size:"):
        _, product_id, size = data.split(":", 2)
        carts.setdefault(user_id, []).append((int(product_id), size))
        await query.edit_message_text(
            "✅ Товар добавлен в корзину.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛒 Корзина", callback_data="cart")],
                [InlineKeyboardButton("🛍 Продолжить покупки", callback_data="catalog")]
            ])
        )
    elif data == "cart":
        await show_cart(query, user_id)
    elif data.startswith("remove:"):
        index = int(data.split(":", 1)[1])
        cart = carts.get(user_id, [])
        if 0 <= index < len(cart):
            cart.pop(index)
        await show_cart(query, user_id)
    elif data == "checkout":
        await begin_checkout(query, user_id)
    elif data == "orders":
        with connect_db() as db:
            rows = db.execute(
                "SELECT id,total,status FROM orders WHERE user_id=? ORDER BY id DESC",
                (user_id,)
            ).fetchall()
        text = "📦 Заказов пока нет." if not rows else "📦 ТВОИ ЗАКАЗЫ\n\n" + "\n".join(
            f"#{r[0]} — {money(r[1])} — {r[2]}" for r in rows
        )
        await query.edit_message_text(text, reply_markup=back_button())
    elif data == "profile":
        await query.edit_message_text(
            f"👤 ПРОФИЛЬ\n\nИмя: {query.from_user.full_name}\n"
            f"Telegram ID: {user_id}",
            reply_markup=back_button()
        )
    elif data == "support":
        await query.edit_message_text(
            "🎫 ТЕХНИЧЕСКАЯ ПОДДЕРЖКА\n\n"
            "Нажми кнопку ниже, чтобы создать обращение. "
            "Администратор ответит тебе прямо в этом боте.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Создать обращение", callback_data="new_ticket")],
                [InlineKeyboardButton("📋 Мои обращения", callback_data="my_tickets")],
                [InlineKeyboardButton("⬅️ Меню", callback_data="home")]
            ])
        )
    elif data == "new_ticket":
        with connect_db() as db:
            cursor = db.execute(
                "INSERT INTO tickets (user_id,username) VALUES (?,?)",
                (user_id, query.from_user.username or "")
            )
            ticket_id = cursor.lastrowid
            db.commit()
        user_states[user_id] = {"step": "ticket_message", "ticket_id": ticket_id}
        await query.edit_message_text(
            f"🎫 Обращение #{ticket_id} создано.\n\n"
            "Напиши свой вопрос следующим сообщением."
        )
    elif data == "my_tickets":
        with connect_db() as db:
            rows = db.execute(
                "SELECT id,status,created_at FROM tickets WHERE user_id=? ORDER BY id DESC LIMIT 10",
                (user_id,)
            ).fetchall()
        text = "Обращений пока нет." if not rows else "\n".join(
            f"#{r[0]} — {'Открыто' if r[1] == 'open' else 'Закрыто'} — {r[2]}"
            for r in rows
        )
        await query.edit_message_text("📋 МОИ ОБРАЩЕНИЯ\n\n" + text, reply_markup=back_button("support"))


# ============================================================
# ЕДИНЫЙ ОБРАБОТЧИК ТЕКСТА
# ============================================================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_states.get(user_id)
    text = (update.message.text or "").strip()

    if not state:
        return

    step = state.get("step")

    # Сообщения в тикете
    if step == "ticket_message":
        ticket_id = state["ticket_id"]
        await send_ticket_message(update, context, ticket_id, "user")
        # Оставляем тикет активным: пользователь может писать дальше.
        return

    # Оформление заказа
    if step == "order_name":
        state["customer"] = text
        state["step"] = "order_phone"
        await update.message.reply_text("📱 Напиши номер телефона:")
    elif step == "order_phone":
        state["phone"] = text
        state["step"] = "order_delivery"
        await update.message.reply_text(
            "Выбери способ доставки:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("СДЭК", callback_data="delivery:СДЭК")],
                [InlineKeyboardButton("Почта России", callback_data="delivery:Почта России")]
            ])
        )
    elif step == "order_address":
        state["address"] = text
        await save_order(update, context, user_id, state)

    # Добавление товара администратором
    elif step == "product_category":
        if not is_admin(user_id):
            user_states.pop(user_id, None)
            return
        if text not in CATEGORIES or text == "Куртки":
            await update.message.reply_text("Выбери категорию с товарами: Обувь, Одежда, Ремни, Рюкзаки или Головные уборы.")
            return
        state["category"] = text
        state["step"] = "product_name"
        await update.message.reply_text("Напиши название товара:")
    elif step == "product_name":
        state["name"] = text
        state["step"] = "product_description"
        await update.message.reply_text("Напиши описание товара:")
    elif step == "product_description":
        state["description"] = text
        state["step"] = "product_price"
        await update.message.reply_text("Напиши цену целым числом, например 3465:")
    elif step == "product_price":
        try:
            price = int(text)
            if price <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("Цена должна быть положительным целым числом.")
            return
        state["price"] = price
        state["step"] = "product_sizes"
        await update.message.reply_text("Напиши размеры через запятую. Например: 38,39,40,41")
    elif step == "product_sizes":
        state["sizes"] = text
        state["step"] = "product_photo"
        await update.message.reply_text("Теперь отправь фото товара как фото или напиши «нет».")
    elif step == "product_photo":
        if text.lower() == "нет":
            await finish_product(update, state, "")
        else:
            raw_number = text.strip().lstrip("#")
            if raw_number.isdigit():
                image_name = f"{int(raw_number):03d}.jpg"
                if (PHOTO_DIR / image_name).is_file():
                    await finish_product(update, state, f"local:{image_name}")
                else:
                    await update.message.reply_text("Такого номера фото нет. Посмотри список командой /photos.")
            else:
                await update.message.reply_text("Отправь фото, напиши номер из /photos (например 12) или «нет».")
    elif step == "order_delivery":
        await update.message.reply_text("Пожалуйста, выбери доставку кнопкой выше.")

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_states.get(user_id)
    if state and state.get("step") == "product_photo" and is_admin(user_id):
        photo_id = update.message.photo[-1].file_id
        await finish_product(update, state, photo_id)

async def finish_product(update, state, photo_id):
    with connect_db() as db:
        db.execute(
            """INSERT INTO products (category,name,description,price,sizes,photo)
            VALUES (?,?,?,?,?,?)""",
            (
                state["category"], state["name"], state["description"],
                state["price"], state["sizes"], photo_id
            )
        )
        db.commit()
    user_states.pop(update.effective_user.id, None)
    await update.message.reply_text("✅ Товар добавлен в каталог!")

async def delivery_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    state = user_states.get(user_id)
    if not state or state.get("step") != "order_delivery":
        await query.edit_message_text("Сначала начни оформление заказа заново.")
        return
    state["delivery"] = query.data.split(":", 1)[1]
    state["step"] = "order_address"
    if state["delivery"] == "СДЭК":
        prompt = "📍 Напиши город и адрес пункта выдачи СДЭК или адрес курьерской доставки:"
    else:
        prompt = "📍 Напиши город, улицу, дом, квартиру и почтовый индекс:"
    await query.edit_message_text(prompt)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_states.pop(update.effective_user.id, None)
    await update.message.reply_text("Действие отменено.", reply_markup=main_menu())

async def photos_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Команда доступна только администратору.")
        return
    index_file = Path("photos_index.jpg")
    if index_file.is_file():
        with index_file.open("rb") as f:
            await update.message.reply_photo(
                photo=f,
                caption=("📸 ФОТОБАНК GRACE STORE\n\n"
                         "Выбери номер на листе. При добавлении товара введи этот номер "
                         "на шаге загрузки фото. Например: 12.")
            )
    else:
        await update.message.reply_text("Файл photos_index.jpg не найден в проекте.")


async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Эта команда доступна только администратору.")
        return
    await update.message.reply_text(
        "👑 ПАНЕЛЬ АДМИНИСТРАТОРА\n\n"
        "/addproduct — добавить товар\n"
        "/photos — посмотреть номера фотографий из архива\n"
        "/orders_admin — последние заказы\n"
        "/tickets — открытые обращения\n"
        "/reply НОМЕР текст — ответить на обращение\n"
        "/close_ticket НОМЕР — закрыть обращение\n"
        "/cancel — отменить текущий ввод"
    )


# ============================================================
# ЗАПУСК
# ============================================================
def main():
    if not TOKEN:
        raise RuntimeError("Добавь BOT_TOKEN в переменные окружения Bothost.")
    if ADMIN_ID <= 0:
        raise RuntimeError("Добавь свой числовой ADMIN_ID в переменные окружения Bothost.")

    init_db()
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("addproduct", add_product))
    app.add_handler(CommandHandler("photos", photos_list))
    app.add_handler(CommandHandler("orders_admin", admin_orders))
    app.add_handler(CommandHandler("tickets", admin_tickets))
    app.add_handler(CommandHandler("reply", reply_ticket))
    app.add_handler(CommandHandler("close_ticket", close_ticket))
    app.add_handler(CommandHandler("admin", admin_help))
    app.add_handler(CommandHandler("mytickets", my_tickets))

    app.add_handler(CallbackQueryHandler(delivery_buttons, pattern=r"^delivery:"))
    app.add_handler(CallbackQueryHandler(buttons))

    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    logger.info("GRACE STORE запущен.")
    app.run_polling()

if __name__ == "__main__":
    main()
