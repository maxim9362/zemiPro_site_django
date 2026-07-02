import logging

from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup
from aiogram.filters import StateFilter

from admin_bot.error_reporter import send_error_to_admin
from db import Database

router = Router()
logger = logging.getLogger(__name__)

STATUS_NEW = 'В обработке'
STATUS_IN_PROGRESS = 'В процессе'
STATUS_COMPLETED = 'Выполнен'
STATUS_CANCELLED = 'Отменен'


class MyOrdersService:
    """Класс для работы с заказами клиента в БД (ООП)."""

    def __init__(self, db: Database):
        self.db = db

    async def get_client_orders(self, telegram_id: int, user_id: int, mode: str = 'read'):
        if mode != 'read': return None, None

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            client_data = await conn.fetchrow(
                "SELECT c.user_id FROM clients c JOIN users u ON c.user_id = u.id WHERE u.telegram_id = $1",
                telegram_id
            )
            if not client_data:
                return None, None

            orders = await conn.fetch(
                """
                SELECT o.id,
                       o.category,
                       o.city,
                       o.description,
                       o.status,
                       o.price,
                       o.created_at,
                       o.worker_id,
                       (SELECT COUNT(r.id) FROM responses r WHERE r.order_id = o.id) AS responses_count,
                       r_check.id IS NOT NULL                                        AS review_left
                FROM orders o
                         LEFT JOIN ratings r_check ON o.id = r_check.order_id
                WHERE o.client_id = $1
                ORDER BY o.created_at DESC
                """,
                client_data['user_id']
            )
            return client_data['user_id'], orders

    async def get_order_worker_info(self, order_id: int, worker_id: int, user_id: int, mode: str = 'read'):
        if mode != 'read': return 0, None

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            responses_count = await conn.fetchval("SELECT COUNT(id) FROM responses WHERE order_id = $1", order_id)
            worker_name = None
            if worker_id:
                worker_name = await conn.fetchval("SELECT name FROM workers WHERE user_id = $1", worker_id)
            return responses_count, worker_name

    async def get_order_responses(self, order_id: int, user_id: int, mode: str = 'read'):
        if mode != 'read': return None, None

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            order_date_row = await conn.fetchval("SELECT created_at FROM orders WHERE id = $1", order_id)
            responders = await conn.fetch(
                """
                SELECT w.user_id,
                       w.name,
                       w.contact,
                       w.skills,
                       r.message,
                       (SELECT AVG(rating) FROM ratings WHERE worker_id = w.user_id) as avg_rating,
                       (SELECT COUNT(id) FROM ratings WHERE worker_id = w.user_id)   as review_count
                FROM responses r
                         JOIN workers w ON w.user_id = r.worker_id
                WHERE r.order_id = $1
                """,
                order_id
            )
            return order_date_row, responders

    async def select_worker(self, order_id: int, worker_id: int, client_telegram_id: int, user_id: int,
                            mode: str = 'write'):
        if mode != 'write': return None, None, None

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            updated = await conn.execute(
                """
                UPDATE orders
                SET status    = $1,
                    worker_id = $2
                WHERE id = $3
                  AND status = $4
                  AND client_id = (SELECT id FROM users WHERE telegram_id = $5)
                """,
                STATUS_IN_PROGRESS, worker_id, order_id, STATUS_NEW, client_telegram_id
            )
            if updated == "UPDATE 0":
                return False, None, None

            worker_info = await conn.fetchrow(
                "SELECT u.telegram_id, w.name FROM users u JOIN workers w ON u.id = w.user_id WHERE u.id = $1",
                worker_id
            )
            client_contact = await conn.fetchval(
                "SELECT c.contact FROM clients c JOIN users u ON c.user_id = u.id WHERE u.telegram_id = $1",
                client_telegram_id
            )
            return True, worker_info, client_contact

    async def get_worker_profile(self, worker_user_id: int, order_id: int, user_id: int, mode: str = 'read'):
        if mode != 'read': return None, None, None, None, None

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            profile_data = await conn.fetchrow(
                "SELECT w.name, w.city, w.skills, w.description, w.contact, u.telegram_id FROM workers w JOIN users u ON w.user_id = u.id WHERE w.user_id = $1",
                worker_user_id
            )
            order_date_row = await conn.fetchval("SELECT created_at FROM orders WHERE id = $1", order_id)
            rating_info = await conn.fetchrow(
                "SELECT AVG(rating) AS avg_rating, COUNT(id) AS review_count FROM ratings WHERE worker_id = $1",
                worker_user_id)
            reviews = await conn.fetch(
                "SELECT r.rating, r.review_text, c.full_name FROM ratings r JOIN clients c ON r.client_id = c.user_id WHERE r.worker_id = $1 AND r.review_text IS NOT NULL ORDER BY r.created_at DESC LIMIT 3",
                worker_user_id
            )
            response_msg = await conn.fetchval("SELECT message FROM responses WHERE order_id = $1 AND worker_id = $2",
                                               order_id, worker_user_id)
            return profile_data, order_date_row, rating_info, reviews, response_msg

    async def get_worker_reviews(self, worker_id: int, offset: int, user_id: int, mode: str = 'read'):
        if mode != 'read': return None, 0

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            reviews = await conn.fetch(
                "SELECT r.rating, r.review_text, c.full_name FROM ratings r JOIN clients c ON r.client_id = c.user_id WHERE r.worker_id = $1 AND r.review_text IS NOT NULL ORDER BY r.created_at DESC LIMIT 5 OFFSET $2",
                worker_id, offset
            )
            total_reviews = await conn.fetchval(
                "SELECT COUNT(id) FROM ratings WHERE worker_id = $1 AND review_text IS NOT NULL", worker_id)
            return reviews, total_reviews

    async def cancel_order(self, order_id: int, telegram_id: int, user_id: int, mode: str = 'write'):
        if mode != 'write': return False

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            client_id = await conn.fetchval("SELECT id FROM users WHERE telegram_id = $1", telegram_id)
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO global_stats (metric_name, count) VALUES ('cancelled_orders', 1) ON CONFLICT (metric_name) DO UPDATE SET count = global_stats.count + 1")
                await conn.execute("DELETE FROM responses WHERE order_id = $1", order_id)
                deleted = await conn.execute("DELETE FROM orders WHERE id = $1 AND client_id = $2 AND status = $3",
                                             order_id, client_id, STATUS_NEW)
                return deleted != "DELETE 0"

    async def complete_order(self, order_id: int, telegram_id: int, user_id: int, mode: str = 'write'):
        if mode != 'write': return None

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            async with conn.transaction():
                order_info = await conn.fetchrow("SELECT category FROM orders WHERE id = $1", order_id)
                result = await conn.fetchrow(
                    "UPDATE orders SET status = $1 WHERE id = $2 AND client_id = (SELECT id FROM users WHERE telegram_id = $3) AND status = $4 RETURNING worker_id",
                    STATUS_COMPLETED, order_id, telegram_id, STATUS_IN_PROGRESS
                )
                if result and order_info:
                    await conn.execute(
                        "INSERT INTO global_stats (metric_name, count) VALUES ('completed_orders', 1) ON CONFLICT (metric_name) DO UPDATE SET count = global_stats.count + 1")
                    await conn.execute(
                        "INSERT INTO category_stats (category, completed_count) VALUES ($1, 1) ON CONFLICT (category) DO UPDATE SET completed_count = category_stats.completed_count + 1",
                        order_info['category'])
                return result['worker_id'] if result else None

    async def cancel_worker(self, order_id: int, telegram_id: int, user_id: int, mode: str = 'write'):
        if mode != 'write': return None, None

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            order_data = await conn.fetchrow(
                "SELECT worker_id FROM orders WHERE id = $1 AND status = $2 AND client_id = (SELECT id FROM users WHERE telegram_id = $3)",
                order_id, STATUS_IN_PROGRESS, telegram_id
            )
            if not order_data: return None, None
            worker_id = order_data['worker_id']

            worker_name = "Исполнитель"
            worker_telegram_id = None
            if worker_id:
                name_val = await conn.fetchval("SELECT name FROM workers WHERE user_id = $1", worker_id)
                if name_val: worker_name = name_val
                worker_telegram_id = await conn.fetchval("SELECT telegram_id FROM users WHERE id = $1", worker_id)

            await conn.execute("UPDATE orders SET status = $1, worker_id = NULL WHERE id = $2", STATUS_NEW, order_id)
            if worker_id:
                await conn.execute("DELETE FROM responses WHERE order_id = $1 AND worker_id = $2", order_id, worker_id)
                await conn.execute("INSERT INTO responses (order_id, worker_id, message) VALUES ($1, $2, 'Отстранен')",
                                   order_id, worker_id)

            return worker_name, worker_telegram_id

    async def delete_history(self, order_id: int, telegram_id: int, user_id: int, mode: str = 'write'):
        if mode != 'write': return False

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            client_id = await conn.fetchval("SELECT id FROM users WHERE telegram_id = $1", telegram_id)
            async with conn.transaction():
                await conn.execute("DELETE FROM responses WHERE order_id = $1", order_id)
                deleted = await conn.execute("DELETE FROM orders WHERE id = $1 AND client_id = $2 AND status = $3",
                                             order_id, client_id, STATUS_COMPLETED)
                return deleted != "DELETE 0"


