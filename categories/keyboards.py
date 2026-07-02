from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from db import Database

class CategoryKeyboards:
    """
    Класс для управления интерфейсом категорий и подкатегорий (ООП).
    Все данные (кнопки и тексты) берутся строго из БД через объект Database.
    """

    def __init__(self, db: Database):
        """Инициализация сервиса с объектом базы данных."""
        self.db = db

    async def get_help_text(self, user_id: int, mode: str = 'read') -> str:
        """
        Собирает текстовую подсказку динамически из базы данных.
        """
        if mode != 'read' or not self.db.pool:
            return "Ошибка доступа или БД не инициализирована."

        async with self.db.pool.acquire() as conn:
            # Получаем все категории для текстового описания
            rows = await conn.fetch("SELECT name, emoji, description FROM categories ORDER BY id")

        header = "ℹ️ **Подсказка по категориям:**\n\n"
        lines = []
        for row in rows:
            desc = row['description'] if row['description'] else "описание в процессе наполнения..."
            line = f"{row['emoji']} **{row['name']}** — {desc}"
            lines.append(line)

        return header + "\n".join(lines)

    async def get_categories_kb(self, prefix: str, user_id: int, mode: str = 'read') -> InlineKeyboardMarkup:
        """
        Генерирует кнопки ГЛАВНЫХ категорий.
        """
        if mode != 'read' or not self.db.pool:
            return InlineKeyboardMarkup(inline_keyboard=[])

        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch("SELECT name, emoji FROM categories ORDER BY id")

        builder = InlineKeyboardBuilder()
        for row in rows:
            builder.button(
                text=f"{row['emoji']} {row['name']}",
                callback_data=f"{prefix}{row['name']}"
            )

        # Если это выбор навыков для мастера, добавляем кнопку сохранения
        if prefix == "skill_":
            builder.row(InlineKeyboardButton(text="✅ Готово (Сохранить)", callback_data="skills_done"))

        builder.adjust(2)
        return builder.as_markup()

    async def get_subcategories_kb(self, category_name: str, prefix: str, user_id: int, mode: str = 'read') -> InlineKeyboardMarkup:
        """
        Генерирует кнопки ПОДКАТЕГОРИЙ для конкретной выбранной категории.
        """
        if mode != 'read' or not self.db.pool:
            return InlineKeyboardMarkup(inline_keyboard=[])

        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT s.name
                FROM subcategories s
                JOIN categories c ON s.category_id = c.id
                WHERE c.name = $1
                ORDER BY s.id
            """, category_name)

        builder = InlineKeyboardBuilder()
        for row in rows:
            builder.button(
                text=row['name'],
                callback_data=f"{prefix}{row['name']}"
            )

        builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_categories"))
        builder.adjust(2)
        return builder.as_markup()