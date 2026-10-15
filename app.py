
import os
import asyncio
import logging

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
KAKAO_KEY = os.getenv("KAKAO_REST_API_KEY")

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
        "Я помогу искать места и услуги по Южной Корее.\n"
        "Напиши, например: «стоматолог в Чхонане» "
        "или «카페 천안».\n\n"
        "Выбирай раздел в меню или отправляй запрос.",
        reply_markup=make_keyboard()
    )

@dp.message(Command("help"))
async def help_command(message: Message):
    await message.answer(
        "TrustMap Korea 🇰🇷\n"
        "Напиши название места или услуги и город.\n"
        "Например: аптека в Сеуле или 카페 천안."
    )

async def search_kakao(query: str):
    if not KAKAO_KEY:
        return None, "Поиск пока не настроен: отсутствует ключ Kakao."

    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_KEY}"}
    params = {"query": query, "size": 5, "page": 1}

    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(
            url, headers=headers, params=params
        ) as response:
            if response.status == 401:
                return None, "Kakao не принял ключ. Проверь REST API Key."
            if response.status == 403:
                return None, "Kakao отклонил запрос. Проверь настройки приложения и доступ к Local API."
            if response.status != 200:
                return None, f"Ошибка поиска Kakao: HTTP {response.status}."
            data = await response.json()
            return data.get("documents", []), None

def format_results(query, places):
    if not places:
        return f"По запросу «{query}» ничего не найдено. Попробуй добавить город или написать запрос по-корейски."

    lines = [f"🔎 Результаты поиска: {query}\n"]
    for i, place in enumerate(places, start=1):
        name = place.get("place_name", "Без названия")
        address = place.get("road_address_name") or place.get("address_name") or "Адрес не указан"
        phone = place.get("phone") or "Не указан"
        link = place.get("place_url", "")
        lines.append(
            f"{i}. {name}\n"
            f"📍 {address}\n"
            f"☎️ {phone}\n"
            f"🔗 {link}"
        )
    lines.append("\nДанные предоставлены Kakao. Перед поездкой уточни часы работы и доступность.")
    return "\n\n".join(lines)

@dp.message()
async def handle_message(message: Message):
    text = (message.text or "").strip()
    if not text:
        return

    for row in CATEGORIES:
        if text in row:
            await message.answer(
                f"Раздел: {text}\n\n"
                "Для поиска напиши конкретный запрос и город.\n"
                "Например: стоматолог в Чхонане или 카센터 천안"
            )
            return

    # Kakao Local API primarily searches Korean place names and keywords.
    # For best results, include the Korean city name or use a Korean query.
    await message.answer("🔎 Ищу места в Kakao. Подожди немного...")
    try:
        places, error = await search_kakao(text)
        if error:
            await message.answer(error)
            return
        await message.answer(format_results(text, places))
    except asyncio.TimeoutError:
        await message.answer("Поиск занял слишком много времени. Попробуй ещё раз.")
    except aiohttp.ClientError:
        logging.exception("Kakao request failed")
        await message.answer("Не удалось связаться с сервисом поиска. Попробуй позже.")
    except Exception:
        logging.exception("Unexpected search error")
        await message.answer("Произошла ошибка при поиске. Попробуй позже.")

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