@router.message(F.text == "Мои заказы", StateFilter('*'))
async def show_my_orders(message: types.Message, db: Database, state: FSMContext, user_id: int, mode: str = 'write'):
    await state.clear()
    current_user_id = message.from_user.id
    orders_service = MyOrdersService(db)

    client_id, orders = await orders_service.get_client_orders(current_user_id, current_user_id, 'read')

    if not client_id:
        await message.answer("❌ Вы не зарегистрированы как Заказчик.")
        return

    if not orders:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text='Создать заказ'), KeyboardButton(text='Мои заказы')],
                [KeyboardButton(text='Мой профиль'), KeyboardButton(text='Главное меню')]
            ],
            resize_keyboard=True
        )
        await message.answer("У тебя пока нет активных заказов 😔", reply_markup=keyboard)
        return

    customers_menu = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='Создать заказ'), KeyboardButton(text='Мои заказы')],
            [KeyboardButton(text='Мой профиль'), KeyboardButton(text='Главное меню')]
        ],
        resize_keyboard=True
    )
    await message.answer("👇 Твои заказы:", reply_markup=customers_menu)

    display_counter = 1
    active_orders = []
    completed_orders = []

    for order in orders:
        if order['status'] in (STATUS_NEW, STATUS_IN_PROGRESS):
            active_orders.append(order)
        elif order['status'] == STATUS_COMPLETED:
            completed_orders.append(order)

    if not active_orders and not completed_orders:
        await message.answer("У тебя пока нет активных или завершенных заказов 😔")
        return

    if active_orders:
        await message.answer("--- Активные заказы ---")
        for order in active_orders:
            responses_count, worker_name = await orders_service.get_order_worker_info(
                order['id'], order['worker_id'], current_user_id, 'read'
            )

            desc_len = len(order['description'])
            description_preview = (
                    order['description'][:100] + ('...' if desc_len > 100 else '')
            )
            responses_text = (
                f"Откликов: {responses_count} 🔔" if responses_count > 0 else "Откликов: 0"
            )
            date_created = order['created_at'].strftime('%d.%m.%Y')

            order_text = (
                f"📌 {display_counter}. Заказ от {date_created}\n"
                f"📂 Категория: {order['category']}\n"
                f"🏙 Город: {order['city']}\n"
                f"💰 Цена: {order['price']}\n"
                f"📝 Статус: {order['status']}\n"
                f"📨 {responses_text}\n\n"
                f"Описание: {description_preview}"
            )

            buttons = []
            if order['status'] == STATUS_NEW:
                buttons.append([
                    InlineKeyboardButton(text="✏️ Изменить", callback_data=f"edit_{order['id']}"),
                    InlineKeyboardButton(text="❌ Удалить", callback_data=f"cancel_order_{order['id']}")
                ])
                buttons.append(
                    [InlineKeyboardButton(text="🔎 Найти исполнителя", callback_data=f"find_workers_{order['id']}_0")])

                if responses_count > 0:
                    buttons.append([InlineKeyboardButton(text=f"👀 Смотреть отклики ({responses_count})",
                                                         callback_data=f"view_responses_{order['id']}")])

            elif order['status'] == STATUS_IN_PROGRESS:
                cancel_text = f"🚫 Отменить {worker_name}" if worker_name else "🚫 Отменить исполнителя"
                buttons.append([InlineKeyboardButton(text="✅ Отметить выполненным",
                                                     callback_data=f"complete_order_{order['id']}")])
                buttons.append([InlineKeyboardButton(text=cancel_text,
                                                     callback_data=f"cancel_worker_{order['id']}_{date_created}")])

            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            await message.answer(order_text, reply_markup=keyboard, parse_mode='Markdown')
            display_counter += 1

    if completed_orders:
        await message.answer("--- Завершенные заказы ---")
        for order in completed_orders:
            desc_len = len(order['description'])
            description_preview = order['description'][:100] + ('...' if desc_len > 100 else '')
            date_created = order['created_at'].strftime('%d.%m.%Y')

            order_text = (
                f"📌 Заказ от {date_created}\n"
                f"📂 Категория: {order['category']}\n"
                f"🏙 Город: {order['city']}\n"
                f"📝 Статус: {order['status']}\n\n"
                f"Описание: {description_preview}"
            )

            buttons = []
            if order['review_left']:
                buttons.append(
                    [InlineKeyboardButton(text="🗑️ Удалить из истории", callback_data=f"delete_history_{order['id']}")])
            else:
                buttons.append([InlineKeyboardButton(text="🌟 Оставить отзыв",
                                                     callback_data=f"rate_work_{order['id']}_{order['worker_id']}")])

            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            await message.answer(order_text, reply_markup=keyboard, parse_mode='Markdown')


