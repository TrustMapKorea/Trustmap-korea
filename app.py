
import os
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
dp = Dispatcher()

CATEGORIES = [
    ["🏥 Больницы и аптеки", "🚗 СТО и запчасти"],
    ["🏠 Недвижимость", "💼 Работа"],
    ["🛍️ Магазины и цены", "📍 Достопримечательности"],
    ["🔧 Услуги", "📢 Объявления"],
]

def make_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=item) for item in row]
            for row in CATEGORIES
        ],
        resize_keyboard=True
    )

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "Добро пожаловать в TrustMap Korea! 🇰🇷\n\n"
        "Твой помощник по всей Южной Корее.\n"
        "Выбирай раздел в меню или напиши, что ищешь.\n\n"
        "Реальный поиск и сравнение цен подключим далее.",
        reply_markup=make_keyboard()
    )

@dp.message(Command("help"))
async def help_command(message: Message):
    await message.answer(
        "TrustMap Korea 🇰🇷\n"
        "Помощник по жизни в Южной Корее.\n"
        "Выбери раздел в меню или напиши запрос."
    )

@dp.message()
async def handle_message(message: Message):
    text = (message.text or "").strip()

    for row in CATEGORIES:
        if text in row:
            await message.answer(
                f"Раздел: {text}\n\n"
                "Поиск по корейским источникам подключим "
                "на следующем этапе."
            )
            return

    await message.answer(
        f"Твой запрос: «{text}»\n\n"
        "Поиск на русском и корейском будет подключён "
        "на следующих этапах."
    )

async def main():
    if not TOKEN:
        raise RuntimeError("Не задан TELEGRAM_BOT_TOKEN")

    bot = Bot(token=TOKEN)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
