import pytest
import pytest_asyncio
import asyncio
import os
from faker import Faker
from dotenv import load_dotenv

# Импортируем модули бота
import db as db_module
from db import Database
from customer.registration import ClientRegistrationService
from customer.create_an_order import CreateOrderService
from executor.registration_exe import ExecutorRegistrationService
from customer.select_specialist import SpecialistSearchService
from customer.my_orders import MyOrdersService

fake = Faker()
NUM_USERS = 100
CATEGORY = "Электрика"


@pytest_asyncio.fixture(scope="function")
async def db():
    """Инициализация БД с подменой хоста для локального теста."""
    load_dotenv()

    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    db_name = os.getenv("POSTGRES_DB")

    # Принудительно localhost для теста вне Docker
    local_url = f"postgresql://{user}:{password}@localhost:5432/{db_name}"
    db_module.DATABASE_URL = local_url

    database = Database()
    # Твой родной метод
    await database.create_pool(user_id=0, mode='write')

    yield database

    if database.pool:
        await database.pool.close()


async def _get_internal_id(db, tg_id):
    async with db.pool.acquire() as conn:
        return await conn.fetchval("SELECT id FROM users WHERE telegram_id = $1", tg_id)


async def run_user_story(db: Database, client_tg_id: int, worker_tg_id: int):
    """Сценарий: Регистрация -> Заказ -> Отклик -> Выбор -> Завершение."""

    await asyncio.sleep(0.2)  # Небольшая задержка для стабильности пула

    client_reg = ClientRegistrationService(db)
    worker_reg = ExecutorRegistrationService(db)
    order_service = CreateOrderService(db)
    orders_manager = MyOrdersService(db)
    search_service = SpecialistSearchService(db)

    # 1. Регистрация Заказчика
    await client_reg.register_client(
        telegram_id=client_tg_id,
        full_name=fake.name(),
        city="Ashdod",
        phone=fake.phone_number(),
        user_id=client_tg_id,
        mode='write'
    )

    # 2. Регистрация Исполнителя
    await worker_reg.add_worker(
        telegram_id=worker_tg_id,
        full_name=fake.name(),
        city="Ashdod",
        contact=f"@{fake.user_name()}",
        skills=[CATEGORY],
        description="Профессиональный мастер для автотеста.",
        user_id=worker_tg_id,
        mode='write'
    )

    # 3. Подготовка данных и создание заказа
    # Сначала получаем данные клиента, как это делает бот
    client_data = await order_service.check_client_exists(client_tg_id, client_tg_id, 'read')
    assert client_data is not None, f"Клиент {client_tg_id} не найден в базе после регистрации"

    full_address = f"{client_data['city']}, Herzl 12"

    # ВАЖНО: убедись, что в customer/create_an_order.py метод называется create_order
    # Если ты оставил имя create_order_record, замени его здесь ниже
    order = await order_service.create_order(
        client_id=client_data['user_id'],
        category=CATEGORY,
        description="Подробное описание задачи для прохождения валидации в тридцать символов.",
        full_address=full_address,
        price="350",
        user_id=client_tg_id,
        mode='write'
    )
    assert order is not None
    order_id = order['id']

    # 4. Проверка видимости через SpecialistSearchService (чтобы импорт не был серым)
    _, _, total = await search_service.get_workers_for_order(order_id, 0, client_tg_id, 'read')
    assert total >= 1

    # 5. Имитация отклика
    worker_internal_id = await _get_internal_id(db, worker_tg_id)
    async with db.pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO responses (order_id, worker_id, message) VALUES ($1, $2, 'Готов приехать')",
            order_id, worker_internal_id
        )

    # 6. Выбор мастера
    success, _, _ = await orders_manager.select_worker(
        order_id=order_id,
        worker_id=worker_internal_id,
        client_telegram_id=client_tg_id,
        user_id=client_tg_id,
        mode='write'
    )
    assert success is True

    # 7. Завершение заказа
    final_id = await orders_manager.complete_order(
        order_id=order_id,
        telegram_id=client_tg_id,
        user_id=client_tg_id,
        mode='write'
    )
    assert final_id == worker_internal_id


@pytest.mark.asyncio
async def test_mass_parallel_flow(db):
    """Параллельный стресс-тест бизнес-логики."""
    tasks = []
    for i in range(NUM_USERS):
        # Используем новые диапазоны ID для чистоты теста
        tasks.append(run_user_story(db, 60000 + i, 65000 + i))

    await asyncio.gather(*tasks)

    # Проверка статистики
    async with db.pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT count FROM global_stats WHERE metric_name = 'completed_orders'"
        )
        print(f"\n✅ Тест пройден успешно! Завершено заказов в системе: {count}")
        assert count >= NUM_USERS


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v", "-s"])
