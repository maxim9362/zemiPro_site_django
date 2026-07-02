import logging

from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

from admin_bot.error_reporter import send_error_to_admin
from db import Database

router = Router()
logger = logging.getLogger(__name__)


class ClientFSM(StatesGroup):
    full_name = State()
    city = State()
    contact = State()


contact_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='Отправить номер телефона', request_contact=True)]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)


class ClientRegistrationService:
    """Класс для работы с регистрацией Заказчика в БД (ООП)."""

    def __init__(self, db: Database):
        self.db = db

    async def register_client(self, telegram_id: int, full_name: str,
                              city: str, phone: str, user_id: int, mode: str = 'write'):
        """Регистрация нового заказчика или обновление его данных."""
        if mode != 'write':
            return False

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            # Обернул в транзакцию для безопасности, так как тут 3 связанных запроса
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO users(telegram_id, role) VALUES($1, 'client') ON CONFLICT DO NOTHING",
                    telegram_id
                )

                internal_user_id = await conn.fetchval(
                    "SELECT id FROM users WHERE telegram_id=$1",
                    telegram_id
                )

                await conn.execute(
                    """
                    INSERT INTO clients(user_id, full_name, city, contact)
                    VALUES ($1, $2, $3, $4) ON CONFLICT(user_id) DO
                    UPDATE SET full_name = $2, city = $3, contact = $4
                    """,
                    internal_user_id, full_name, city, phone
                )
        return True


@router.message(ClientFSM.full_name)
async def get_name(message: types.Message, state: FSMContext, user_id: int, mode: str = 'write'):
    full_name = message.text.strip().title()
    await state.update_data(full_name=full_name)
    await message.answer("Укажите ваш город")
    await state.set_state(ClientFSM.city)


@router.message(ClientFSM.city)
async def get_city(message: types.Message, state: FSMContext, user_id: int, mode: str = 'write'):
    city = message.text.strip().title()
    await state.update_data(city=city)
    await message.answer(
        "Как с вами связаться? Вы можете нажать кнопку ниже или ввести Telegram username/телефон вручную.",
        reply_markup=contact_kb
    )

    await state.set_state(ClientFSM.contact)


@router.message(ClientFSM.contact, F.text | F.contact)
async def get_contact(message: types.Message, state: FSMContext, db: Database, user_id: int, mode: str = 'write'):
    phone = None
    telegram_id = message.from_user.id

    if message.contact:
        phone = message.contact.phone_number
    elif message.text:
        contact_input = message.text.strip()
        if contact_input.startswith(("+", "@")) or contact_input.isdigit():
            phone = contact_input
        else:
            await message.answer(
                "❌ Неверный формат контакта. Введите корректный номер (начиная с +), "
                "или Telegram username (начиная с @), или нажмите кнопку."
            )
            return

    if not phone:
        await message.answer("❌ Пожалуйста, отправьте контакт, используя кнопку, или введите его вручную.")
        return

    data = await state.get_data()

    try:
        reg_service = ClientRegistrationService(db)
        # Используем наш сервис для записи в БД
        await reg_service.register_client(
            telegram_id=telegram_id,
            full_name=data['full_name'],
            city=data['city'],
            phone=phone,
            user_id=telegram_id,
            mode='write'
        )

        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text='Создать заказ'), KeyboardButton(text='Мои заказы')],
                [KeyboardButton(text='Мой профиль'), KeyboardButton(text='Главное меню')]
            ],
            resize_keyboard=True
        )

        await message.answer(
            f"✅ Регистрация завершена! \n\n"
            f"Имя: {data['full_name']}\n"
            f"Город: {data['city']}\n"
            f"Контакт: {phone}",
            reply_markup=ReplyKeyboardRemove()
        )

        await message.answer(
            f"{data['full_name']}, теперь ты можешь пользоваться ботом 🎯",
            reply_markup=keyboard
        )
        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка при регистрации клиента {telegram_id}: {e}", exc_info=True)

        await send_error_to_admin(message.bot, e, f"Client Registration: {telegram_id}")
        await message.answer("❌ Произошла ошибка при регистрации. Администратор уведомлен")
        await state.clear()
