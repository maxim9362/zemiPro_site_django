import logging

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from admin_bot.error_reporter import send_error_to_admin
from categories.keyboards import CategoryKeyboards
from db import Database

router = Router()
logger = logging.getLogger(__name__)


class EditExecutorProfile(StatesGroup):
    edit_name = State()
    edit_city = State()
    edit_contact = State()
    edit_skills = State()
    edit_description = State()


contact_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='📱 Отправить номер телефона', request_contact=True)]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)


class EditProfileService:
    """Класс для работы с обновлением профиля Исполнителя в БД (ООП)."""

    def __init__(self, db: Database):
        self.db = db

    async def check_profile_exists(self, telegram_id: int, user_id: int, mode: str = 'read') -> bool:
        """Проверка существования профиля исполнителя."""
        if mode != 'read':
            return False

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT 1 FROM workers WHERE user_id = (SELECT id FROM users WHERE telegram_id = $1)",
                telegram_id
            )
            return bool(result)

    async def update_worker_profile(
            self,
            telegram_id: int,
            full_name: str,
            city: str,
            contact: str,
            skills: list,
            description: str,
            user_id: int,
            mode: str = 'write'
    ) -> bool:
        """Обновление всех данных профиля Исполнителя."""
        if mode != 'write':
            return False

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE workers
                SET name        = $1,
                    city        = $2,
                    contact     = $3,
                    skills      = $4,
                    description = $5
                WHERE user_id = (SELECT id FROM users WHERE telegram_id = $6)
                """,
                full_name, city, contact, skills, description, telegram_id
            )
        return True


# --- ВОТ ЭТОТ БЛОК МЫ ДОБАВИЛИ (ВХОД В РЕДАКТИРОВАНИЕ) ---
@router.callback_query(F.data == 'profile_edit')
async def handle_start_edit_profile(
        callback: types.CallbackQuery,
        state: FSMContext,
        db: Database,
        user_id: int,
        mode: str = 'write'
):
    current_user_id = callback.from_user.id
    profile_service = EditProfileService(db)

    profile_exists = await profile_service.check_profile_exists(
        telegram_id=current_user_id, user_id=current_user_id, mode='read'
    )

    if not profile_exists:
        await callback.answer("❌ Профиль не найден.", show_alert=True)
        return

    await callback.message.answer(
        "✏️ Начинаем обновление профиля.\n\nВведите ваше **имя**:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )

    await state.set_state(EditExecutorProfile.edit_name)
    await callback.answer()


# --- ДАЛЕЕ ТВОИ ШАГИ БЕЗ ИЗМЕНЕНИЙ ---

@router.message(EditExecutorProfile.edit_name)
async def process_edit_name(message: types.Message, state: FSMContext, user_id: int, mode: str = 'write'):
    await state.update_data(full_name=message.text.strip().title())
    await state.update_data(telegram_id=message.from_user.id)
    await message.answer("🏙 Введите новый город:")
    await state.set_state(EditExecutorProfile.edit_city)


@router.message(EditExecutorProfile.edit_city)
async def process_edit_city(message: types.Message, state: FSMContext, user_id: int, mode: str = 'write'):
    await state.update_data(city=message.text.strip().title())
    await message.answer(
        "📞 Введите новый контакт (нажмите кнопку или введите вручную):",
        reply_markup=contact_kb
    )
    await state.set_state(EditExecutorProfile.edit_contact)


@router.message(EditExecutorProfile.edit_contact, F.text | F.contact)
async def process_edit_contact(message: types.Message, state: FSMContext, db: Database, user_id: int, mode: str = 'write'):
    contact_info = None
    current_user_id = message.from_user.id

    if message.contact:
        contact_info = message.contact.phone_number
    elif message.text:
        contact_input = message.text.strip()
        if contact_input.startswith(("+", "@")) or contact_input.isdigit():
            contact_info = contact_input
        else:
            await message.answer("❌ Неверный формат. Введите номер или username (@).")
            return

    if not contact_info:
        await message.answer("❌ Пожалуйста, отправьте контакт.")
        return

    await state.update_data(contact=contact_info)

    # ДИНАМИЧЕСКИЙ ТЕКСТ
    category_kb_service = CategoryKeyboards(db)
    help_text = await category_kb_service.get_help_text(user_id=current_user_id, mode='read')

    await message.answer(
        help_text,
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )

    # ДИНАМИЧЕСКАЯ КЛАВИАТУРА
    skills_kb = await category_kb_service.get_categories_kb(prefix="skill_", user_id=current_user_id, mode='read')

    await message.answer(
        "👇 Выберите навыки (можно несколько):\n"
        "Нажимайте на категории, которые вам подходят. "
        "Когда закончите — нажмите «✅ Готово».",
        reply_markup=skills_kb
    )
    await state.update_data(selected_skills=[])
    await state.set_state(EditExecutorProfile.edit_skills)


@router.callback_query(EditExecutorProfile.edit_skills, F.data.startswith("skill_"))
async def process_edit_skills(callback: types.CallbackQuery, state: FSMContext, db: Database, user_id: int, mode: str = 'write'):
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


@router.callback_query(EditExecutorProfile.edit_skills, F.data == "skills_done")
async def process_skills_done(callback: types.CallbackQuery, state: FSMContext, user_id: int, mode: str = 'write'):
    data = await state.get_data()
    skills = list(data.get("selected_skills", []))

    if not skills:
        await callback.answer("⚠️ Выберите хотя бы один навык!", show_alert=True)
        return

    await state.update_data(skills=skills)

    skills.sort()
    skills_text = "\n".join([f"🔹 {skill}" for skill in skills])

    await callback.message.edit_text(
        f"✅ Навыки обновлены:\n\n{skills_text}",
        reply_markup=None
    )
    await callback.message.answer("📝 Введите новое описание услуг (опыт, инструменты):")
    await state.set_state(EditExecutorProfile.edit_description)


@router.message(EditExecutorProfile.edit_description)
async def process_edit_description(
        message: types.Message,
        state: FSMContext,
        db: Database,
        user_id: int,
        mode: str = 'write'
):
    data = await state.get_data()
    description = message.text.strip()
    telegram_id = data.get('telegram_id')
    current_user_id = message.from_user.id

    if not telegram_id:
        await message.answer(
            "❌ Произошла ошибка (не найден telegram_id). Попробуйте начать заново: /start."
        )
        await state.clear()
        return

    workers_menu = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='Мои отклики'), KeyboardButton(text='🛠 Мой профиль')],
            [KeyboardButton(text='Смотреть заказы'), KeyboardButton(text='Главное меню')]
        ],
        resize_keyboard=True
    )

    try:
        profile_service = EditProfileService(db)
        await profile_service.update_worker_profile(
            telegram_id=telegram_id,
            full_name=data['full_name'],
            city=data['city'],
            contact=data['contact'],
            skills=data['skills'],
            description=description,
            user_id=current_user_id,
            mode='write'
        )

        skills_raw = list(data['skills'])
        skills_raw.sort()
        skills_formatted = "\n".join([f"🔹 {s}" for s in skills_raw])

        await message.answer(
            "✅ Профиль успешно обновлен!\n\n"
            f"👤 Имя: {data['full_name']}\n"
            f"🏙 Город: {data['city']}\n"
            f"📞 Контакт: {data['contact']}\n\n"
            f"📂 Навыки:\n{skills_formatted}\n\n"
            f"📝 Описание:\n{description}",
            reply_markup=workers_menu
        )

    except Exception as e:
        logger.error(f"Ошибка в FSM 'EditExecutorProfile': {e}", exc_info=True)
        await send_error_to_admin(
            message.bot, e, f"Edit Executor Profile: {current_user_id}"
        )
        await message.answer(
            "❌ Произошла неизвестная ошибка. Попробуйте начать заново: /start.",
            reply_markup=workers_menu
        )
    finally:
        await state.clear()