@router.callback_query(F.data.startswith("view_responses_"))
async def view_order_responses(callback: types.CallbackQuery, db: Database, user_id: int, mode: str = 'write'):
    parts = callback.data.split("_")
    order_id = int(parts[2])
    current_user_id = callback.from_user.id
    orders_service = MyOrdersService(db)

    order_date_row, responders = await orders_service.get_order_responses(order_id, current_user_id, 'read')
    order_date = order_date_row.strftime('%d.%m.%Y') if order_date_row else "..."

    if not responders:
        await callback.answer("❌ Нет доступных откликов.", show_alert=True)
        return

    await callback.message.answer(f"👇 Отклики по заказу от {order_date}:")

    for worker in responders:
        avg_val = worker['avg_rating'] if worker['avg_rating'] else 0
        rev_count = worker['review_count']
        stars = "⭐" * int(avg_val) if avg_val > 0 else ""
        rating_line = f"{stars} {avg_val:.1f} ({rev_count} отз.)" if rev_count > 0 else "Нет оценок"
        skills_text = ", ".join(worker['skills']) if worker['skills'] else "Не указаны"

        response_msg = worker['message']
        is_pending = response_msg == "Предложение от заказчика"
        is_declined = response_msg == "Отказался"

        status_line = ""
        if is_pending:
            status_line = "\n⏳ Статус: Ожидается ответ исполнителя"
        elif is_declined:
            status_line = "\n🚫 Статус: Исполнитель отказался"

        worker_text = (
            f"👤 {worker['name']}\n"
            f"🌟 Рейтинг: {rating_line}\n"
            f"📞 Контакт: `{worker['contact']}`\n"
            f"📂 Навыки: {skills_text}"
            f"{status_line}"
        )

        keyboard_buttons = []
        if not is_pending and not is_declined:
            keyboard_buttons.append([InlineKeyboardButton(text="👉 Выбрать этого исполнителя",
                                                          callback_data=f"select_worker_{order_id}_{worker['user_id']}_{order_date}")])

        keyboard_buttons.append([InlineKeyboardButton(text="👤 Посмотреть профиль",
                                                      callback_data=f"view_response_profile_{worker['user_id']}_{order_id}")])

        await callback.message.answer(worker_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons),
                                      parse_mode='Markdown')

    await callback.answer()


