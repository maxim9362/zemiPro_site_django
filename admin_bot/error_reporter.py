import traceback
import logging
import os
import html
from aiogram import Bot
from dotenv import load_dotenv

load_dotenv()


class ErrorReporterService:
    """Класс для инкапсуляции логики репортинга ошибок (ООП)."""

    def __init__(self):
        self.admin_id = os.getenv("ADMIN_ID")
        self.admin_bot_token = os.getenv("ADMIN_BOT_TOKEN")

    async def format_error_message(self, source_bot: Bot, error: Exception, context: str) -> str:
        """Формирование безопасного HTML-сообщения об ошибке."""
        error_trace = traceback.format_exc()

        if len(error_trace) > 3000:
            error_trace = error_trace[-3000:]

        try:
            bot_info = await source_bot.get_me()
            bot_username = f"@{bot_info.username}"
        except Exception:
            bot_username = "Unknown Bot"

        context_safe = html.escape(str(context))
        error_safe = html.escape(str(error))
        trace_safe = html.escape(error_trace)

        return (
            f"🚨 <b>КРИТИЧЕСКАЯ ОШИБКА</b>\n"
            f"🤖 Источник: {bot_username}\n"
            f"📂 Контекст: {context_safe}\n\n"
            f"❌ Ошибка: <code>{error_safe}</code>\n\n"
            f"📜 Трейсбек:\n<pre><code class=\"language-python\">{trace_safe}</code></pre>"
        )

    async def report_error(self, source_bot: Bot, error: Exception, context: str = ""):
        """Отправка отчета об ошибке админу с инкапсулированным управлением сессией."""
        if not self.admin_id or not self.admin_bot_token:
            logging.warning("⚠️ Отправка ошибки невозможна: отсутствуют ADMIN_ID или ADMIN_BOT_TOKEN.")
            return

        try:
            text = await self.format_error_message(
                source_bot=source_bot,
                error=error,
                context=context
            )

            async with Bot(token=self.admin_bot_token) as admin_notifier_bot:
                await admin_notifier_bot.send_message(
                    chat_id=int(self.admin_id),
                    text=text,
                    parse_mode="HTML"
                )
        except Exception as e:
            logging.error(f"❌ Критическая ошибка в error_reporter: {e}")


async def send_error_to_admin(source_bot: Bot, error: Exception, context: str = ""):
    """
    Адаптер для вызова сервиса репортинга.
    Обеспечивает обратную совместимость с существующими импортами и архитектурой проекта.
    """
    reporter = ErrorReporterService()
    await reporter.report_error(source_bot, error, context)
