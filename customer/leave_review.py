import logging

from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from admin_bot.error_reporter import send_error_to_admin
from db import Database

router = Router()
logger = logging.getLogger(__name__)

rating_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="⭐", callback_data="set_rating_1"),
            InlineKeyboardButton(text="⭐⭐", callback_data="set_rating_2"),
            InlineKeyboardButton(text="⭐⭐⭐", callback_data="set_rating_3"),
        ],
        [
            InlineKeyboardButton(text="⭐⭐⭐⭐", callback_data="set_rating_4"),
            InlineKeyboardButton(text="⭐⭐⭐⭐⭐", callback_data="set_rating_5"),
        ]
    ]
)


class LeaveReviewFSM(StatesGroup):
    rating = State()
    review_text = State()


class ReviewService:
    """Класс для работы с отзывами в БД (ООП)."""

    def __init__(self, db: Database):
        self.db = db

    async def check_review_exists(self, order_id: int, user_id: int, mode: str = 'read') -> bool:
        """Проверка, оставлял ли заказчик уже отзыв на этот заказ."""
        if mode != 'read':
            return False

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            existing_rating = await conn.fetchval(
                "SELECT id FROM ratings WHERE order_id = $1", order_id
            )
            return bool(existing_rating)

    async def save_review_and_get_worker(self, order_id: int, worker_id: int,
                                         telegram_id: int, rating: int, review_text: str,
                                         user_id: int, mode: str = 'write'):
        """Сохранение отзыва и получение данных мастера для отправки уведомления."""
        if mode != 'write':
            return None

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            # Получаем внутренний ID клиента
            client_id = await conn.fetchval(
                "SELECT id FROM users WHERE telegram_id = $1", telegram_id
            )

            if not client_id:
                return None

            # Вставляем отзыв
            await conn.execute(
                """
                INSERT INTO ratings (order_id, worker_id, client_id, rating, review_text)
                VALUES ($1, $2, $3, $4, $5) ON CONFLICT (order_id) DO NOTHING
                """,
                order_id, worker_id, client_id, rating, review_text
            )

            # Получаем telegram_id мастера для уведомления
            worker_info = await conn.fetchrow(
                "SELECT u.telegram_id, w.name FROM users u JOIN workers w ON u.id = w.user_id WHERE u.id = $1",
                worker_id
            )
            return worker_info


@router.callback_query(F.data.startswith("rate_work_"))
async def start_leave_review(callback: types.CallbackQuery, state: FSMContext, db: Database, user_id: int, mode: str = 'write'):
    parts = callback.data.split("_")
    order_id = int(parts[2])
    worker_id = int(parts[3])
    current_user_id = callback.from_user.id

    review_service = ReviewService(db)
    # Используем метод сервиса (режим read)
    exists = await review_service.check_review_exists(order_id=order_id, user_id=current_user_id, mode='read')

    if exists:
        await callback.answer("Вы уже оставляли отзыв на этот заказ.", show_alert=True)
        return

    await state.update_data(order_id=order_id, worker_id=worker_id)
    await callback.message.answer(
        "Пожалуйста, оцените работу исполнителя (от 1 до 5 звезд):",
        reply_markup=rating_keyboard
    )
    await state.set_state(LeaveReviewFSM.rating)
    await callback.answer()


@router.callback_query(LeaveReviewFSM.rating, F.data.startswith("set_rating_"))
async def get_rating(callback: types.CallbackQuery, state: FSMContext, user_id: int, mode: str = 'write'):
    rating = int(callback.data.split("_")[2])
    await state.update_data(rating=rating)

    await callback.message.edit_text(
        f"Вы поставили: {'⭐' * rating}\n\n"
        f"Теперь напишите, пожалуйста, текстовый отзыв (что понравилось или не понравилось):"
    )
    await state.set_state(LeaveReviewFSM.review_text)
    await callback.answer()


@router.message(LeaveReviewFSM.review_text)
async def get_review_text(message: types.Message, state: FSMContext, db: Database, bot: Bot, user_id: int, mode: str = 'write'):
    data = await state.get_data()
    review_text = message.text.strip()
    current_user_id = message.from_user.id

    order_id = data.get('order_id')
    worker_id = data.get('worker_id')
    rating = data.get('rating')

    if not all([order_id, worker_id, rating]):
        await message.answer("❌ Произошла ошибка FSM. Попробуйте снова.")
        await state.clear()
        return

    try:
        review_service = ReviewService(db)
        # Сохраняем отзыв и сразу получаем данные мастера через сервис (режим write)
        worker_info = await review_service.save_review_and_get_worker(
            order_id=order_id,
            worker_id=worker_id,
            telegram_id=current_user_id,
            rating=rating,
            review_text=review_text,
            user_id=current_user_id,
            mode='write'
        )

        await message.answer(
            "✅ Спасибо! Ваш отзыв сохранен.\n\n"
            "Он поможет другим заказчикам сделать правильный выбор."
        )

        # Отправляем уведомление мастеру, если его нашли
        if worker_info:
            try:
                await bot.send_message(
                    chat_id=worker_info['telegram_id'],
                    text=f"🎉 Вам оставили новый отзыв!\n\n"
                         f"Оценка: {'⭐' * rating}\n"
                         f"Отзыв: {review_text}\n\n"
                         f"Ваш общий рейтинг в профиле обновлен."
                )
            except Exception as e:
                logger.error(f"Не удалось уведомить исполнителя {worker_id} о новом отзыве: {e}")
                await send_error_to_admin(message.bot, e, f"Leave Review (Notify): Worker {worker_id}")

    except Exception as e:
        logger.error(f"Ошибка при сохранении отзыва: {e}", exc_info=True)

        await send_error_to_admin(message.bot, e, f"Leave Review (Save DB): User {current_user_id}")
        await message.answer(f"❌ Произошла ошибка при сохранении отзыва: Администратор уведомлен.")
    finally:
        await state.clear()
