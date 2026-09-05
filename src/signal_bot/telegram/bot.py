from __future__ import annotations

from loguru import logger
from telegram import Bot
from telegram.error import TelegramError

from signal_bot.config import get_settings


class TelegramNotifier:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._bot: Bot | None = None
        if self.settings.telegram_bot_token:
            self._bot = Bot(token=self.settings.telegram_bot_token)

    async def send(self, text: str) -> bool:
        if not self._bot or not self.settings.telegram_chat_id:
            logger.warning("Telegram not configured – printing signal to console instead")
            print("\n" + "=" * 40)
            print(text)
            print("=" * 40 + "\n")
            return False
        try:
            await self._bot.send_message(
                chat_id=self.settings.telegram_chat_id,
                text=text,
                disable_web_page_preview=True,
            )
            logger.info("Telegram signal sent")
            return True
        except TelegramError as e:
            logger.error(f"Telegram send failed: {e}")
            return False
