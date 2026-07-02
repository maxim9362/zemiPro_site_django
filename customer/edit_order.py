import logging

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from admin_bot.error_reporter import send_error_to_admin
from db import Database

router = Router()
logger = logging.getLogger(__name__)


class EditOrder(StatesGroup):
    city = State()
    street = State()
    description = State()


class EditOrderService:
    """Класс для работы с редактированием заказов в БД (ООП)."""

    def __init__(self, db: Database):
        self.db = db

    async def update_order(self, order_id: int, telegram_id: int,
                           new_description: str, full_address: str,
                           user_id: int, mode: str = 'write') -> str:
        """Обновление описания и адреса заказа."""
        if mode != 'write':
            return "UPDATE 0"

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            updated = await conn.execute(
                """
                UPDATE orders
                SET description = $1,
                    city        = $2
                WHERE id = $3
                  AND client_id = (SELECT id
                                   FROM users
                                   WHERE telegram_id = $4)
                """,
                new_description, full_address, order_id, telegram_id
            )
            return updated


@router.callback_query(F.data.startswith("edit_"))
async def start_edit(callback: types.CallbackQuery, state: FSMContext, user_id: int, mode: str = 'write'):
    order_id = int(callback.data.split("_")[1])
    await state.update_data(order_id=order_id)

    await callback.message.answer("Введите новый город:")
    await state.set_state(EditOrder.city)
    await callback.answer()


@router.message(EditOrder.city)
async def edit_city(message: types.Message, state: FSMContext, user_id: int, mode: str = 'write'):
    city = message.text.strip()
    await state.update_data(city=city)
    await message.answer("Введите новую улицу и номер дома (например: sderot herzl 45):")
    await state.set_state(EditOrder.street)


@router.message(EditOrder.street)
async def edit_street(message: types.Message, state: FSMContext, user_id: int, mode: str = 'write'):
    street = message.text.strip()
    await state.update_data(street=street)
    await message.answer("Введите новое описание:")
    await state.set_state(EditOrder.description)


@router.message(EditOrder.description)
async def edit_description(message: types.Message, state: FSMContext, db: Database, user_id: int, mode: str = 'write'):
    user_data = await state.get_data()
    order_id = user_data['order_id']
    new_city = user_data['city']
    new_street = user_data['street']
    new_description = message.text.strip()
    current_user_id = message.from_user.id

    full_address = f"{new_city}, {new_street}"

    customers_menu = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='Создать заказ'), KeyboardButton(text='Мои заказы')],
            [KeyboardButton(text='Мой профиль'), KeyboardButton(text='Главное меню')]
        ],
        resize_keyboard=True
    )

    try:
        edit_service = EditOrderService(db)
        # Вызываем метод из сервиса, соблюдая правила передачи user_id и mode
        updated = await edit_service.update_order(
            order_id=order_id,
            telegram_id=current_user_id,
            new_description=new_description,
            full_address=full_address,
            user_id=current_user_id,
            mode='write'
        )

        if updated == "UPDATE 0":
            logger.warning(f"Попытка обновить несуществующий или чужой заказ: {order_id} пользователем "
                           f"{current_user_id}")
            await message.answer(
                "❌ Не удалось обновить заказ. Возможно, он уже не принадлежит вам или был удален.",
                reply_markup=customers_menu
            )
        else:
            await message.answer(
                "✅ Заказ успешно обновлён!",
                reply_markup=customers_menu
            )

    except Exception as e:
        logger.error(f"Ошибка при обновлении заказа {order_id}: {e}", exc_info=True)

        await send_error_to_admin(message.bot, e, f"Edit Order: {order_id} (User {current_user_id})")
        await message.answer(f"❌ Произошла ошибка при обновлении: Администратор уведомлен.",
                             reply_markup=customers_menu)
    finally:
        await state.clear()