@router.callback_query(F.data.startswith("select_worker_"))
async def select_worker_for_order(callback: types.CallbackQuery, db: Database, user_id: int, mode: str = 'write'):
    parts = callback.data.split("_")
    order_id = int(parts[2])
    worker_id = int(parts[3])
    order_date = parts[4]
    client_telegram_id = callback.from_user.id
    orders_service = MyOrdersService(db)

    success, worker_info, client_contact = await orders_service.select_worker(
        order_id, worker_id, client_telegram_id, client_telegram_id, 'write'
    )

    if not success:
        await callback.answer("❌ Не удалось выбрать исполнителя", show_alert=True)
        return

    await callback.message.answer(
        f"✅ Вы выбрали исполнителя!\n"
        f"Заказ от {order_date} переведен в статус: {STATUS_IN_PROGRESS}.\n"
        f"Исполнитель {worker_info['name']} уведомлен."
    )
    await callback.answer("Исполнитель выбран!")

    contact_display = f"@{callback.from_user.username}" if callback.from_user.username else client_contact

    keyboard_to_worker = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Связаться с заказчиком", url=f"tg://user?id={client_telegram_id}")]])

    try:
        await callback.bot.send_message(
            chat_id=worker_info['telegram_id'],
            text=f"🎉 Вас выбрали исполнителем по заказу от {order_date}!\n\nЗаказчик: `{contact_display}`\nСвяжитесь с ним для уточнения деталей.",
            reply_markup=keyboard_to_worker, parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить исполнителя {worker_id}: {e}", exc_info=True)
        await send_error_to_admin(callback.bot, e, f"Select Worker (Notify): Worker {worker_id} Order {order_id}")


@router.callback_query(F.data.startswith("view_response_profile_"))
async def view_response_profile(callback: types.CallbackQuery, db: Database, user_id: int, mode: str = 'write'):
    parts = callback.data.split("_")
    worker_user_id = int(parts[3])
    order_id = int(parts[4])
    current_user_id = callback.from_user.id
    orders_service = MyOrdersService(db)

    profile_data, order_date_row, rating_info, reviews, response_msg = await orders_service.get_worker_profile(
        worker_user_id, order_id, current_user_id, 'read'
    )

    if not profile_data:
        await callback.answer("❌ Ошибка: Профиль исполнителя не найден.", show_alert=True)
        return

    order_date = order_date_row.strftime('%d.%m.%Y') if order_date_row else "..."
    avg_rating = rating_info['avg_rating'] if rating_info and rating_info['avg_rating'] else 0
    review_count = rating_info['review_count'] if rating_info else 0
    rating_text = f"{'⭐' * int(avg_rating)} ({avg_rating:.2f}, {review_count} отзывов)" if avg_rating > 0 else "Нет оценок"
    skills_text = ", ".join(profile_data['skills']) if profile_data['skills'] else "Не указаны"

    reviews_text_list = []
    if reviews:
        for review in reviews:
            reviews_text_list.append(
                f"  👤 {review['full_name']} (Оценка: {'⭐' * review['rating']}):\n  {review['review_text']}")
        reviews_text = "\n\n" + "\n\n".join(reviews_text_list)
    else:
        reviews_text = "\n\n_Пока нет текстовых отзывов._"

    is_pending = response_msg == "Предложение от заказчика"
    is_declined = response_msg == "Отказался"
    status_info = "\n\n⏳ Статус: Ожидается ответ исполнителя" if is_pending else "\n\n🚫 Статус: Исполнитель отказался от заказа" if is_declined else ""

    profile_text = (
        f"👤 Профиль Исполнителя\n\nИмя: {profile_data['name']}\nГород: {profile_data['city']}\n"
        f"Контакт: `{profile_data['contact']}`\nРейтинг: {rating_text}\n\nКатегории услуг: {skills_text}\n\n"
        f"Описание услуг:\n{profile_data['description']}{status_info}\n\nПоследние отзывы{reviews_text}"
    )

    keyboard_buttons = []
    if not is_pending and not is_declined:
        keyboard_buttons.append([InlineKeyboardButton(text="✅ Выбрать этого исполнителя",
                                                      callback_data=f"select_worker_{order_id}_{worker_user_id}_{order_date}")])
    if review_count > 0:
        keyboard_buttons.append([InlineKeyboardButton(text=f"📖 Читать отзывы ({review_count})",
                                                      callback_data=f"read_reviews_other_{worker_user_id}_0")])

    await callback.message.answer(profile_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons),
                                  parse_mode='Markdown')
    await callback.answer()


