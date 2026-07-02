import asyncio
import logging
import os
import datetime

import asyncpg
import aiohttp
from aiogram import Bot, Dispatcher, F, types
from aiogram.client.session.aiohttp import AiohttpSession
from aiohttp_socks import ProxyConnector
from aiogram.filters import StateFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup
)
from dotenv import load_dotenv

# Этот импорт заработает, как только пропишешь PYTHONPATH
from db import Database

load_dotenv()

# --- ВСПОМОГАТЕЛЬНЫЕ КЛАССЫ ---

class Socks5Session(AiohttpSession):
    """Класс для работы через SOCKS5 прокси."""
    def __init__(self, proxy_url: str):
        super().__init__()
        self.proxy_url = proxy_url

    async def create_session(self) -> aiohttp.ClientSession:
        if getattr(self, "_session", None) is None or self._session.closed:
            connector = ProxyConnector.from_url(self.proxy_url)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session

class AdminStates(StatesGroup):
    waiting_for_search = State()
    waiting_for_broadcast_message = State()

class AdminService:
    """Сервис для административных задач (ООП)."""
    def __init__(self, db: Database):
        self.db = db

    async def get_statistics(self, user_id: int, mode: str = 'read') -> str:
        if mode != 'read' or not self.db.pool:
            return "Ошибка доступа."

        async with self.db.pool.acquire() as conn:
            # Сбор данных
            total_clients = await conn.fetchval("SELECT COUNT(*) FROM clients") or 0
            total_workers = await conn.fetchval("SELECT COUNT(*) FROM workers") or 0
            blocked_users = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_blocked = TRUE") or 0
            total_ever = await conn.fetchval("SELECT count FROM global_stats WHERE metric_name = 'total_orders'") or 0
            completed_ever = await conn.fetchval("SELECT count FROM global_stats WHERE metric_name = 'completed_orders'") or 0
            cancelled_ever = await conn.fetchval("SELECT count FROM global_stats WHERE metric_name = 'cancelled_orders'") or 0
            active_orders = await conn.fetchval("SELECT COUNT(*) FROM orders WHERE status IN ('В обработке', 'В работе')") or 0

        return (
            f"📊 **СТАТИСТИКА ПЛАТФОРМЫ**\n\n"
            f"👥 **Юзеры:** {total_clients + total_workers}\n"
            f"👤 Заказчики: {total_clients} | 🛠 Мастера: {total_workers}\n"
            f"🚫 В бане: {blocked_users}\n\n"
            f"📦 **Заказы (История):**\n"
            f"🌍 Создано: {total_ever}\n"
            f"✅ Завершено: {completed_ever}\n"
            f"🗑 Отменено: {cancelled_ever}\n\n"
            f"⏳ **Сейчас активно:** {active_orders}"
        )

    async def search_users(self, query: str, user_id: int, mode: str = 'read'):
        if mode != 'read' or not self.db.pool: return []
        search_pattern = f"%{query}%"
        async with self.db.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT u.id, u.telegram_id, u.role, u.is_blocked,
                       COALESCE(c.full_name, w.name) as name,
                       COALESCE(c.contact, w.contact) as contact
                FROM users u
                LEFT JOIN clients c ON u.id = c.user_id
                LEFT JOIN workers w ON u.id = w.user_id
                WHERE c.contact ILIKE $1 OR w.contact ILIKE $1 OR CAST(u.telegram_id AS TEXT) = $2
                LIMIT 5
            """, search_pattern, query)

    async def block_user_cascading(self, target_db_id: int, user_id: int, mode: str = 'write'):
        if mode != 'write' or not self.db.pool: return False
        async with self.db.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("UPDATE users SET is_blocked = TRUE WHERE id = $1", target_db_id)
                await conn.execute("DELETE FROM clients WHERE user_id = $1", target_db_id)
                await conn.execute("DELETE FROM workers WHERE user_id = $1", target_db_id)
        return True

# --- КОНФИГУРАЦИЯ ---

ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")
API_TOKEN = os.getenv("API_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
PROXY_URL = "socks5://root:El60T882FZ@170.168.100.47:1080"

# Используем SOCKS5 если нужно
admin_session = Socks5Session(proxy_url=PROXY_URL)
bot = Bot(token=ADMIN_BOT_TOKEN, session=admin_session)
client_bot = Bot(token=API_TOKEN, session=admin_session)

dp = Dispatcher()

admin_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Показать статистику")],
        [KeyboardButton(text="🔍 Поиск пользователя"), KeyboardButton(text="📢 Рассылка сообщений")]
    ],
    resize_keyboard=True
)

# --- ХЕНДЛЕРЫ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("👋 Режим администратора активирован.", reply_markup=admin_kb)

@dp.message(F.text == "📊 Показать статистику")
async def cmd_stats(message: types.Message, db: Database):
    if message.from_user.id != ADMIN_ID: return
    service = AdminService(db)
    text = await service.get_statistics(user_id=message.from_user.id)
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "🔍 Поиск пользователя")
async def start_search(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("Введите телефон или ID:")
    await state.set_state(AdminStates.waiting_for_search)

@dp.message(AdminStates.waiting_for_search)
async def process_search(message: types.Message, state: FSMContext, db: Database):
    service = AdminService(db)
    users = await service.search_users(message.text.strip(), message.from_user.id)
    if not users:
        await message.answer("Ничего не найдено.")
    else:
        for u in users:
            status = "🔴 БАН" if u['is_blocked'] else "🟢 ОК"
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🚫 Бан", callback_data=f"block_{u['id']}")
            ]])
            await message.answer(f"ID: `{u['telegram_id']}`\nИмя: {u['name']}\nСтатус: {status}",
                                 reply_markup=kb, parse_mode="Markdown")
    await state.clear()

@dp.callback_query(F.data.startswith("block_"))
async def handle_block(callback: types.CallbackQuery, db: Database):
    user_db_id = int(callback.data.split("_")[1])
    service = AdminService(db)
    await service.block_user_cascading(user_db_id, callback.from_user.id, 'write')
    await callback.message.edit_text("🔴 Пользователь заблокирован.")

async def main():
    logging.basicConfig(level=logging.INFO)
    db = Database()
    # ИСПОЛЬЗУЕМ ТВОЙ МЕТОД create_pool
    await db.create_pool(user_id=0, mode='write')

    # Middleware для проброса db во все хендлеры
    @dp.update.outer_middleware
    async def db_middleware(handler, event, data):
        data['db'] = db
        return await handler(event, data)

    print("🚀 Админ-панель запущена...")
    try:
        await dp.start_polling(bot)
    finally:
        if db.pool: await db.pool.close()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
