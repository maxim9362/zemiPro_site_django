import asyncpg
from config import DATABASE_URL
import asyncpg.pool
from datetime import datetime

# Импортируем данные из твоего нового модуля
from categories.initial_data import INITIAL_CATEGORIES, INITIAL_SUBCATEGORIES


class Database:
    """Класс для управления базой данных (ООП)."""

    def __init__(self):
        self.pool: asyncpg.pool.Pool | None = None

    async def create_pool(self, user_id: int, mode: str = 'write') -> asyncpg.pool.Pool:
        """Создает пул соединений с заранее подготовленными слотами и сохраняет в состоянии объекта."""
        if mode != 'write':
            pass

        self.pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=5,  # Всегда держать 5 соединений открытыми
            max_size=20,  # Разрешать расширение до 20 при нагрузке
            command_timeout=30  # Если запрос завис на 30 сек — обрывать его
        )
        return self.pool

    async def create_tables(self, user_id: int, mode: str = 'write'):
        """
        Создает необходимые таблицы, расширяет структуру и инициализирует категории.
        Использует IF NOT EXISTS для сохранения существующих данных.
        """
        if mode != 'write':
            return

        if not self.pool:
            raise RuntimeError("Пул базы данных не инициализирован. Сначала вызовите create_pool().")

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # --- 1. ГЛАВНАЯ ТАБЛИЦА ПОЛЬЗОВАТЕЛЕЙ ---
                await conn.execute("""
                                   CREATE TABLE IF NOT EXISTS users
                                   (
                                       id
                                       SERIAL
                                       PRIMARY
                                       KEY,
                                       telegram_id
                                       BIGINT
                                       UNIQUE
                                       NOT
                                       NULL,
                                       role
                                       TEXT
                                       NOT
                                       NULL,
                                       last_active
                                       TIMESTAMP
                                       DEFAULT
                                       now
                                   (
                                   ),
                                       is_blocked BOOLEAN DEFAULT FALSE,
                                       created_at TIMESTAMP DEFAULT now
                                   (
                                   )
                                       );
                                   """)

                # --- 2. ПРОФИЛИ ЗАКАЗЧИКОВ ---
                await conn.execute("""
                                   CREATE TABLE IF NOT EXISTS clients
                                   (
                                       user_id
                                       INTEGER
                                       PRIMARY
                                       KEY
                                       REFERENCES
                                       users
                                   (
                                       id
                                   ) ON DELETE CASCADE,
                                       full_name TEXT,
                                       city TEXT,
                                       contact TEXT
                                       );
                                   """)

                # --- 3. ПРОФИЛИ ИСПОЛНИТЕЛЕЙ ---
                await conn.execute("""
                                   CREATE TABLE IF NOT EXISTS workers
                                   (
                                       user_id
                                       INTEGER
                                       PRIMARY
                                       KEY
                                       REFERENCES
                                       users
                                   (
                                       id
                                   ) ON DELETE CASCADE,
                                       name TEXT,
                                       city TEXT,
                                       skills TEXT[],
                                       contact TEXT,
                                       description TEXT,
                                       receive_notifications BOOLEAN DEFAULT TRUE
                                       );
                                   """)

                # --- 4. КАТЕГОРИИ И ПОДКАТЕГОРИИ ---
                await conn.execute("""
                                   CREATE TABLE IF NOT EXISTS categories
                                   (
                                       id
                                       SERIAL
                                       PRIMARY
                                       KEY,
                                       name
                                       VARCHAR
                                   (
                                       100
                                   ) NOT NULL UNIQUE,
                                       emoji VARCHAR
                                   (
                                       10
                                   ),
                                       description TEXT
                                       );
                                   """)

                await conn.execute("""
                                   CREATE TABLE IF NOT EXISTS subcategories
                                   (
                                       id
                                       SERIAL
                                       PRIMARY
                                       KEY,
                                       category_id
                                       INTEGER
                                       REFERENCES
                                       categories
                                   (
                                       id
                                   ) ON DELETE CASCADE,
                                       name VARCHAR
                                   (
                                       100
                                   ) NOT NULL,
                                       UNIQUE
                                   (
                                       category_id,
                                       name
                                   )
                                       );
                                   """)

                await conn.execute("""
                                   CREATE TABLE IF NOT EXISTS worker_subskills
                                   (
                                       worker_id
                                       INTEGER
                                       REFERENCES
                                       users
                                   (
                                       id
                                   ) ON DELETE CASCADE,
                                       subcategory_id INTEGER REFERENCES subcategories
                                   (
                                       id
                                   )
                                     ON DELETE CASCADE,
                                       PRIMARY KEY
                                   (
                                       worker_id,
                                       subcategory_id
                                   )
                                       );
                                   """)

                # --- 5. ТАБЛИЦА ЗАКАЗОВ ---
                await conn.execute("""
                                   CREATE TABLE IF NOT EXISTS orders
                                   (
                                       id
                                       SERIAL
                                       PRIMARY
                                       KEY,
                                       client_id
                                       INTEGER
                                       REFERENCES
                                       users
                                   (
                                       id
                                   ) ON DELETE CASCADE,
                                       worker_id INTEGER REFERENCES users
                                   (
                                       id
                                   )
                                     ON DELETE SET NULL,
                                       category TEXT,
                                       description TEXT,
                                       city TEXT,
                                       price TEXT DEFAULT 'Договорная',
                                       status TEXT DEFAULT 'В обработке',
                                       created_at TIMESTAMP DEFAULT now
                                   (
                                   )
                                       );
                                   """)

                # --- 6. ОТКЛИКИ НА ЗАКАЗЫ ---
                await conn.execute("""
                                   CREATE TABLE IF NOT EXISTS responses
                                   (
                                       id
                                       SERIAL
                                       PRIMARY
                                       KEY,
                                       order_id
                                       INTEGER
                                       REFERENCES
                                       orders
                                   (
                                       id
                                   ) ON DELETE CASCADE,
                                       worker_id INTEGER REFERENCES users
                                   (
                                       id
                                   )
                                     ON DELETE CASCADE,
                                       message TEXT,
                                       created_at TIMESTAMP DEFAULT now
                                   (
                                   )
                                       );
                                   """)

                # --- 7. ОТЗЫВЫ И РЕЙТИНГ ---
                await conn.execute("""
                                   CREATE TABLE IF NOT EXISTS ratings
                                   (
                                       id
                                       SERIAL
                                       PRIMARY
                                       KEY,
                                       order_id
                                       INTEGER
                                       REFERENCES
                                       orders
                                   (
                                       id
                                   ) ON DELETE SET NULL UNIQUE,
                                       worker_id INTEGER REFERENCES users
                                   (
                                       id
                                   )
                                     ON DELETE CASCADE,
                                       client_id INTEGER REFERENCES users
                                   (
                                       id
                                   )
                                     ON DELETE SET NULL,
                                       rating INTEGER,
                                       review_text TEXT,
                                       created_at TIMESTAMP DEFAULT now
                                   (
                                   )
                                       );
                                   """)

                # --- 8. ТЕХНИЧЕСКИЙ ЖУРНАЛ ОШИБОК ---
                await conn.execute("""
                                   CREATE TABLE IF NOT EXISTS error_logs
                                   (
                                       id
                                       SERIAL
                                       PRIMARY
                                       KEY,
                                       error_text
                                       TEXT,
                                       context
                                       TEXT,
                                       created_at
                                       TIMESTAMP
                                       DEFAULT
                                       now
                                   (
                                   )
                                       );
                                   """)

                # --- 9. СТАТИСТИКА ---
                await conn.execute("""
                                   CREATE TABLE IF NOT EXISTS global_stats
                                   (
                                       metric_name
                                       TEXT
                                       PRIMARY
                                       KEY,
                                       count
                                       INTEGER
                                       DEFAULT
                                       0
                                   );
                                   """)

                await conn.execute("""
                                   CREATE TABLE IF NOT EXISTS category_stats
                                   (
                                       category
                                       TEXT
                                       PRIMARY
                                       KEY,
                                       completed_count
                                       INTEGER
                                       DEFAULT
                                       0
                                   );
                                   """)

            # --- ИНИЦИАЛИЗАЦИЯ И ОБНУЛЕНИЕ СТАТИСТИКИ ---
            current_month_marker = int(datetime.now().strftime('%Y%m'))

            await conn.execute("""
                               INSERT INTO global_stats (metric_name, count)
                               VALUES ('total_orders', 0),
                                      ('completed_orders', 0),
                                      ('cancelled_orders', 0),
                                      ('last_reset_month', $1) ON CONFLICT (metric_name) DO NOTHING;
                               """, current_month_marker)

            last_reset = await conn.fetchval(
                "SELECT count FROM global_stats WHERE metric_name = 'last_reset_month'"
            )

            if last_reset and current_month_marker > last_reset:
                print(f"📅 Новый месяц! Сбрасываю счетчики заказов в global_stats.")
                await conn.execute("""
                                   UPDATE global_stats
                                   SET count = 0
                                   WHERE metric_name IN ('total_orders', 'completed_orders', 'cancelled_orders')
                                   """)
                await conn.execute(
                    "UPDATE global_stats SET count = $1 WHERE metric_name = 'last_reset_month'",
                    current_month_marker
                )

            # --- МИГРАЦИИ (ПОДДЕРЖКА АКТУАЛЬНОСТИ) ---
            try:
                await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_active TIMESTAMP DEFAULT now();")
                await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_blocked BOOLEAN DEFAULT FALSE;")
                await conn.execute(
                    "ALTER TABLE workers ADD COLUMN IF NOT EXISTS receive_notifications BOOLEAN DEFAULT TRUE;")
                await conn.execute("ALTER TABLE categories ADD COLUMN IF NOT EXISTS description TEXT;")
            except Exception:
                pass

            # --- НАПОЛНЕНИЕ ТАБЛИЦ ДАННЫМИ ---
            await self.seed_categories(conn, user_id=user_id, mode=mode)
            # await self.seed_subcategories(conn, user_id=user_id, mode=mode)

        print("✅ Структура БД проверена. Категории и описания актуализированы.")

    async def seed_categories(self, conn, user_id: int, mode: str):
        """Заполняет главные категории данными из categories.initial_data."""
        if mode != 'write':
            return

        for name, emoji, desc in INITIAL_CATEGORIES:
            await conn.execute("""
                               INSERT INTO categories (name, emoji, description)
                               VALUES ($1, $2, $3) ON CONFLICT (name) 
                DO
                               UPDATE SET description = EXCLUDED.description, emoji = EXCLUDED.emoji
                               """, name, emoji, desc)

    async def seed_subcategories(self, conn, user_id: int, mode: str):
        """Наполнение подкатегориями из categories.initial_data."""
        if mode != 'write':
            return

        for main_cat_name, sub_list in INITIAL_SUBCATEGORIES.items():
            cat_id = await conn.fetchval("SELECT id FROM categories WHERE name = $1", main_cat_name)
            if cat_id:
                for sub_name in sub_list:
                    await conn.execute("""
                                       INSERT INTO subcategories (category_id, name)
                                       VALUES ($1, $2) ON CONFLICT (category_id, name) DO NOTHING
                                       """, cat_id, sub_name)

    async def get_user_data(self, user_id: int, mode: str):
        """Получение или обновление данных пользователя."""
        if not self.pool:
            raise RuntimeError("Пул базы данных не инициализирован.")

        async with self.pool.acquire() as conn:
            if mode == 'read':
                return await conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", user_id)
            elif mode == 'write':
                await conn.execute("UPDATE users SET last_active = now() WHERE telegram_id = $1", user_id)
                return True
            return None
