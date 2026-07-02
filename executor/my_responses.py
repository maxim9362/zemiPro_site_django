import logging

from aiogram import Bot, F, Router, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from admin_bot.error_reporter import send_error_to_admin
from db import Database

router = Router()
logger = logging.getLogger(__name__)

STATUS_NEW = 'В обработке'
STATUS_IN_PROGRESS = 'В процессе'
STATUS_COMPLETED = 'Выполнен'


class MyResponsesService:
    """Класс для работы с откликами Исполнителя в БД (ООП)."""

    def __init__(self, db: Database):
        self.db = db

    async def get_my_responses(self, telegram_id: int, user_id: int, mode: str = 'read'):
        """Получение списка всех откликов исполнителя."""
        if mode != 'read':
            return None, None

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            worker_id = await conn.fetchval(
                """
                SELECT u.id
                FROM users u
                         JOIN workers w ON w.user_id = u.id
                WHERE u.telegram_id = $1
                """,
                telegram_id
            )

            if not worker_id:
                return None, None

            responses = await conn.fetch(
                """
                SELECT r.created_at  AS response_date,
                       r.message     AS response_msg,
                       o.id          AS order_id,
                       o.category,
                       o.description,
                       o.status,
                       o.created_at  AS order_date,
                       o.worker_id   AS chosen_worker_id,
                       u.telegram_id AS client_telegram_id
                FROM responses r
                         JOIN orders o ON r.order_id = o.id
                         JOIN users u ON o.client_id = u.id
                WHERE r.worker_id = $1
                ORDER BY r.created_at DESC
                """,
                worker_id
            )
            return worker_id, responses

    async def get_order_details(self, order_id: int, user_id: int, mode: str = 'read'):
        """Получение деталей заказа для персонального предложения."""
        if mode != 'read':
            return None

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            return await conn.fetchrow(
                """
                SELECT category, city, price, description, status, created_at
                FROM orders
                WHERE id = $1
                """,
                order_id,
            )

    async def process_offer_accept(self, order_id: int, worker_telegram_id: int, user_id: int,
                                   mode: str = 'write'):
        """Обработка принятия персонального предложения."""
        if mode != 'write':
            return None, None

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            worker_data = await conn.fetchrow(
                """
                SELECT u.id, w.name, w.contact
                FROM users u
                         JOIN workers w ON u.id = w.user_id
                WHERE u.telegram_id = $1
                """,
                worker_telegram_id
            )

            if not worker_data:
                return None, None

            internal_worker_id = worker_data['id']
            worker_name = worker_data['name']
            worker_contact = worker_data['contact']

            existing_response = await conn.fetchrow(
                "SELECT id, message FROM responses WHERE order_id = $1 AND worker_id = $2",
                order_id, internal_worker_id
            )

            if existing_response:
                if existing_response['message'] == "Принял предложение заказчика":
                    return "already_accepted", None
                else:
                    await conn.execute(
                        "UPDATE responses SET message = $1 WHERE id = $2",
                        "Принял предложение заказчика", existing_response['id']
                    )
            else:
                await conn.execute(
                    """
                    INSERT INTO responses (order_id, worker_id, message)
                    VALUES ($1, $2, $3)
                    """,
                    order_id, internal_worker_id, "Принял предложение заказчика"
                )

            return "success", {'name': worker_name, 'contact': worker_contact}

    async def process_offer_decline(self, order_id: int, worker_telegram_id: int, user_id: int,
                                    mode: str = 'write'):
        """Обработка отказа от персонального предложения."""
        if mode != 'write':
            return None

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE responses
                SET message = 'Отказался'
                WHERE order_id = $1
                  AND worker_id = (SELECT id
                                   FROM users
                                   WHERE telegram_id = $2)
                """,
                order_id, worker_telegram_id
            )

            worker_name = await conn.fetchval(
                """
                SELECT w.name
                FROM workers w
                         JOIN users u ON u.id = w.user_id
                WHERE u.telegram_id = $1
                """,
                worker_telegram_id
            )
            return worker_name


@router.message(F.text == "Мои отклики", StateFilter('*'))
async def show_my_responses(message: types.Message, state: FSMContext, db: Database, user_id: int, mode: str = 'write'):
    await state.clear()
    user_telegram_id = message.from_user.id
    responses_service = MyResponsesService(db)

    worker_id, responses = await responses_service.get_my_responses(
        telegram_id=user_telegram_id, user_id=user_telegram_id, mode='read'
    )

    if worker_id is None:
        await message.answer("❌ Вы не зарегистрированы как Исполнитель.")
        return

    if not responses:
        await message.answer("😔 Ты еще не откликался ни на один заказ.")
        return

    await message.answer(f"📦 Найдено {len(responses)} твоих откликов:")

    for resp in responses:
        desc_len = len(resp['description'])
        description_preview = (
                resp['description'][:100] + ('...' if desc_len > 100 else '')
        )
        order_date_formatted = resp['order_date'].strftime('%d.%m.%Y')
        response_date_formatted = resp['response_date'].strftime('%d.%m.%Y %H:%M')

        status_text = ""
        keyboard = None

        if resp['response_msg'] == 'Отказался':
            status_text = "🚫 Вы отказались от этого заказа."
        elif resp['status'] == STATUS_NEW:
            status_text = "⏳ Заказчик еще не выбрал исполнителя."
        elif resp['status'] == STATUS_IN_PROGRESS:
            if resp['chosen_worker_id'] == worker_id:
                status_text = "✅ Заказчик выбрал вас!"
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(
                            text="💬 Написать заказчику",
                            url=f"tg://user?id={resp['client_telegram_id']}"
                        )]
                    ]
                )
            else:
                status_text = "⚠️ Заказчик выбрал другого исполнителя."
        elif resp['status'] == STATUS_COMPLETED:
            status_text = "🏁 Заказ выполнен."

        response_card = (
            f"📌 Отклик на заказ от {order_date_formatted}\n"
            f"Откликнулся: {response_date_formatted}\n\n"
            f"📂 Категория: {resp['category']}\n"
            f"📝 Описание: {description_preview}\n\n"
            f"Статус заказа: {status_text}"
        )

        await message.answer(
            response_card,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )


@router.callback_query(F.data.startswith("view_offer_"))
async def handle_view_offer(callback: types.CallbackQuery, db: Database, user_id: int, mode: str = 'write'):
    parts = callback.data.split("_")
    order_id = int(parts[2])
    client_telegram_id = int(parts[3])
    order_date = parts[4]
    current_user_id = callback.from_user.id
    responses_service = MyResponsesService(db)

    order_details = await responses_service.get_order_details(
        order_id=order_id, user_id=current_user_id, mode='read'
    )

    if not order_details:
        await callback.answer("❌ Заказ не найден (возможно, отменен).", show_alert=True)
        await callback.message.edit_text("❌ Заказ не найден.")
        return

    if order_details['status'] != STATUS_NEW:
        await callback.answer("❌ Это предложение уже неактуально.", show_alert=True)
        await callback.message.edit_text("❌ Предложение больше неактуально (заказ взят в работу или отменен).")
        return

    order_text = (
        f"🔔 Вам предложили заказ от {order_date}\n\n"
        f"📂 Категория: {order_details['category']}\n"
        f"🏙  Город/Адрес: {order_details['city']}\n"
        f"💰 Цена: {order_details['price']}\n\n"
        f"📝 Задача: \n{order_details['description']}"
    )

    offer_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="✅ Принять",
                callback_data=f"offer_accept_{order_id}_{client_telegram_id}_{order_date}"
            )],
            [InlineKeyboardButton(
                text="❌ Отказаться",
                callback_data=f"offer_decline_{order_id}_{client_telegram_id}_{order_date}"
            )]
        ]
    )

    await callback.message.edit_text(
        order_text,
        reply_markup=offer_keyboard,
        parse_mode='Markdown'
    )
    await callback.answer()


@router.callback_query(F.data.startswith("offer_accept_"))
async def handle_offer_accept(
        callback: types.CallbackQuery,
        bot: Bot,
        db: Database,
        user_id: int,
        mode: str = 'write'
):
    parts = callback.data.split("_")
    order_id = int(parts[2])
    client_telegram_id = int(parts[3])
    order_date = parts[4]
    worker_telegram_id = callback.from_user.id
    responses_service = MyResponsesService(db)

    status, worker_info = await responses_service.process_offer_accept(
        order_id=order_id, worker_telegram_id=worker_telegram_id, user_id=worker_telegram_id, mode='write'
    )

    if status is None:
        await callback.answer("❌ Ошибка: профиль не найден.", show_alert=True)
        return

    if status == "already_accepted":
        await callback.answer("Вы уже приняли это предложение.", show_alert=True)
        keyboard_contact_client = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="💬 Связаться с заказчиком",
                    url=f"tg://user?id={client_telegram_id}"
                )]
            ]
        )
        await callback.message.edit_text(
            "✅ Предложение уже принято.",
            reply_markup=keyboard_contact_client
        )
        return

    keyboard_contact_client = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="💬 Связаться с заказчиком",
                url=f"tg://user?id={client_telegram_id}"
            )]
        ]
    )

    await callback.message.edit_text(
        f"✅ Вы приняли предложение по заказу от {order_date}!\n\n"
        f"Заказчик уведомлен.",
        reply_markup=keyboard_contact_client
    )
    await callback.answer("Предложение принято!")

    worker_name = worker_info['name']
    worker_contact = worker_info['contact']
    contact_display = worker_contact or f"@{callback.from_user.username}"

    notification_text = (
        f"✅ Исполнитель {worker_name} ПРИНЯЛ ваше предложение "
        f"по Заказу от {order_date}!\n\n"
        f"Контакт исполнителя: {contact_display}\n\n"
        f"Теперь вы можете выбрать его в \n\n"
        f"'Моих заказах' -> 'Смотреть отклики'."
    )

    keyboard_to_executor = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="💬 Написать исполнителю",
                url=f"tg://user?id={worker_telegram_id}"
            )]
        ]
    )

    try:
        await bot.send_message(
            chat_id=client_telegram_id,
            text=notification_text,
            reply_markup=keyboard_to_executor
        )
    except Exception as e:
        logger.error(
            f"ОШИБКА уведомления заказчика {client_telegram_id}: {e}",
            exc_info=True
        )
        await send_error_to_admin(
            callback.bot, e,
            f"Offer Accept: Client {client_telegram_id} Order {order_id}"
        )


@router.callback_query(F.data.startswith("offer_decline_"))
async def handle_offer_decline(
        callback: types.CallbackQuery,
        bot: Bot,
        db: Database,
        user_id: int,
        mode: str = 'write'
):
    parts = callback.data.split("_")
    order_id = int(parts[2])
    client_telegram_id = int(parts[3])
    order_date = parts[4]
    worker_telegram_id = callback.from_user.id
    responses_service = MyResponsesService(db)

    worker_name = await responses_service.process_offer_decline(
        order_id=order_id, worker_telegram_id=worker_telegram_id, user_id=worker_telegram_id, mode='write'
    )

    await callback.message.edit_text(
        f"🚫 Вы отклонили предложение по заказу от {order_date}."
    )
    await callback.answer("Предложение отклонено.")

    notification_text = (
        f"🚫 Увы, исполнитель {worker_name or ''} отклонил ваше предложение "
        f"по Заказу от {order_date}.\n\n"
        f"Вы можете предложить его другому исполнителю."
    )
    try:
        await bot.send_message(
            chat_id=client_telegram_id,
            text=notification_text
        )
    except Exception as e:
        logger.error(
            f"Не удалось уведомить заказчика {client_telegram_id} об отклонении: {e}",
            exc_info=True
        )
        await send_error_to_admin(
            callback.bot, e,
            f"Offer Decline: Client {client_telegram_id} Order {parts[2]}"
        )