@router.callback_query(F.data.startswith("read_reviews_other_"))
async def read_worker_reviews(callback: types.CallbackQuery, db: Database, user_id: int, mode: str = 'write'):
    parts = callback.data.split("_")
    worker_id = int(parts[3])
    offset = int(parts[4])
    current_user_id = callback.from_user.id
    orders_service = MyOrdersService(db)

    reviews, total_reviews_count = await orders_service.get_worker_reviews(worker_id, offset, current_user_id,
                                                                           'read')

    if not reviews:
        await callback.answer("Больше отзывов нет.", show_alert=True)
        return

    await callback.message.answer(f" Отзывы (с {offset + 1} по {offset + len(reviews)}) ")
    await callback.message.answer(
        "\n\n".join([f"👤 {r['full_name']} (Оценка: {'⭐' * r['rating']}):\n{r['review_text']}" for r in reviews]),
        parse_mode='Markdown')

    if offset + 5 < total_reviews_count:
        next_offset = offset + 5
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"Показать еще 5 (из {total_reviews_count})",
                                  callback_data=f"read_reviews_other_{worker_id}_{next_offset}")]])
        await callback.message.answer("Показать следующие?", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("cancel_order_"))
async def cancel_my_order(callback: types.CallbackQuery, db: Database, user_id: int, mode: str = 'write'):
    order_id = int(callback.data.split("_")[2])
    current_user_id = callback.from_user.id
    orders_service = MyOrdersService(db)

    try:
        success = await orders_service.cancel_order(order_id, current_user_id, current_user_id, 'write')
        if not success:
            await callback.answer("❌ Нельзя удалить заказ.", show_alert=True)
            return

        await callback.answer("Заказ удален")
        await callback.message.edit_text(callback.message.text + "\n\n❌ Заказ был удален.")
    except Exception as e:
        logger.error(f"Ошибка при удалении заказа {order_id}: {e}", exc_info=True)
        await send_error_to_admin(callback.bot, e, f"Cancel Order: {order_id} (User {current_user_id})")
        await callback.answer("Ошибка при удалении заказа", show_alert=True)


