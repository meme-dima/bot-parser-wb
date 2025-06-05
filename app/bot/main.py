import asyncio
from aiogram import Bot, Dispatcher
from .handlers import router
from app.core.utils import setup_logging
import os

TOKEN = os.getenv("WB_BOT_TOKEN", "6019303726:AAFXaULfvUI6CtGKDZLX7XqPxSkQJb0-UzM")

async def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    setup_logging()
    asyncio.run(main()) 