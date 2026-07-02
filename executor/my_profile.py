import logging
import math

from aiogram import Bot, F, Router, types
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup
)

from admin_bot.error_reporter import send_error_to_admin
from db import Database

router = Router()
logger = logging.getLogger(__name__)


class ExecutorProfileService:
    """Класс для работы с профилем Исполнителя в БД (ООП)."""

    def __init__(self, db: Database):
        self.db = db

    async def get_profile_data(self, telegram_id: int, user_id: int, mode: str = 'read'):
        """Получение данных профиля и рейтинга."""
        if mode != 'read':
            return None, None

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            internal_user_id = await conn.fetchval(
                "SELECT id FROM users WHERE telegram_id=$1",
                telegram_id
            )
            if not internal_user_id:
                return None, None

            profile_data = await conn.fetchrow(
                """
                SELECT name, city, skills, description, contact
                FROM workers
                WHERE user_id = $1
                """,
                internal_user_id
            )

            rating_info = await conn.fetchrow(
                """
                SELECT AVG(rating) AS avg_rating, COUNT(id) AS review_count
                FROM ratings
                WHERE worker_id = $1
                """,
                internal_user_id
            )

            return profile_data, rating_info

    async def get_reviews(self, telegram_id: int, offset: int, user_id: int, mode: str = 'read'):
        """Получение списка отзывов с пагинацией."""
        if mode != 'read':
            return None, 0

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            internal_user_id = await conn.fetchval(
                "SELECT id FROM users WHERE telegram_id=$1",
                telegram_id
            )

            if not internal_user_id:
                return None, 0

            reviews = await conn.fetch(
                """
                SELECT r.rating, r.review_text, c.full_name
                FROM ratings r
                JOIN clients c ON r.client_id = c.user_id
                WHERE r.worker_id = $1 AND r.review_text IS NOT NULL
                ORDER BY r.created_at DESC
                LIMIT 5 OFFSET $2
                """,
                internal_user_id, offset
            )

            total_reviews_count = await conn.fetchval(
                "SELECT COUNT(id) FROM ratings WHERE worker_id = $1 AND review_text IS NOT NULL",
                internal_user_id
            )

            return reviews, total_reviews_count

    async def delete_profile(self, telegram_id: int, user_id: int, mode: str = 'write'):
        """Каскадное удаление профиля исполнителя."""
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
                # 1. Удаляем связанные данные исполнителя
                await conn.execute("DELETE FROM responses WHERE worker_id = $1", internal_user_id)
                await conn.execute("DELETE FROM ratings WHERE worker_id = $1", internal_user_id)
                await conn.execute(
                    "UPDATE orders SET worker_id = NULL WHERE worker_id = $1",
                    internal_user_id
                )

                # 2. Удаляем самого исполнителя
                await conn.execute("DELETE FROM workers WHERE user_id = $1", internal_user_id)

                # 3. ПРОВЕРКА: Является ли пользователь также Клиентом?
                is_client = await conn.fetchval(
                    "SELECT 1 FROM clients WHERE user_id = $1",
                    internal_user_id
                )

                if not is_client:
                    await conn.execute("DELETE FROM users WHERE id = $1", internal_user_id)

            return True


# --- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ: Отправка профиля ---
async def send_executor_profile(
    bot: Bot,
    chat_id: int,
    user_id: int,
    db: Database,
    mode: str = 'read'
):
    profile_service = ExecutorProfileService(db)
    profile_data, rating_info = await profile_service.get_profile_data(
        telegram_id=user_id, user_id=user_id, mode='read'
    )

    if profile_data is None and rating_info is None:
        await bot.send_message(
            chat_id,
            "❌ Вы не зарегистрированы. Начните с /start."
        )
        return

    if not profile_data:
        await bot.send_message(
            chat_id,
            "⚠️ Ваш профиль Исполнителя не найден. "
            "Возможно, вы зарегистрированы только как Заказчик."
        )
        return

    avg_rating = rating_info['avg_rating'] if rating_info and rating_info['avg_rating'] else 0
    review_count = rating_info['review_count'] if rating_info else 0
    rating_display = "⭐" * math.ceil(avg_rating)
    rating_text = (
        f"{rating_display} ({avg_rating:.2f}, {review_count} отзывов)"
        if avg_rating > 0 else "Нет оценок"
    )

    if profile_data['skills']:
        skills_list = sorted(profile_data['skills'])
        skills_text = "\n" + "\n".join([f"🔹 {s}" for s in skills_list])
    else:
        skills_text = "Не указаны"

    profile_text = (
        f"👤 Мой Профиль Исполнителя\n\n"
        f"Имя: {profile_data['name']}\n"
        f"Город: {profile_data['city']}\n"
        f"Контакт: `{profile_data['contact']}`\n"
        f"Рейтинг: {rating_text}\n\n"
        f"Категории услуг: {skills_text}\n\n"
        f"Описание услуг:\n{profile_data['description']}\n\n"
        f"🔔 Важно: Чтобы отключить уведомления о новых заказах, вы можете "
        f"заглушить этот бот в настройках чата Telegram."
    )

    profile_keyboard_buttons = [
        [InlineKeyboardButton(
            # Кнопка ведет на хендлер profile_edit, который мы уже написали в edit_profile.py
            text='✏️ Изменить данные',
            callback_data='profile_edit'
        )],
        [InlineKeyboardButton(
            text='🗑 Удалить профиль',
            callback_data='delete_executor_profile_confirm'
        )]
    ]

    if review_count > 0:
        profile_keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"📖 Читать отзывы ({review_count})",
                callback_data=f"read_reviews_my_0"
            )
        ])

    await bot.send_message(
        chat_id=chat_id,
        text=profile_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=profile_keyboard_buttons),
        parse_mode='Markdown'
    )


