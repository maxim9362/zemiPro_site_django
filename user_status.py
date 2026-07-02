import logging
from aiogram import Router
from aiogram.filters.chat_member_updated import (
    KICKED,
    MEMBER,
    ChatMemberUpdatedFilter
)
from aiogram.types import ChatMemberUpdated

from db import Database

router = Router()
logger = logging.getLogger(__name__)

# Список статусов заказов, которые считаются активными и должны быть удалены при уходе юзера
STATUS_ACTIVE_LIST = ('В обработке', 'В процессе')


class UserStatusService:
    """Класс для работы со статусом пользователя и очисткой данных (ООП)."""

    def __init__(self, db: Database):
        self.db = db

    async def cleanup_user_data(self, user_id: int, mode: str = 'write'):
        """Удаляет активные заказы и отклики пользователя, если он заблокировал бота."""
        if mode != 'write':
            return None

        if not self.db.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.db.pool.acquire() as conn:
            async with conn.transaction():
                # Получаем внутренний ID пользователя (telegram_id передается в user_id)
                user_db_id = await conn.fetchval(
                    "SELECT id FROM users WHERE telegram_id = $1",
                    user_id
                )

                if user_db_id:
                    # 1. Удаляем отклики на активные заказы этого пользователя
                    await conn.execute(
                        """
                        DELETE
                        FROM responses
                        WHERE order_id IN (SELECT id
                                           FROM orders
                                           WHERE client_id = $1
                                             AND status = ANY ($2))
                        """,
                        user_db_id, STATUS_ACTIVE_LIST
                    )

                    # 2. Удаляем сами активные заказы
                    deleted_orders = await conn.execute(
                        """
                        DELETE
                        FROM orders
                        WHERE client_id = $1
                          AND status = ANY ($2)
                        """,
                        user_db_id, STATUS_ACTIVE_LIST
                    )
                    return deleted_orders
        return None


# 1. ПОЛЬЗОВАТЕЛЬ ОСТАНОВИЛ БОТА (KICKED)
@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=KICKED))
async def user_blocked_bot(event: ChatMemberUpdated, db: Database, user_id: int, mode: str = 'write'):
    """
    Срабатывает, когда пользователь блокирует бота.
    Мы НЕ ставим is_blocked = TRUE, чтобы он мог вернуться.
    Мы просто чистим его активные заказы.
    """
    logger.info(f"User {user_id} stopped the bot. Cleaning up orders...")

    try:
        # Инициализация сервиса через внедрение зависимости (DI)
        status_service = UserStatusService(db)

        # Используем сервис (режим write)
        deleted_orders = await status_service.cleanup_user_data(
            user_id=user_id, mode='write'
        )

        if deleted_orders is not None:
            logger.info(f"Cleaned up orders for user {user_id}. Result: {deleted_orders}")

    except Exception as e:
        logger.error(f"Error during order cleanup for user {user_id}: {e}")


# 2. ПОЛЬЗОВАТЕЛЬ ВЕРНУЛСЯ (MEMBER)
@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=MEMBER))
async def user_unblocked_bot(event: ChatMemberUpdated, db: Database, user_id: int, mode: str = 'write'):
    """
    Срабатывает, когда пользователь разблокировал бота.
    Так как мы больше не ставим бан в БД автоматически, нам не нужно
    ничего менять. Мы просто фиксируем возвращение в логах.
    """
    logger.info(f"User {user_id} came back to the bot.")
