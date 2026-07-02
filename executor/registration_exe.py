import logging
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup
)

from admin_bot.error_reporter import send_error_to_admin
from categories.keyboards import CategoryKeyboards
from db import Database

router = Router()
logger = logging.getLogger(__name__)


class ExecutorRegistration(StatesGroup):
    full_name = State()
    city = State()
    contact = State()
    skills = State()
    description = State()


contact_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='📱 Отправить номер телефона', request_contact=True)]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)


class ExecutorRegistrationService:
    """Класс для работы с регистрацией Исполнителя в БД (ООП)."""

    def __init__(self, db: Database):
        self.db = db

    async def is_worker(self, telegram_id: int, user_id: int, mode: str = 'read') -> bool:
        """Проверка, является ли пользователь исполнителем."""
        if mode != 'read':
            return False

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT w.user_id
                FROM workers w
                         JOIN users u ON w.user_id = u.id
                WHERE u.telegram_id = $1
                """,
                telegram_id
            )
        return bool(row)

    async def add_worker(
            self,
            telegram_id: int,
            full_name: str,
            city: str,
            contact: str,
            skills: list,
            description: str,
            user_id: int,
            mode: str = 'write'
    ):
        """Регистрация нового исполнителя или обновление его данных."""
        if mode != 'write':
            return False

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            async with conn.transaction():
                user = await conn.fetchrow(
                    "SELECT id FROM users WHERE telegram_id=$1",
                    telegram_id
                )

                if not user:
                    internal_user_id = await conn.fetchval(
                        """
                        INSERT INTO users (telegram_id, role)
                        VALUES ($1, 'worker') RETURNING id
                        """,
                        telegram_id
                    )
                else:
                    internal_user_id = user['id']

                await conn.execute(
                    """
                    INSERT INTO workers (user_id, name, city, skills, description, contact)
                    VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (user_id) DO
                    UPDATE
                        SET name=EXCLUDED.name,
                        city=EXCLUDED.city,
                        skills=EXCLUDED.skills,
                        description=EXCLUDED.description,
                        contact=EXCLUDED.contact
                    """,
                    internal_user_id, full_name, city, skills, description, contact
                )
        return True


@router.message(ExecutorRegistration.full_name)
async def get_name(message: types.Message, state: FSMContext, user_id: int, mode: str = 'write'):
    full_name = message.text.strip().title()
    await state.update_data(full_name=full_name)
    await state.update_data(telegram_id=message.from_user.id)
    await message.answer("🏙 Укажите ваш город:")
    await state.set_state(ExecutorRegistration.city)


@router.message(ExecutorRegistration.city)
async def get_city(message: types.Message, state: FSMContext, user_id: int, mode: str = 'write'):
    city = message.text.strip().title()
    await state.update_data(city=city)
    await message.answer(
        "Как с вами связаться? Вы можете нажать кнопку ниже или ввести "
        "Telegram username/телефон вручную.",
        reply_markup=contact_kb
    )
    await state.set_state(ExecutorRegistration.contact)


@router.message(ExecutorRegistration.contact, F.text | F.contact)
async def get_contact(
        message: types.Message,
        state: FSMContext,
        db: Database,
        user_id: int,
        mode: str = 'write'
):
    contact_info = None
    current_user_id = message.from_user.id

    if message.contact:
        contact_info = message.contact.phone_number
    elif message.text:
        contact_input = message.text.strip()
        if contact_input.startswith(("+", "@")) or contact_input.isdigit():
            contact_info = contact_input
        else:
            await message.answer(
                "❌ Неверный формат контакта. Введите корректный номер (начиная с +), "
                "или Telegram username (начиная с @), или нажмите кнопку."
            )
            return

    if not contact_info:
        await message.answer(
            "❌ Пожалуйста, отправьте контакт, используя кнопку, или введите его вручную."
        )
        return

    await state.update_data(contact=contact_info)

    category_kb_service = CategoryKeyboards(db)
    help_text = await category_kb_service.get_help_text(user_id=current_user_id, mode='read')

    await message.answer(
        help_text,
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )

    skills_kb = await category_kb_service.get_categories_kb(prefix="skill_", user_id=current_user_id, mode='read')

    await message.answer(
        "👇 Выберите навыки (можно несколько):\n"
        "Нажимайте на категории, которые вам подходят. "
        "Когда закончите — нажмите «✅ Готово».",
        reply_markup=skills_kb
    )
    await state.update_data(selected_skills=[])
    await state.set_state(ExecutorRegistration.skills)


@router.callback_query(F.data.startswith("skill_"), ExecutorRegistration.skills)
async def select_skill(
        callback: types.CallbackQuery,
        state: FSMContext,
        db: Database,
        user_id: int,
        mode: str = 'write'
):
    skill = callback.data.replace("skill_", "")
    current_user_id = callback.from_user.id
    data = await state.get_data()
    selected = list(data.get("selected_skills", []))

    if skill in selected:
        selected.remove(skill)
    else:
        selected.append(skill)

    await state.update_data(selected_skills=selected)

    if selected:
        selected.sort()
        selected_text = "\n".join([f"✅ {s}" for s in selected])
    else:
        selected_text = "Ничего не выбрано"

    text = (
        "👇 Выберите навыки (можно несколько):\n"
        "Нажимайте на категории, которые вам подходят. "
        "Когда закончите — нажмите «✅ Готово».\n\n"
        f"📋 Ваш выбор:\n{selected_text}"
    )

    category_kb_service = CategoryKeyboards(db)
    skills_kb = await category_kb_service.get_categories_kb(prefix="skill_", user_id=current_user_id, mode='read')

    try:
        await callback.message.edit_text(
            text=text,
            reply_markup=skills_kb,
            parse_mode="Markdown"
        )
    except Exception:
        pass

    await callback.answer()


@router.callback_query(F.data == "skills_done", ExecutorRegistration.skills)
async def skills_done(callback: types.CallbackQuery, state: FSMContext, user_id: int, mode: str = 'write'):
    data = await state.get_data()
    skills = list(data.get("selected_skills", []))

    if not skills:
        await callback.answer("⚠️ Выберите хотя бы один навык!", show_alert=True)
        return

    await state.update_data(skills=skills)

    skills.sort()
    skills_text = "\n".join([f"🔹 {skill}" for skill in skills])

    await callback.message.edit_text(
        f"✅ Ваш выбор сохранен:\n\n{skills_text}",
        reply_markup=None
    )

    await callback.message.answer("📝 Теперь введите описание ваших услуг (опыт, инструменты, особенности):")
    await state.set_state(ExecutorRegistration.description)


@router.message(ExecutorRegistration.description)
async def get_description(
        message: types.Message,
        state: FSMContext,
        db: Database,
        user_id: int,
        mode: str = 'write'
):
    data = await state.get_data()
    description = message.text.strip()
    telegram_id = message.from_user.id
    current_user_id = message.from_user.id

    main_menu = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='Мои отклики'), KeyboardButton(text='Мой профиль')],
            [KeyboardButton(text='Смотреть заказы'), KeyboardButton(text='Главное меню')]
        ],
        resize_keyboard=True
    )

    try:
        skills_to_save = list(data.get('skills', []))
        reg_service = ExecutorRegistrationService(db)

        # Используем сервис (режим write)
        await reg_service.add_worker(
            telegram_id=telegram_id,
            full_name=data['full_name'],
            city=data['city'],
            contact=data['contact'],
            skills=skills_to_save,
            description=description,
            user_id=current_user_id,
            mode='write'
        )
    except Exception as e:
        logger.error(
            f"Ошибка при регистрации исполнителя {telegram_id}: {e}",
            exc_info=True
        )
        await send_error_to_admin(
            message.bot, e, f"Executor Registration: {telegram_id}"
        )
        await state.clear()
        await message.answer(
            "❌ Произошла ошибка при сохранении. Попробуйте начать заново: /start.",
            reply_markup=main_menu
        )
        return

    skills_to_save.sort()
    skills_formatted = "\n".join([f"🔹 {s}" for s in skills_to_save])

    await message.answer(
        f"✅ Регистрация завершена!\n\n"
        f"👤 Имя: {data['full_name']}\n"
        f"🏙 Город: {data['city']}\n"
        f"📞 Контакт: {data['contact']}\n\n"
        f"📂 Навыки:\n{skills_formatted}\n\n"
        f"📝 Описание: {description}",
        reply_markup=main_menu
    )

    await state.clear()
    await message.answer(
        f"{data['full_name']}, профиль готов! 🎯\n\n"
        f"🚀 Мы сейчас на этапе запуска, активно собираем базу лучших мастеров "
        f"перед стартом рекламы для заказчиков.\n\n"
        f"🔔 Важно: Заказы могут появиться не сразу. "
        f"Пожалуйста, не отключайте уведомления — "
        f"мы сообщим вам лично, как только в вашей категории появится работа!"
    )
