import datetime
import logging
from aiogram import Bot, Router, F, types
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from categories.keyboards import CategoryKeyboards
from admin_bot.error_reporter import send_error_to_admin
from db import Database

router = Router()
logger = logging.getLogger(__name__)

STATUS_NEW = 'В обработке'


class CreateOrderFSM(StatesGroup):
    category = State()
    street = State()
    description = State()
    price = State()


class CreateOrderService:
    """Класс для работы с созданием заказов и уведомлениями (ООП)."""

    def __init__(self, db: Database):
        self.db = db

    async def check_client_exists(self, telegram_id: int, user_id: int, mode: str = 'read'):
        """Проверка регистрации заказчика."""
        if mode != 'read':
            return None

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            return await conn.fetchrow(
                """
                SELECT c.user_id, c.city
                FROM clients c
                         JOIN users u ON c.user_id = u.id
                WHERE u.telegram_id = $1
                """,
                telegram_id
            )

    async def create_order(self, client_id: int, category: str,
                           description: str, full_address: str, price: str,
                           user_id: int, mode: str = 'write'):
        """Сохранение заказа и обновление глобальной статистики."""
        if mode != 'write':
            return None

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            async with conn.transaction():
                # Вставка заказа
                new_order = await conn.fetchrow(
                    """
                    INSERT INTO orders (client_id, category, description, city, price, status)
                    VALUES ($1, $2, $3, $4, $5, $6) RETURNING id, created_at
                    """,
                    client_id, category, description, full_address, price, STATUS_NEW
                )

                # Обновление вечной статистики
                await conn.execute(
                    """
                    INSERT INTO global_stats (metric_name, count)
                    VALUES ('total_orders', 1) ON CONFLICT (metric_name) DO
                    UPDATE SET count = global_stats.count + 1
                    """
                )
                return new_order

    async def get_workers_to_notify(self, category: str, sender_id: int, user_id: int, mode: str = 'read'):
        """Поиск подходящих исполнителей для рассылки уведомлений."""
        if mode != 'read':
            return []

        async with self.db.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT u.telegram_id
                FROM users u
                         JOIN workers w ON u.id = w.user_id
                WHERE $1 = ANY (w.skills)
                  AND w.receive_notifications = TRUE
                  AND u.telegram_id != $2
                """,
                category, sender_id
            )


# --- ХЕНДЛЕРЫ ---

@router.message(F.text == "Создать заказ", StateFilter('*'))
async def start_creating_order(message: types.Message, db: Database, state: FSMContext, user_id: int,
                               mode: str = 'write'):
    await state.clear()
    order_service = CreateOrderService(db)

    client_data = await order_service.check_client_exists(user_id, user_id, 'read')

    if not client_data:
        await message.answer("❌ Вы не зарегистрированы как Заказчик.")
        return

    category_keyboards = CategoryKeyboards(db)
    help_text = await category_keyboards.get_help_text(user_id=user_id, mode='read')
    kb = await category_keyboards.get_categories_kb(prefix="category_", user_id=user_id, mode='read')

    await message.answer(help_text, parse_mode='Markdown')
    await message.answer("Выберите категорию для вашего заказа:", reply_markup=kb)
    await state.set_state(CreateOrderFSM.category)


@router.callback_query(F.data.startswith("category_"), CreateOrderFSM.category)
async def get_category(callback: types.CallbackQuery, state: FSMContext, user_id: int, mode: str = 'write'):
    category = callback.data.split("_")[1]
    await state.update_data(category=category)
    await callback.message.edit_text(
        f"Категория: {category}\n\n"
        f"Теперь введите улицу и номер дома (например: Herzl 45):"
    )
    await state.set_state(CreateOrderFSM.street)
    await callback.answer()


@router.message(CreateOrderFSM.street)
async def get_street(message: types.Message, state: FSMContext, user_id: int, mode: str = 'write'):
    await state.update_data(street=message.text.strip())
    await message.answer("Отлично. Теперь введите подробное описание задачи:")
    await state.set_state(CreateOrderFSM.description)


@router.message(CreateOrderFSM.description)
async def get_description(message: types.Message, state: FSMContext, user_id: int, mode: str = 'write'):
    description = message.text.strip().replace("_", "-").replace("*", "").replace("`", "'")

    if len(description) < 30:
        await message.answer("❌ Слишком короткое описание. Пожалуйста, опишите задачу подробнее (минимум 30 символов).")
        return

    await state.update_data(description=description)
    await message.answer("Укажите цену (например: 500) или напишите 'Договорная':")
    await state.set_state(CreateOrderFSM.price)


@router.message(CreateOrderFSM.price)
async def process_order_final(message: types.Message, state: FSMContext, db: Database, user_id: int,
                              mode: str = 'write'):
    price_input = message.text.strip()

    if not price_input.isdigit() and price_input.lower() != 'договорная':
        await message.answer("❌ Введите число или 'Договорная'.")
        return

    price = 'Договорная' if price_input.lower() == 'договорная' else price_input
    user_data = await state.get_data()
    order_service = CreateOrderService(db)

    try:
        client_data = await order_service.check_client_exists(user_id, user_id, 'read')
        full_address = f"{client_data['city']}, {user_data['street']}"

        # 1. Сохранение в БД
        new_order = await order_service.create_order(
            client_id=client_data['user_id'],
            category=user_data['category'],
            description=user_data['description'],
            full_address=full_address,
            price=price,
            user_id=user_id,
            mode='write'
        )

        customers_menu = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text='Создать заказ'), KeyboardButton(text='Мои заказы')],
                [KeyboardButton(text='Мой профиль'), KeyboardButton(text='Главное меню')]
            ],
            resize_keyboard=True
        )

        await message.answer(
            f"✅ Заказ успешно создан!\n\n"
            f"Номер: {new_order['id']}\n"
            f"Категория: {user_data['category']}\n"
            f"Адрес: {full_address}\n"
            f"Цена: {price}",
            reply_markup=customers_menu
        )

        # 2. Уведомление исполнителей
        workers = await order_service.get_workers_to_notify(user_data['category'], user_id, user_id, 'read')

        if workers:
            preview = user_data['description'][:150] + "..."
            notif_text = (
                f"🔔 Новый заказ: {user_data['category']}\n"
                f"🏙 Город: {client_data['city']}\n"
                f"📝 Задача: {preview}\n\n"
                f"Откликнитесь в разделе 'Смотреть заказы'."
            )
            for w in workers:
                try:
                    await message.bot.send_message(w['telegram_id'], notif_text)
                except Exception:
                    continue

    except Exception as e:
        logger.error(f"Ошибка создания заказа: {e}", exc_info=True)
        await send_error_to_admin(message.bot, e, f"Finalize Order: {user_id}")
        await message.answer("❌ Ошибка при создании заказа.")
    finally:
        await state.clear()