@router.callback_query(F.data.startswith("complete_order_"))
async def complete_my_order(callback: types.CallbackQuery, db: Database, user_id: int, mode: str = 'write'):
    order_id = int(callback.data.split("_")[2])
    current_user_id = callback.from_user.id
    orders_service = MyOrdersService(db)

    worker_id = await orders_service.complete_order(order_id, current_user_id, current_user_id, 'write')

    if not worker_id:
        await callback.answer("❌ Ошибка: статус не изменен (возможно, заказ уже завершен).", show_alert=True)
        return

    await callback.answer("Заказ отмечен как выполненный!")
    review_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌟 Оставить отзыв", callback_data=f"rate_work_{order_id}_{worker_id}")]])
    await callback.message.edit_text(
        callback.message.text + f"\n\n✅ СТАТУС: {STATUS_COMPLETED}\n\n👇 Пожалуйста, оцените работу исполнителя:",
        reply_markup=review_kb)


@router.callback_query(F.data.startswith("cancel_worker_"))
async def cancel_worker(callback: types.CallbackQuery, db: Database, user_id: int, mode: str = 'write'):
    parts = callback.data.split("_")
    order_id = int(parts[2])
    order_date = parts[3]
    current_user_id = callback.from_user.id
    orders_service = MyOrdersService(db)

    worker_name, worker_telegram_id = await orders_service.cancel_worker(order_id, current_user_id,
                                                                         current_user_id, 'write')

    if worker_name is None:
        await callback.answer("❌ Не удалось отменить.", show_alert=True)
        return

    await callback.answer("Исполнитель отменен!")
    await callback.message.edit_text(
        callback.message.text + f"\n\n🚫 Исполнитель {worker_name} отменен. Заказ возвращен в поиск.")

    if worker_telegram_id:
        try:
            await callback.bot.send_message(chat_id=worker_telegram_id,
                                            text=f"🚫 Заказчик отменил вас как исполнителя по заказу от {order_date}.")
        except Exception as e:
            logger.error(f"Не удалось уведомить исполнителя об отмене: {e}", exc_info=True)
            await send_error_to_admin(callback.bot, e,
                                      f"Cancel Worker (Notify): Worker {worker_telegram_id} Order {order_id}")


@router.callback_query(F.data.startswith("delete_history_"))
async def delete_order_from_history(callback: types.CallbackQuery, db: Database, user_id: int, mode: str = 'write'):
    order_id = int(callback.data.split("_")[2])
    current_user_id = callback.from_user.id
    orders_service = MyOrdersService(db)

    try:
        success = await orders_service.delete_history(order_id, current_user_id, current_user_id, 'write')
        if not success:
            await callback.answer("❌ Не удалось удалить.", show_alert=True)
            return

        await callback.answer("Заказ удален.")
        await callback.message.edit_text(callback.message.text + "\n\n🗑️ Заказ удален из истории.")
    except Exception as e:
        logger.error(f"Ошибка при удалении заказа {order_id} из истории: {e}", exc_info=True)
        await send_error_to_admin(callback.bot, e, f"Delete History: {order_id} (User {current_user_id})")
        await callback.answer("Ошибка", show_alert=True)
