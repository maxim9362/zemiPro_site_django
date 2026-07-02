import logging

from aiogram import F, Router, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from admin_bot.error_reporter import send_error_to_admin
from db import Database

router = Router()
logger = logging.getLogger(__name__)

ORDER_STATUS_NEW = 'В обработке'


class NewOrdersService:
    """Класс для работы с новыми заказами в БД (ООП)."""

    def __init__(self, db: Database):
        self.db = db

    async def get_executor_data(self, telegram_id: int, user_id: int, mode: str = 'read'):
        """Получение данных исполнителя (навыки и внутренний ID)."""
        if mode != 'read':
            return None

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            return await conn.fetchrow(
                """
                SELECT w.city, w.skills, u.id AS user_id, w.name AS executor_name, w.contact AS executor_contact
                FROM workers w
                         JOIN users u ON u.id = w.user_id
                WHERE u.telegram_id = $1
                """,
                telegram_id
            )

    async def get_new_orders(self, executor_skills: list, executor_user_id: int, user_id: int,
                             mode: str = 'read'):
        """Поиск подходящих новых заказов по навыкам."""
        if mode != 'read':
            return None

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT DISTINCT
                ON (o.id)
                    o.id, o.category, o.city, o.description, o.client_id,
                    o.price, o.created_at,
                    u_client.telegram_id AS client_tg_id,
                    r.id AS response_id,
                    r.message AS response_message
                FROM orders o
                    JOIN users u_client
                ON u_client.id = o.client_id
                    LEFT JOIN responses r ON r.order_id = o.id AND r.worker_id = $3
                WHERE o.status = $1
                  AND o.category = ANY ($2::TEXT[])
                  AND o.client_id != $3
                ORDER BY o.id DESC
                    LIMIT 5
                """,
                ORDER_STATUS_NEW, executor_skills, executor_user_id
            )

    async def check_existing_response(self, order_id: int, worker_id: int, user_id: int,
                                      mode: str = 'read'):
        """Проверка, откликался ли уже исполнитель на этот заказ."""
        if mode != 'read':
            return None

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            return await conn.fetchrow(
                """
                SELECT message
                FROM responses
                WHERE order_id = $1
                  AND worker_id = $2
                """,
                order_id, worker_id
            )

    async def get_client_data_and_create_response(
            self,
            order_id: int,
            worker_id: int,
            user_id: int,
            mode: str = 'write'
    ):
        """Получение данных заказчика и создание отклика (в одной транзакции)."""
        if mode != 'write':
            return None

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            async with conn.transaction():
                # Сначала проверяем статус и получаем данные клиента
                client_data = await conn.fetchrow(
                    """
                    SELECT c.full_name   AS client_name,
                           c.contact     AS client_contact,
                           u.telegram_id AS client_tg_id,
                           o.created_at
                    FROM orders o
                             JOIN users u ON u.id = o.client_id
                             JOIN clients c ON c.user_id = u.id
                    WHERE o.id = $1
                      AND o.status = $2
                    """,
                    order_id, ORDER_STATUS_NEW
                )

                if not client_data:
                    return None

                # Если заказ еще актуален, создаем отклик
                await conn.execute(
                    "INSERT INTO responses (order_id, worker_id) VALUES ($1, $2)",
                    order_id, worker_id
                )

                return client_data


@router.message(F.text.in_({'Смотреть заказы', 'Новые заказы'}), StateFilter('*'))
async def show_new_orders(message: types.Message, state: FSMContext, db: Database, user_id: int, mode: str = 'write'):
    await state.clear()
    user_telegram_id = message.from_user.id
    orders_service = NewOrdersService(db)

    # Используем сервис (режим read)
    executor_data = await orders_service.get_executor_data(
        telegram_id=user_telegram_id, user_id=user_telegram_id, mode='read'
    )

    if not executor_data:
        await message.answer(
            "❌ Вы не зарегистрированы как Исполнитель. "
            "Пожалуйста, пройдите регистрацию."
        )
        return

    executor_skills = executor_data['skills']
    executor_user_id = executor_data['user_id']

    if not executor_skills:
        await message.answer(
            "⚠️ Ваш профиль Исполнителя не содержит категорий услуг. "
            "Добавьте их в 'Мой профиль', чтобы видеть заказы."
        )
        return

    # Используем сервис (режим read)
    orders = await orders_service.get_new_orders(
        executor_skills=executor_skills, executor_user_id=executor_user_id, user_id=user_telegram_id, mode='read'
    )

    if not orders:
        await message.answer(
            f"💼 Новых заказов по вашим категориям "
            f"({', '.join(executor_skills)}) пока нет 😔"
        )
        return

    # Считаем реальное количество заказов (исключая "Отстранен")
    visible_orders_count = 0
    for order in orders:
        if order['response_message'] != 'Отстранен':
            visible_orders_count += 1

    if visible_orders_count == 0:
        await message.answer("💼 Подходящих новых заказов пока нет.")
        return

    await message.answer(
        f"📦 Найдено {visible_orders_count} новых подходящих заказов:"
    )

    for order in orders:
        response_id = order['response_id']
        response_msg = order['response_message']

        # Если исполнитель был отстранен, пропускаем этот заказ
        if response_msg == 'Отстранен':
            continue

        desc_len = len(order['description'])
        description_preview = (
                order['description'][:150] + ('...' if desc_len > 150 else '')
        )
        date_created = order['created_at'].strftime('%d.%m.%Y')

        order_text = (
            f"📌 Заказ от {date_created}\n"
            f"📂 Категория: {order['category']}\n"
            f"🏙 Город/Адрес: {order['city']}\n"
            f"💰 Цена: {order['price']}\n"
            f"📝 Задача: {description_preview}"
        )

        keyboard = None

        # --- ЛОГИКА СТАТУСОВ ---
        if response_msg == 'Предложение от заказчика':
            order_text = "⚡️ Вам предложили этот заказ!\n" + order_text
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ Принять",
                            callback_data=f"offer_accept_{order['id']}_{order['client_tg_id']}_{date_created}"
                        ),
                        InlineKeyboardButton(
                            text="❌ Отказаться",
                            callback_data=f"offer_decline_{order['id']}_{order['client_tg_id']}_{date_created}"
                        )
                    ]
                ]
            )
        elif response_msg == 'Отказался':
            order_text += "\n\n🚫 Вы отказались от этого заказа."
            keyboard = None
        elif response_id is not None:
            # Отклик существует в базе (даже если текст пустой)
            order_text += "\n\n✅ Вы уже откликнулись на этот заказ."
            keyboard = None
        else:
            # Отклика нет вообще — показываем кнопку
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(
                        text="📞 Откликнуться",
                        callback_data=f"contact_{order['id']}"
                    )]
                ]
            )

        await message.answer(order_text, reply_markup=keyboard, parse_mode='Markdown')


@router.callback_query(F.data.startswith("contact_"))
async def contact_client(callback: types.CallbackQuery, db: Database, user_id: int, mode: str = 'write'):
    order_id = int(callback.data.split("_")[1])
    executor_telegram_id = callback.from_user.id
    orders_service = NewOrdersService(db)

    # Получаем данные исполнителя (режим read)
    executor_data = await orders_service.get_executor_data(
        telegram_id=executor_telegram_id, user_id=executor_telegram_id, mode='read'
    )

    if not executor_data:
        await callback.answer("❌ Ошибка получения вашего профиля.", show_alert=True)
        return

    worker_id = executor_data['user_id']

    # Проверяем существующий отклик (режим read)
    existing_response = await orders_service.check_existing_response(
        order_id=order_id, worker_id=worker_id, user_id=executor_telegram_id, mode='read'
    )

    if existing_response is not None:
        resp_msg = existing_response['message']
        if resp_msg == 'Отказался':
            text = "Вы отказались от этого заказа."
        elif resp_msg == 'Отстранен':
            text = "Вы не можете откликнуться на этот заказ."
        else:
            text = "Вы уже откликались!"

        await callback.answer(text, show_alert=True)
        return

    # Получаем данные клиента и создаем отклик в транзакции (режим write)
    client_data = await orders_service.get_client_data_and_create_response(
        order_id=order_id, worker_id=worker_id, user_id=executor_telegram_id, mode='write'
    )

    if not client_data:
        await callback.answer(
            "❌ Этот заказ уже неактуален (взят в работу или отменен).",
            show_alert=True
        )
        await callback.message.edit_text(
            callback.message.text + "\n\n**❌ Заказ неактуален**",
            parse_mode='Markdown'
        )
        return

    # Отправляем сообщение исполнителю
    date_created = client_data['created_at'].strftime('%d.%m.%Y')

    await callback.message.answer(
        f"✅ Вы откликнулись!\n\nЗаказчик уведомлен о вашем отклике. Он свяжется с вами, если выберет вас.",
        parse_mode='Markdown'
    )

    # Уведомляем клиента о НОВОМ ОТКЛИКЕ
    exec_contact = executor_data['executor_contact']
    executor_contact_display = exec_contact or f"@{callback.from_user.username}"
    notification_text = (
        f"🔔 У вас новый отклик по заказу от {date_created}!\n\n"
        f"Исполнитель: {executor_data['executor_name']}\n"
        f"Контакт: `{executor_contact_display}`\n\n"
        f"Чтобы посмотреть все отклики, зайдите в 'Мои заказы'."
    )

    try:
        await callback.bot.send_message(
            chat_id=client_data['client_tg_id'],
            text=notification_text,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(
            f"Не удалось отправить уведомление клиенту {client_data['client_tg_id']}: {e}",
            exc_info=True
        )
        await send_error_to_admin(
            callback.bot, e,
            f"Contact Client: Order {order_id} Worker {executor_telegram_id}"
        )

    await callback.answer(
        "Вы успешно откликнулись! Заказчик уведомлен.",
        show_alert=True
    )
    await callback.message.edit_text(
        callback.message.text + "\n\n✅ Вы откликнулись на этот заказ!"
    )

