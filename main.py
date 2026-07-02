import asyncio
import logging
from datetime import datetime, timedelta
from typing import Callable, Dict, Any, Awaitable

import aiohttp
from aiogram.client.session.aiohttp import AiohttpSession
from aiohttp_socks import ProxyConnector

from aiogram import Bot, Dispatcher, Router, types, BaseMiddleware
from aiogram.types import Update

from config import API_TOKEN
# Импортируем наш новый класс Database
from db import Database

# Импорты роутеров (Заказчик)
from menu.start import router as start_router
from customer.registration import router as customer_reg_router
from customer.create_an_order import router as create_order_router
from customer.edit_order import router as edit_order_router
from customer.my_orders import router as my_orders_router
from customer.select_specialist import router as select_specialist_router
from customer.leave_review import router as leave_review_router
from customer.profile import router as customer_profile_router

# Импорты роутеров (Исполнитель)
from executor.registration_exe import router as executor_reg_router
from executor.new_orders import router as new_orders_router
from executor.my_profile import router as my_profile_router
from executor.edit_profile import router as edit_profile_router
from executor.my_responses import router as my_responses_router

from user_status import router as status_router


class Socks5Session(AiohttpSession):
    """Класс для управления SOCKS5 сессией."""

    def __init__(self, proxy_url: str):
        super().__init__()
        self.proxy_url = proxy_url

    async def create_session(self) -> aiohttp.ClientSession:
        if getattr(self, "_session", None) is None or self._session.closed:
            connector = ProxyConnector.from_url(self.proxy_url)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session


class GlobalMiddleware(BaseMiddleware):
    """
    Middleware для проверки статуса пользователя и обновления его активности.
    Соблюдает правило: прием user_id и mode.
    """

    def __init__(self, db: Database):
        self.db = db

    async def __call__(
            self,
            handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
            event: Update,
            data: Dict[str, Any]
    ) -> Any:
        db = data.get('db')
        user = data.get('event_from_user')

        if db and user:
            user_id = user.id

            # Внедрение зависимостей: пробрасываем user_id и mode для хендлеров
            data['user_id'] = user_id
            data['mode'] = 'write'

            try:
                # 1. Проверка блокировки (режим 'read')
                user_data = await self.db.get_user_data(user_id=user_id, mode='read')

                if user_data:
                    if user_data['is_blocked']:
                        if event.message:
                            await event.message.answer("🚫 Вы заблокированы администратором.")
                        return

                    # 2. Обновление активности (режим 'write')
                    # Проверяем, прошло ли более 5 минут с последнего обновления
                    last_active = user_data['last_active']
                    if not last_active or (datetime.now() - last_active.replace(tzinfo=None)) > timedelta(minutes=5):
                        await self.db.get_user_data(user_id=user_id, mode='write')

            except Exception as e:
                logging.error(f"Middleware Error for user {user_id}: {e}")

        return await handler(event, data)


class TachlesBotApp:
    """
    Основной класс приложения.
    Инкапсулирует логику запуска, настройки и завершения работы бота.
    """

    def __init__(self):
        self.bot: Bot | None = None
        self.dp: Dispatcher | None = None
        self.db: Database | None = None
        self.session: Socks5Session | None = None
        self.catch_all_router = Router()

        # Настройка прокси
        self.proxy_url = "socks5://root:El60T882FZ@170.168.100.47:1080"

    def _setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        )

    def _register_routers(self):
        """Подключение всех роутеров в диспетчер."""

        # Хендлер для неизвестных сообщений
        @self.catch_all_router.message()
        async def unknown_message_handler(message: types.Message, user_id: int = 0, mode: str = 'write'):
            await message.answer(
                "Неверная команда ❌\n"
                "Пожалуйста, воспользуйтесь кнопками меню 👇\n"
                "Или нажмите /start"
            )

        self.dp.include_routers(
            start_router,
            my_responses_router,
            new_orders_router,
            my_orders_router,
            customer_profile_router,
            my_profile_router,
            customer_reg_router,
            executor_reg_router,
            create_order_router,
            edit_order_router,
            select_specialist_router,
            leave_review_router,
            edit_profile_router,
            status_router,
            self.catch_all_router
        )

    async def start(self):
        """Запуск бота."""
        self._setup_logging()

        # Инициализация ресурсов базы данных через экземпляр (ООП)
        self.db = Database()
        await self.db.create_pool(user_id=0, mode='write')

        # Создание таблиц (режим 'write', системный ID 0)
        await self.db.create_tables(user_id=0, mode='write')

        # Инициализация сессии и бота
        self.session = Socks5Session(proxy_url=self.proxy_url)
        self.bot = Bot(token=API_TOKEN, session=self.session)
        self.dp = Dispatcher()

        # Регистрация Middleware
        self.dp.update.outer_middleware.register(GlobalMiddleware(self.db))

        # Регистрация роутеров
        self._register_routers()

        print("✅ Бот TachlesPro запущен!")

        try:
            # Передаем экземпляр базы данных в polling, чтобы он был доступен во всех хендлерах через data['db']
            await self.dp.start_polling(self.bot, db=self.db)
        finally:
            await self.stop()

    async def stop(self):
        """Корректная остановка всех ресурсов."""
        if self.bot:
            await self.bot.session.close()
        if self.db and self.db.pool:
            await self.db.pool.close()
        print("🔌 Бот остановлен, соединения закрыты.")


if __name__ == "__main__":
    # Создаем экземпляр приложения и запускаем его
    app = TachlesBotApp()
    try:
        asyncio.run(app.start())
    except KeyboardInterrupt:
        pass
