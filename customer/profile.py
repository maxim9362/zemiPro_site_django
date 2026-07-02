import logging

from aiogram import F, Router, types
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from admin_bot.error_reporter import send_error_to_admin
from db import Database

router = Router()
logger = logging.getLogger(__name__)


class ClientProfileFSM(StatesGroup):
    editing_name = State()
    editing_city = State()
    editing_contact = State()


contact_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='Отправить номер телефона', request_contact=True)]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)


class ClientProfileService:
    """Класс для работы с профилем Заказчика в БД (ООП)."""

    def __init__(self, db: Database):
        self.db = db

    async def get_profile(self, telegram_id: int, user_id: int, mode: str = 'read'):
        """Получение данных профиля клиента."""
        if mode != 'read':
            return None

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            return await conn.fetchrow(
                """
                SELECT c.full_name, c.city, c.contact
                FROM clients c
                         JOIN users u ON c.user_id = u.id
                WHERE u.telegram_id = $1
                """,
                telegram_id
            )

    async def update_profile(self, telegram_id: int, full_name: str,
                             city: str, contact_info: str, user_id: int, mode: str = 'write'):
        """Обновление данных профиля клиента."""
        if mode != 'write':
            return False

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE clients
                SET full_name = $1,
                    city      = $2,
                    contact   = $3
                WHERE user_id = (SELECT id FROM users WHERE telegram_id = $4)
                """,
                full_name, city, contact_info, telegram_id
            )
            return True

    async def delete_profile(self, telegram_id: int, user_id: int, mode: str = 'write'):
        """Каскадное удаление профиля заказчика и связанных данных."""
        if mode != 'write':
            return False

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            internal_user_id = await conn.fetchval(
                "SELECT id FROM users WHERE telegram_id=$1",
                telegram_id
            )

            if not internal_user_id:
                return False

            async with conn.transaction():
                # 1. Удаляем отклики на заказы этого клиента
                await conn.execute(
                    """
                    DELETE
                    FROM responses
                    WHERE order_id IN (SELECT id FROM orders WHERE client_id = $1)
                    """,
                    internal_user_id
                )

                # 2. Удаляем заказы клиента
                await conn.execute("DELETE FROM orders WHERE client_id = $1", internal_user_id)

                # 3. Обезличиваем отзывы
                await conn.execute(
                    "UPDATE ratings SET client_id = NULL WHERE client_id = $1",
                    internal_user_id
                )

                # 4. Удаляем профиль клиента из таблицы clients
                await conn.execute("DELETE FROM clients WHERE user_id = $1", internal_user_id)

                # 5. ПРОВЕРКА: Является ли пользователь Исполнителем (Worker)?
                is_worker = await conn.fetchval(
                    "SELECT 1 FROM workers WHERE user_id = $1",
                    internal_user_id
                )

                if not is_worker:
                    # Если он НЕ исполнитель, удаляем аккаунт полностью
                    await conn.execute("DELETE FROM users WHERE id = $1", internal_user_id)

            return True


# 1. ПРОСМОТР ПРОФИЛЯ
@router.message(F.text == "Мой профиль", StateFilter('*'))
async def show_client_profile(message: types.Message, db: Database, state: FSMContext, user_id: int, mode: str = 'write'):
    await state.clear()
    telegram_id = message.from_user.id

    try:
        profile_service = ClientProfileService(db)
        # Используем сервис (режим read)
        client_data = await profile_service.get_profile(
            telegram_id=telegram_id, user_id=telegram_id, mode='read'
        )

        if not client_data:
            await message.answer("❌ Профиль Заказчика не найден.")
            return

        profile_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="✏️ Изменить данные",
                    callback_data="edit_client_profile"
                )],
                [InlineKeyboardButton(
                    text="🗑 Удалить профиль",
                    callback_data="delete_client_profile_confirm"
                )]
            ]
        )

        text = (
            f"👤 Ваш профиль Заказчика\n\n"
            f"📝 Имя: {client_data['full_name']}\n"
            f"🏙 Город: {client_data['city']}\n"
            f"📞 Контакт: `{client_data['contact']}`"
        )

        await message.answer(text, reply_markup=profile_kb, parse_mode="Markdown")

    except Exception as e:
        logger.error(
            f"Ошибка при просмотре профиля заказчика {telegram_id}: {e}",
            exc_info=True
        )
        await send_error_to_admin(message.bot, e, f"Show Client Profile: {telegram_id}")
        await message.answer("❌ Произошла ошибка при загрузке профиля.")


# 2. РЕДАКТИРОВАНИЕ ПРОФИЛЯ ЗАКАЗЧИКА
@router.callback_query(F.data == "edit_client_profile")
async def start_edit_profile(callback: types.CallbackQuery, state: FSMContext, user_id: int, mode: str = 'write'):
    await callback.message.answer("✏️ Введите новое имя:")
    await state.set_state(ClientProfileFSM.editing_name)
    await callback.answer()


@router.message(ClientProfileFSM.editing_name)
async def process_new_name(message: types.Message, state: FSMContext, user_id: int, mode: str = 'write'):
    new_name = message.text.strip().title()
    await state.update_data(full_name=new_name)
    await message.answer("🏙 Введите новый город:")
    await state.set_state(ClientProfileFSM.editing_city)


@router.message(ClientProfileFSM.editing_city)
async def process_new_city(message: types.Message, state: FSMContext, user_id: int, mode: str = 'write'):
    new_city = message.text.strip().title()
    await state.update_data(city=new_city)
    await message.answer(
        "📞 Отправьте новый контакт (кнопкой или текстом):",
        reply_markup=contact_kb
    )
    await state.set_state(ClientProfileFSM.editing_contact)


@router.message(ClientProfileFSM.editing_contact, F.text | F.contact)
async def process_new_contact(
        message: types.Message,
        state: FSMContext,
        db: Database,
        user_id: int,
        mode: str = 'write'
):
    contact_info = None
    if message.contact:
        contact_info = message.contact.phone_number
    elif message.text:
        contact_input = message.text.strip()
        if contact_input.startswith(("+", "@")) or contact_input.isdigit():
            contact_info = contact_input
        else:
            await message.answer("❌ Неверный формат. Введите номер (+) или username (@).")
            return

    if not contact_info:
        await message.answer("❌ Пожалуйста, отправьте контакт.")
        return

    data = await state.get_data()
    telegram_id = message.from_user.id

    customers_menu = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='Создать заказ'), KeyboardButton(text='Мои заказы')],
            [KeyboardButton(text='Мой профиль'), KeyboardButton(text='Главное меню')]
        ],
        resize_keyboard=True
    )

    try:
        profile_service = ClientProfileService(db)
        # Используем сервис (режим write)
        await profile_service.update_profile(
            telegram_id=telegram_id,
            full_name=data['full_name'],
            city=data['city'],
            contact_info=contact_info,
            user_id=telegram_id,
            mode='write'
        )

        await message.answer(
            f"✅ Профиль обновлен!\n\n"
            f"Имя: {data['full_name']}\n"
            f"Город: {data['city']}\n"
            f"Контакт: {contact_info}",
            reply_markup=customers_menu
        )

    except Exception as e:
        logger.error(
            f"Ошибка обновления профиля клиента {telegram_id}: {e}",
            exc_info=True
        )
        await send_error_to_admin(
            message.bot, e, f"Edit Client Profile: {telegram_id}"
        )
        await message.answer("❌ Не удалось обновить профиль.", reply_markup=customers_menu)

    finally:
        await state.clear()


# 3. УДАЛЕНИЕ ПРОФИЛЯ ЗАКАЗЧИКА
@router.callback_query(F.data == "delete_client_profile_confirm")
async def confirm_delete_profile(callback: types.CallbackQuery, user_id: int, mode: str = 'write'):
    confirm_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Да, удалить навсегда",
                    callback_data="delete_client_profile_final"
                ),
                InlineKeyboardButton(
                    text="🔙 Отмена",
                    callback_data="cancel_delete_profile"
                )
            ]
        ]
    )
    await callback.message.edit_text(
        "⚠️ Вы уверены, что хотите удалить профиль?\n\n"
        "1. Ваши активные заказы будут удалены.\n"
        "2. История заказов очистится.\n"
        "3. Отзывы, которые вы оставили исполнителям, сохранятся (анонимно).\n\n"
        "Это действие нельзя отменить!",
        reply_markup=confirm_kb,
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data == "cancel_delete_profile")
async def cancel_delete(callback: types.CallbackQuery, user_id: int, mode: str = 'write'):
    await callback.message.delete()
    await callback.answer("Удаление отменено.")


@router.callback_query(F.data == "delete_client_profile_final")
async def final_delete_profile(callback: types.CallbackQuery, db: Database, user_id: int, mode: str = 'write'):
    telegram_id = callback.from_user.id

    start_menu = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='Заказчик'), KeyboardButton(text='Исполнитель')],
            [KeyboardButton(text='Помощь')],
        ],
        resize_keyboard=True
    )

    try:
        profile_service = ClientProfileService(db)
        # Используем сервис (режим write)
        success = await profile_service.delete_profile(
            telegram_id=telegram_id, user_id=telegram_id, mode='write'
        )

        if success:
            await callback.message.answer(
                "🗑 Ваш профиль Заказчика успешно удален.\n"
                "Если у вас был профиль Исполнителя, он остался активным.",
                reply_markup=start_menu
            )
            await callback.message.delete()
        else:
            await callback.answer("❌ Профиль не найден или уже удален.", show_alert=True)

    except Exception as e:
        logger.error(
            f"Ошибка удаления профиля {telegram_id}: {e}",
            exc_info=True
        )
        await send_error_to_admin(
            callback.bot, e, f"Delete Client Profile: {telegram_id}"
        )
        await callback.answer("❌ Произошла ошибка при удалении.", show_alert=True)