# --- ХЕНДЛЕР: Мой профиль (из меню) ---
@router.message(F.text == "🛠 Мой профиль")
async def show_my_profile(message: types.Message, db: Database, user_id: int, mode: str = 'write'):
    await send_executor_profile(
        bot=message.bot,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        db=db,
        mode='read'
    )


@router.callback_query(F.data.startswith("read_reviews_my_"))
async def read_my_reviews(callback: types.CallbackQuery, db: Database, user_id: int, mode: str = 'write'):
    offset = int(callback.data.split("_")[3])
    current_user_id = callback.from_user.id
    profile_service = ExecutorProfileService(db)

    reviews, total_reviews_count = await profile_service.get_reviews(
        telegram_id=current_user_id, offset=offset, user_id=current_user_id, mode='read'
    )

    if reviews is None:
        await callback.answer("❌ Ошибка: не найден ваш ID.", show_alert=True)
        return

    if not reviews:
        await callback.answer("Больше отзывов нет.", show_alert=True)
        return

    await callback.message.answer(f" Отзывы (с {offset + 1} по {offset + len(reviews)})")

    reviews_text_list = []
    for review in reviews:
        reviews_text_list.append(
            f"👤 {review['full_name']} (Оценка: {'⭐' * review['rating']}):\n"
            f"{review['review_text']}"
        )

    await callback.message.answer("\n\n".join(reviews_text_list), parse_mode='Markdown')

    if offset + 5 < total_reviews_count:
        next_offset = offset + 5
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(
                    text=f"Показать еще 5 (из {total_reviews_count})",
                    callback_data=f"read_reviews_my_{next_offset}"
                )
            ]]
        )
        await callback.message.answer("Показать следующие?", reply_markup=keyboard)

    await callback.answer()


# 4. УДАЛЕНИЕ ПРОФИЛЯ ИСПОЛНИТЕЛЯ
@router.callback_query(F.data == "delete_executor_profile_confirm")
async def confirm_delete_profile(callback: types.CallbackQuery, user_id: int, mode: str = 'write'):
    confirm_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Да, удалить навсегда",
                    callback_data="delete_executor_profile_final"
                ),
                InlineKeyboardButton(
                    text="🔙 Отмена",
                    callback_data="cancel_delete_executor"
                )
            ]
        ]
    )
    await callback.message.edit_text(
        "⚠️ Вы уверены, что хотите удалить профиль Исполнителя?\n\n"
        "1. Все ваши данные (рейтинг, история, отклики) будут стерты.\n"
        "2. Вы перестанете отображаться в поиске для заказчиков.\n\n"
        "Это действие нельзя отменить!",
        reply_markup=confirm_kb,
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data == "cancel_delete_executor")
async def cancel_delete(callback: types.CallbackQuery, user_id: int, mode: str = 'write'):
    await callback.message.delete()
    await callback.answer("Удаление отменено.")


@router.callback_query(F.data == "delete_executor_profile_final")
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
        profile_service = ExecutorProfileService(db)
        success = await profile_service.delete_profile(
            telegram_id=telegram_id, user_id=telegram_id, mode='write'
        )

        if success:
            await callback.message.answer(
                "🗑 Ваш профиль Исполнителя удален.\n"
                "Если у вас был профиль Заказчика, он остался активным.",
                reply_markup=start_menu
            )
            await callback.message.delete()
        else:
            await callback.answer("❌ Профиль не найден или уже удален.", show_alert=True)

    except Exception as e:
        logger.error(
            f"Ошибка удаления профиля исполнителя {telegram_id}: {e}",
            exc_info=True
        )
        await send_error_to_admin(
            callback.bot, e, f"Delete Executor Profile: {telegram_id}"
        )

        await callback.answer("❌ Произошла ошибка при удалении.", show_alert=True)
