import logging

from aiogram import F, Router, types
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from admin_bot.error_reporter import send_error_to_admin
from customer.registration import ClientFSM

# ИСПРАВЛЕННЫЙ ИМПОРТ: используем новый класс-сервис для проверки исполнителя
from executor.registration_exe import ExecutorRegistration, ExecutorRegistrationService
from menu.Job_support import help as help_text, support as support_text
from db import Database

router = Router()
logger = logging.getLogger(__name__)

# --- Главное меню (Reply) ---
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='Заказчик'), KeyboardButton(text='Исполнитель')],
        [KeyboardButton(text='Помощь')],
    ],
    resize_keyboard=True
)


class StartService:
    """Класс для работы с базой данных при старте бота (ООП)."""

    def __init__(self, db: Database):
        self.db = db

    async def check_user_exists(self, telegram_id: int, user_id: int, mode: str = 'read') -> bool:
        """Проверка, существует ли пользователь в базе."""
        if mode != 'read':
            return False

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            user_exists = await conn.fetchval(
                "SELECT id FROM users WHERE telegram_id = $1",
                telegram_id
            )
            return bool(user_exists)

    async def check_client_exists(self, telegram_id: int, user_id: int, mode: str = 'read') -> bool:
        """Проверка, есть ли у пользователя профиль Заказчика."""
        if mode != 'read':
            return False

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            client_profile = await conn.fetchval(
                """
                SELECT c.user_id
                FROM clients c
                         JOIN users u ON c.user_id = u.id
                WHERE u.telegram_id = $1
                """,
                telegram_id
            )
            return bool(client_profile)


@router.message(CommandStart(), StateFilter('*'))
async def start(
        message: Message,
        state: FSMContext,
        db: Database,
        user_id: int,
        mode: str = 'write'
):
    await state.clear()
    current_user_id = message.from_user.id

    try:
        start_service = StartService(db)
        # Используем сервис (режим read)
        user_exists = await start_service.check_user_exists(
            telegram_id=current_user_id, user_id=current_user_id, mode='read'
        )

        if user_exists:
            # Если пользователь уже зарегистрирован, выдаем главное меню без правил
            await message.answer(
                "Выберите нужное действие 👇",
                reply_markup=main_menu
            )
            return

    except Exception as e:
        logger.error(f"Ошибка при проверке пользователя в /start: {e}")

    rules_text = (
        "👋 Привет! Я — TachlesPro.\n\n"
        "📜 Перед началом использования сервиса, пожалуйста, ознакомьтесь с правилами:\n\n"
        "🔹 [Правила сервиса](https://docs.google.com/document/d/"
        "1y2dlGd_rYCu-EWpLDpB2r9ga1wjBhAlrWv1YrOFVYB4/edit?usp=sharing)\n"

        "🔹 [Политика конфиденциальности](https://docs.google.com/document/d/"
        "1W0RZmH12CxILWOmERk3jaArgcdMcgSwa09wX0HJmkJM/edit?usp=sharing)\n\n"
        "Нажимая кнопку ниже, вы принимаете условия использования."
    )

    # Инлайн-кнопка подтверждения
    confirm_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтверждаю", callback_data="rules_confirmed")]
        ]
    )

    await message.answer(rules_text, reply_markup=confirm_kb, parse_mode="Markdown", disable_web_page_preview=True)


@router.callback_query(F.data == "rules_confirmed")
async def confirm_rules(callback: CallbackQuery, user_id: int, mode: str = 'write'):
    # Убираем кнопку "Подтверждаю", чтобы не нажимали повторно
    await callback.message.edit_reply_markup(reply_markup=None)

    # Приветствие и выдача клавиатуры
    await callback.message.answer(
        "✅ Вы приняли условия. Добро пожаловать!",
        reply_markup=main_menu
    )

    # Сообщение с выбором роли
    await callback.message.answer(
        "Выберите, кто вы:\n"
        "👉 Заказчик (ищу специалиста)\n"
        "👉 Исполнитель (предлагаю услуги)"
    )
    await callback.answer()


@router.message(F.text == "Заказчик", StateFilter('*'))
async def handle_client_start(
        message: Message,
        state: FSMContext,
        db: Database,
        user_id: int,
        mode: str = 'write'
):
    await state.clear()
    current_user_id = message.from_user.id

    try:
        start_service = StartService(db)
        # Используем сервис (режим read)
        is_client = await start_service.check_client_exists(
            telegram_id=current_user_id, user_id=current_user_id, mode='read'
        )

        if is_client:
            # Меню заказчика с кнопкой "Мой профиль"
            customers_menu = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text='Создать заказ'), KeyboardButton(text='Мои заказы')],
                    [KeyboardButton(text='Мой профиль'), KeyboardButton(text='Главное меню')]
                ],
                resize_keyboard=True
            )
            await message.answer("Меню заказчика", reply_markup=customers_menu)
        else:
            await message.answer("Регистрация Заказчика 👤\nВведите ваше имя:")
            await state.set_state(ClientFSM.full_name)

    except Exception as e:
        logger.error(f"Ошибка при проверке профиля заказчика: {e}", exc_info=True)
        await send_error_to_admin(
            message.bot, e, f"Start Menu (Client check): {current_user_id}"
        )
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")


@router.message(F.text == "Исполнитель", StateFilter('*'))
async def handle_executor_start(
        message: Message,
        state: FSMContext,
        db: Database,
        user_id: int,
        mode: str = 'write'
):
    await state.clear()
    current_user_id = message.from_user.id

    try:
        exe_service = ExecutorRegistrationService(db)
        # Используем метод из сервиса исполнителя (режим read)
        is_executor = await exe_service.is_worker(
            telegram_id=current_user_id, user_id=current_user_id, mode='read'
        )

        if is_executor:
            workers_menu = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text='Мои отклики'), KeyboardButton(text='🛠 Мой профиль')],
                    [KeyboardButton(text='Смотреть заказы'), KeyboardButton(text='Главное меню')]
                ],
                resize_keyboard=True
            )
            await message.answer("Меню исполнителя", reply_markup=workers_menu)
        else:
            await message.answer("Регистрация Исполнителя 👤\nВведите ваше имя:")
            await state.set_state(ExecutorRegistration.full_name)

    except Exception as e:
        logger.error(f"Ошибка при проверке профиля исполнителя: {e}", exc_info=True)
        await send_error_to_admin(
            message.bot, e, f"Start Menu (Executor check): {current_user_id}"
        )
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")


@router.message(F.text.in_({'Помощь', 'Главное меню'}), StateFilter('*'))
async def handle_main_navigation(message: Message, state: FSMContext, user_id: int, mode: str = 'write'):
    await state.clear()

    if message.text == 'Помощь':
        help_menu = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text='Как работает бот'), KeyboardButton(text='Поддержка')],
                [KeyboardButton(text='Главное меню')],
            ],
            resize_keyboard=True
        )
        await message.answer('Как тебе помочь? Выбери ниже 👇', reply_markup=help_menu)

    elif message.text == 'Главное меню':
        await message.answer('Ты вернулся в главное меню', reply_markup=main_menu)


@router.message(F.text.in_({'Как работает бот', 'Поддержка'}), StateFilter('*'))
async def handle_job_support(message: Message, state: FSMContext, user_id: int, mode: str = 'write'):
    await state.clear()

    if message.text == 'Как работает бот':
        await message.answer(help_text)
    elif message.text == 'Поддержка':
        await message.answer(support_text)
