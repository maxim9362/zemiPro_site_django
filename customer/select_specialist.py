import logging
import math

from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from admin_bot.error_reporter import send_error_to_admin
from db import Database


router = Router()
logger = logging.getLogger(__name__)

STATUS_NEW = 'В обработке'


class SelectSpecialist(StatesGroup):
    choosing_category = State()


class OfferOrder(StatesGroup):
    selecting_order = State()


class SpecialistSearchService:
    """Класс для работы с поиском и предложением заказов исполнителям (ООП)."""

    def __init__(self, db: Database):
        self.db = db

    async def get_workers_for_order(self, order_id: int, offset: int, user_id: int, mode: str = 'read'):
        if mode != 'read':
            return None, None, None

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            order_info = await conn.fetchrow(
                "SELECT o.category, o.client_id FROM orders o WHERE o.id = $1",
                order_id
            )

            if not order_info:
                return None, None, None

            target_category = order_info['category']

            workers = await conn.fetch(
                """
                SELECT w.user_id,
                       w.name,
                       w.city,
                       w.skills,
                       w.description,
                       COALESCE(AVG(r.rating), 0) AS avg_rating,
                       COUNT(r.id)                AS review_count
                FROM workers w
                         LEFT JOIN ratings r ON r.worker_id = w.user_id
                WHERE $1 = ANY (w.skills)
                  AND w.user_id != $2
                GROUP BY w.user_id, w.name, w.city, w.skills, w.description
                ORDER BY avg_rating DESC NULLS LAST, review_count DESC
                    LIMIT 5
                OFFSET $3
                """,
                target_category, order_info['client_id'], offset
            )

            total_workers = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM workers w
                WHERE $1 = ANY (w.skills)
                  AND w.user_id != $2
                """,
                target_category, order_info['client_id']
            )

            return target_category, workers, total_workers

    async def get_worker_profile(self, worker_user_id: int, user_id: int, mode: str = 'read'):
        if mode != 'read':
            return None, None, None

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            profile_data = await conn.fetchrow(
                "SELECT w.name, w.city, w.skills, w.description, w.contact FROM workers w WHERE w.user_id = $1",
                worker_user_id
            )

            rating_info = await conn.fetchrow(
                "SELECT AVG(rating) AS avg_rating, COUNT(id) AS review_count FROM ratings WHERE worker_id = $1",
                worker_user_id
            )

            reviews = await conn.fetch(
                """
                SELECT r.rating, r.review_text, c.full_name
                FROM ratings r
                JOIN clients c ON r.client_id = c.user_id
                WHERE r.worker_id = $1 AND r.review_text IS NOT NULL
                ORDER BY r.created_at DESC
                LIMIT 3
                """,
                worker_user_id
            )

            return profile_data, rating_info, reviews

    async def process_direct_offer(self, order_id: int, worker_user_id: int, client_telegram_id: int, user_id: int, mode: str = 'write'):
        if mode != 'write':
            return None, None, None, "error"

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            existing_msg = await conn.fetchval(
                "SELECT message FROM responses WHERE order_id = $1 AND worker_id = $2",
                order_id, worker_user_id
            )

            if existing_msg is not None:
                if existing_msg == 'Отказался':
                    return None, None, None, "declined"
                else:
                    return None, None, None, "already_sent"

            worker_info = await conn.fetchrow(
                "SELECT u.telegram_id, w.name FROM users u JOIN workers w ON u.id = w.user_id WHERE w.user_id = $1",
                worker_user_id
            )
            client_info = await conn.fetchrow(
                "SELECT c.contact, c.full_name FROM clients c JOIN users u ON u.id = c.user_id WHERE u.telegram_id = $1",
                client_telegram_id
            )
            order_info = await conn.fetchrow("SELECT created_at FROM orders WHERE id = $1", order_id)

            await conn.execute(
                "INSERT INTO responses (order_id, worker_id, message) VALUES ($1, $2, $3)",
                order_id, worker_user_id, "Предложение от заказчика"
            )

            return worker_info, client_info, order_info, "success"

    async def get_active_orders_for_offer(self, client_telegram_id: int, category: str, user_id: int, mode: str = 'read'):
        if mode != 'read':
            return None

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            client_id = await conn.fetchval("SELECT id FROM users WHERE telegram_id = $1", client_telegram_id)
            if not client_id:
                return None

            if category:
                return await conn.fetch(
                    "SELECT id, category, description, created_at FROM orders WHERE client_id = $1 AND status = $2 AND category = $3",
                    client_id, STATUS_NEW, category
                )
            else:
                return await conn.fetch(
                    "SELECT id, category, description, created_at FROM orders WHERE client_id = $1 AND status = $2",
                    client_id, STATUS_NEW
                )

    async def get_offer_details(self, worker_id: int, client_telegram_id: int, user_id: int, mode: str = 'read'):
        if mode != 'read':
            return None, None

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            worker_info = await conn.fetchrow(
                "SELECT u.telegram_id, w.name FROM users u JOIN workers w ON u.id = w.user_id WHERE u.id = $1",
                worker_id
            )
            client_info = await conn.fetchrow(
                "SELECT c.contact, c.full_name FROM clients c JOIN users u ON u.id = c.user_id WHERE u.telegram_id = $1",
                client_telegram_id
            )
            return worker_info, client_info


@router.callback_query(F.data.startswith("find_workers_"))
async def find_workers_for_order(callback: types.CallbackQuery, db: Database, user_id: int, mode: str = 'write'):
    parts = callback.data.split("_")
    order_id = int(parts[2])
    offset = int(parts[3])
    current_user_id = callback.from_user.id
    search_service = SpecialistSearchService(db)

    target_category, workers, total_workers = await search_service.get_workers_for_order(
        order_id, offset, current_user_id, 'read'
    )

    if target_category is None:
        await callback.answer("Заказ не найден.", show_alert=True)
        return

    if offset == 0:
        await callback.message.answer(
            f"🔎 Поиск исполнителей\n"
            f"Категория: {target_category}\n"
            f"🌍 Поиск: По всей стране\n\n"
            f"👇 Выберите специалиста, чтобы предложить ему этот заказ."
        )

    if not workers:
        if offset == 0:
            await callback.message.answer("😔 Пока нет исполнителей в этой категории.")
        else:
            await callback.answer("Больше исполнителей нет.")
        return

    for worker in workers:
        avg_rating = worker['avg_rating']
        review_count = worker['review_count']
        rating_display = "⭐" * math.ceil(avg_rating) if avg_rating > 0 else "Нет рейтинга"

        rating_text = f"{rating_display} ({avg_rating:.2f}, {review_count} отзывов)" \
            if review_count > 0 else "Нет оценок"
        skills_text = ", ".join(worker['skills']) if worker['skills'] else "Не указаны"

        worker_text = (
            f"👤 {worker['name']}\n"
            f"🏙 Город: {worker['city']}\n"
            f"⭐ Рейтинг: {rating_text}\n"
            f"📂 Навыки: {skills_text}"
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="👤 Посмотреть профиль",
                    callback_data=f"view_worker_profile_search_{worker['user_id']}_{order_id}"
                )],
                [InlineKeyboardButton(
                    text="📥 Предложить этот заказ",
                    callback_data=f"send_offer_{worker['user_id']}_{order_id}"
                )]
            ]
        )

        await callback.message.answer(worker_text, reply_markup=keyboard, parse_mode='Markdown')

    if offset + 5 < total_workers:
        next_offset = offset + 5
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="➡️ Показать еще",
                callback_data=f"find_workers_{order_id}_{next_offset}"
            )
        ]])
        await callback.message.answer("Показать еще?", reply_markup=kb)

    await callback.answer()


@router.callback_query(F.data.startswith("view_worker_profile_search_"))
async def view_worker_profile_search(callback: types.CallbackQuery, db: Database, user_id: int, mode: str = 'write'):
    parts = callback.data.split("_")
    worker_user_id = int(parts[4])
    order_id = int(parts[5]) if len(parts) > 5 else None
    current_user_id = callback.from_user.id
    search_service = SpecialistSearchService(db)

    profile_data, rating_info, reviews = await search_service.get_worker_profile(
        worker_user_id, current_user_id, 'read'
    )

    avg_rating = rating_info['avg_rating'] if rating_info and rating_info['avg_rating'] is not None else 0
    review_count = rating_info['review_count'] if rating_info else 0
    rating_display = "⭐" * math.ceil(avg_rating if avg_rating is not None else 0)
    rating_text = f"{rating_display} ({avg_rating:.2f}, {review_count} отзывов)" if review_count > 0 else "Нет оценок"
    skills_text = ", ".join(profile_data['skills']) if profile_data['skills'] else "Не указаны"

    reviews_text_list = []
    if reviews:
        for review in reviews:
            reviews_text_list.append(
                f"  👤 {review['full_name']} (Оценка: {'⭐' * review['rating']}):\n"
                f"  {review['review_text']}"
            )
        reviews_text = "\n\n" + "\n\n".join(reviews_text_list)
    else:
        reviews_text = "\n\n_Пока нет текстовых отзывов._"

    profile_text = (
        f"👤 Профиль Исполнителя\n\n"
        f"Имя: {profile_data['name']}\n"
        f"Город: {profile_data['city']}\n"
        f"Контакт: `{profile_data['contact']}`\n"
        f"Рейтинг: {rating_text}\n\n"
        f"Категории услуг: {skills_text}\n\n"
        f"Описание услуг:\n{profile_data['description']}\n\n"
        f"Последние отзывы"
        f"{reviews_text}"
    )

    keyboard_buttons = []
    if order_id:
        keyboard_buttons.append([
            InlineKeyboardButton(
                text="📥 Предложить этот заказ",
                callback_data=f"send_offer_{worker_user_id}_{order_id}"
            )
        ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    await callback.message.answer(profile_text, reply_markup=keyboard, parse_mode='Markdown')
    await callback.answer()


@router.callback_query(F.data.startswith("send_offer_"))
async def send_direct_offer(callback: types.CallbackQuery, db: Database, user_id: int, mode: str = 'write'):
    parts = callback.data.split("_")
    worker_user_id = int(parts[2])
    order_id = int(parts[3])
    client_telegram_id = callback.from_user.id
    search_service = SpecialistSearchService(db)

    worker_info, client_info, order_info, status = await search_service.process_direct_offer(
        order_id, worker_user_id, client_telegram_id, client_telegram_id, 'write'
    )

    if status == "declined":
        await callback.answer("🚫 Этот исполнитель отказался от данного заказа.", show_alert=True)
        return
    elif status == "already_sent":
        await callback.answer("Вы уже отправляли предложение этому исполнителю (или он уже откликнулся).", show_alert=True)
        return
    elif status == "error":
        await callback.answer("❌ Произошла ошибка. Попробуйте позже.", show_alert=True)
        return

    await callback.answer("Предложение отправлено!")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"✅ Предложение отправлено исполнителю {worker_info['name']}.")

    contact_display = client_info['full_name'] or client_info['contact']
    order_date = order_info['created_at'].strftime('%d.%m.%Y')

    notification_text = (
        f"🔔 Вам лично предложили заказ!\n\n"
        f"Заказчик {contact_display} предлагает вам выполнить заказ от {order_date}.\n\n"
        f"Нажмите, чтобы посмотреть детали заказа."
    )

    offer_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="👀 Посмотреть предложение",
                callback_data=f"view_offer_{order_id}_{client_telegram_id}_{order_date}"
            )]
        ]
    )

    try:
        await callback.bot.send_message(
            chat_id=worker_info['telegram_id'],
            text=notification_text,
            reply_markup=offer_keyboard,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить исполнителя: {e}", exc_info=True)
        await send_error_to_admin(callback.bot, e, f"Send Direct Offer: Worker {worker_user_id} Order {order_id}")
        await callback.message.answer("❌ Не удалось отправить предложение...")


@router.callback_query(F.data.startswith("offer_order_"))
async def offer_order_start(callback: types.CallbackQuery, state: FSMContext, db: Database, user_id: int, mode: str = 'write'):
    worker_user_id = int(callback.data.split("_")[2])
    client_telegram_id = callback.from_user.id
    data = await state.get_data()
    category = data.get("selected_category")
    search_service = SpecialistSearchService(db)

    active_orders = await search_service.get_active_orders_for_offer(
        client_telegram_id, category, client_telegram_id, 'read'
    )

    if active_orders is None:
        await callback.answer("❌ Ваш профиль заказчика не найден.", show_alert=True)
        return

    if not active_orders:
        msg = f"У вас нет активных заказов в категории '{category}'." if category else "У вас нет активных заказов."
        await callback.answer(msg, show_alert=True)
        return

    await state.update_data(offer_worker_id=worker_user_id)

    order_buttons = []
    for order in active_orders:
        date_created = order['created_at'].strftime('%d.%m.%Y')
        order_buttons.append([
            InlineKeyboardButton(
                text=f"Заказ от {date_created} ({order['category']})",
                callback_data=f"select_offer_{order['id']}_{date_created}"
            )
        ])

    await callback.message.answer(
        f"Какой из ваших заказов вы хотите предложить?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=order_buttons)
    )
    await state.set_state(OfferOrder.selecting_order)
    await callback.answer()


@router.callback_query(OfferOrder.selecting_order, F.data.startswith("select_offer_"))
async def offer_order_select(callback: types.CallbackQuery, state: FSMContext, db: Database, user_id: int, mode: str = 'write'):
    parts = callback.data.split("_")
    order_id = int(parts[2])
    order_date = parts[3]
    client_telegram_id = callback.from_user.id

    data = await state.get_data()
    worker_id = data.get('offer_worker_id')

    if not worker_id:
        await callback.answer("❌ Ошибка , не найден ID исполнителя. Начните заново.", show_alert=True)
        await state.clear()
        return

    await state.clear()
    search_service = SpecialistSearchService(db)

    worker_info, client_info = await search_service.get_offer_details(
        worker_id, client_telegram_id, client_telegram_id, 'read'
    )

    if not worker_info or not client_info:
        await callback.answer("❌ Ошибка: не найден профиль исполнителя или заказчика.", show_alert=True)
        return

    await callback.message.edit_text(
        f"✅ Предложение по заказу от {order_date} отправлено исполнителю {worker_info['name']}."
    )
    await callback.answer()

    contact_display = client_info['full_name'] or client_info['contact']

    notification_text = (
        f"🔔 Вам лично предложили заказ!\n\n"
        f"Заказчик {contact_display} предлагает вам выполнить заказ от {order_date}.\n\n"
        f"Нажмите, чтобы посмотреть детали заказа."
    )

    offer_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="👀 Посмотреть предложение",
                callback_data=f"view_offer_{order_id}_{client_telegram_id}_{order_date}"
            )]
        ]
    )

    try:
        await callback.bot.send_message(
            chat_id=worker_info['telegram_id'],
            text=notification_text,
            reply_markup=offer_keyboard,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить исполнителя {worker_id} о предложении: {e}", exc_info=True)
        await callback.message.answer("❌ Не удалось отправить предложение исполнителю (возможно, он заблокировал бота).")
