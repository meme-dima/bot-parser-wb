import asyncio
from aiogram import Bot, Dispatcher
from app.bot.handlers import router
from app.core.utils import setup_logging
import os

TOKEN = os.getenv("WB_BOT_TOKEN", "7416839304:AAH0oZxFeBdRQdYLEnft6YiPx-k7UOa2bwQ")

async def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    setup_logging()
    asyncio.run(main()) 