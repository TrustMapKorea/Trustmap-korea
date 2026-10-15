
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

# Перевод популярных запросов с русского на корейский.
TRANSLATIONS = {
    "кафе": "카페",
    "кофейня": "카페",
    "ресторан": "음식점",
    "рестораны": "음식점",
    "больница": "병원",
    "больницы": "병원",
    "клиника": "병원",
    "стоматолог": "치과",
    "стоматология": "치과",
    "аптека": "약국",
    "аптеки": "약국",
    "магазин": "매장",
    "супермаркет": "마트",
    "супермаркеты": "마트",
    "детский магазин": "아동용품점",
    "детские товары": "유아용품",
    "косметика": "화장품",
    "мебель": "가구점",
    "автосервис": "자동차 정비소",
    "сто": "자동차 정비소",
    "автозапчасти": "자동차 부품",
    "запчасти": "자동차 부품",
    "парикмахерская": "미용실",
    "салон красоты": "미용실",
    "отель": "호텔",
    "гостиница": "호텔",
    "ветеринар": "동물병원",
    "ветклиника": "동물병원",
    "зоомагазин": "반려동물용품",
    "достопримечательности": "관광명소",
    "достопримечательность": "관광명소",
}

CITIES = {
    "чхонан": "천안",
    "чонан": "천안",
    "cheonan": "천안",
    "сеул": "서울",
    "пусан": "부산",
    "инчхон": "인천",
    "тэгу": "대구",
    "тэджон": "대전",
    "сувон": "수원",
    "соннам": "성남",
    "пхёнтхэк": "평택",
    "хонсон": "홍성",
    "корея": "한국",
    "южная корея": "한국",
}

CATEGORY_DESCRIPTIONS = {
    "카페": "Кафе или кофейня",
    "음식점": "Ресторан или заведение питания",
    "병원": "Больница или медицинская клиника",
    "치과": "Стоматологическая клиника",
    "약국": "Аптека",
    "마트": "Супермаркет или продуктовый магазин",
    "호텔": "Отель или гостиница",
    "미용실": "Парикмахерская или салон красоты",
    "동물병원": "Ветеринарная клиника",
    "자동차 정비소": "Автосервис",
    "자동차 부품": "Магазин автозапчастей",
    "관광명소": "Достопримечательность",
    "가구점": "Мебельный магазин",
    "화장품": "Магазин косметики",
    "유아용품": "Магазин детских товаров",
    "아동용품점": "Магазин детских товаров",
}

def make_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=item) for item in row]
            for row in CATEGORIES
        ],
        resize_keyboard=True
    )

def translate_query(text):
    query = text.lower().strip()

    # Заменяем название города.
    for russian, korean in sorted(
        CITIES.items(), key=lambda item: len(item[0]), reverse=True
    ):
        query = query.replace(russian, korean)

    # Заменяем категории и популярные услуги.
    for russian, korean in sorted(
        TRANSLATIONS.items(), key=lambda item: len(item[0]), reverse=True
    ):
        query = query.replace(russian, korean)

    # Убираем распространённые русские служебные слова.
    for word in [" в ", " возле ", " около ", " рядом с ", " недалеко от "]:
        query = query.replace(word, " ")

    return " ".join(query.split())

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "Добро пожаловать в TrustMap Korea! 🇰🇷\n\n"
        "Я помогу искать места и услуги по Южной Корее.\n\n"
        "Можно писать по-русски:\n"
        "• кафе в Чхонане\n"
        "• стоматолог в Сеуле\n"
        "• аптека в Пусане\n\n"
        "Также можно отправлять запросы на корейском.\n"
        "Выбирай раздел в меню или напиши свой запрос.",
        reply_markup=make_keyboard()
    )

@dp.message(Command("help"))
async def help_command(message: Message):
    await message.answer(
        "TrustMap Korea 🇰🇷\n\n"
        "Напиши название места или услуги и город.\n"
        "Примеры:\n"
        "• кафе в Чхонане\n"
        "• стоматолог в Сеуле\n"
        "• 카페 천안\n\n"
        "Я постараюсь найти адреса и контактные данные."
    )

async def search_kakao(query: str):
    if not KAKAO_KEY:
        return None, "Поиск не настроен: отсутствует ключ Kakao."

    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_KEY}"}
    params = {"query": query, "size": 5, "page": 1}

    timeout = aiohttp.ClientTimeout(total=15)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(
            url, headers=headers, params=params
        ) as response:
            if response.status == 401:
                return None, "Kakao не принял ключ API. Проверь настройки ключа."
            if response.status == 403:
                return None, (
                    "Kakao отклонил запрос (HTTP 403). "
                    "Нужно проверить доступ к Local API."
                )
            if response.status != 200:
                return None, f"Ошибка поиска Kakao: HTTP {response.status}."

            data = await response.json()
            return data.get("documents", []), None

def describe_category(place):
    category = place.get("category_name", "")
    group = place.get("category_group_name", "")
    combined = f"{category} {group}"

    translations = [
        ("카페", "Кафе или кофейня"),
        ("음식점", "Ресторан или заведение питания"),
        ("병원", "Медицинское учреждение"),
        ("약국", "Аптека"),
        ("치과", "Стоматология"),
        ("마트", "Магазин или супермаркет"),
        ("미용실", "Парикмахерская или салон красоты"),
        ("자동차", "Автомобильные услуги или товары"),
        ("숙박", "Гостиница или размещение"),
        ("관광", "Туристическое место"),
        ("동물병원", "Ветеринарная клиника"),
    ]

    for korean, russian in translations:
        if korean in combined:
            return russian

    return "Категория: " + (group or category or "не указана")

def format_results(original_query, korean_query, places):
    if not places:
        return (
            f"По запросу «{original_query}» ничего не найдено.\n\n"
            f"Поисковый запрос: {korean_query}\n"
            "Попробуй указать город или написать название услуги по-корейски."
        )

    lines = [
        f"🔎 Результаты поиска\n"
        f"Твой запрос: {original_query}\n"
        f"Поиск на корейском: {korean_query}\n"
    ]

    for i, place in enumerate(places, start=1):
        name = place.get("place_name", "Название не указано")
        address = (
            place.get("road_address_name")
            or place.get("address_name")
            or "Адрес не указан"
        )
        phone = place.get("phone") or "Телефон не указан"
        link = place.get("place_url", "")
        description = describe_category(place)

        item = (
            f"{i}. {name}\n"
            f"📌 Что это: {description}\n"
            f"📍 Адрес: {address}\n"
            f"☎️ Телефон: {phone}\n"
        )

        if link:
            item += f"🗺️ Карта и информация: {link}\n"

        item += "⭐ Рейтинг: пока нет подтверждённых данных от источника"
        lines.append(item)

    lines.append(
        "ℹ️ Информация получена через Kakao. "
        "Проверь часы работы и актуальность данных перед посещением."
    )

    return "\n\n".join(lines)

@dp.message()
async def handle_message(message: Message):
    original_text = (message.text or "").strip()
    if not original_text:
        return

    for row in CATEGORIES:
        if original_text in row:
            await message.answer(
                f"Раздел: {original_text}\n\n"
                "Напиши конкретный запрос и город.\n"
                "Например: стоматолог в Чхонане или 카페 천안."
            )
            return

    korean_query = translate_query(original_text)

    await message.answer("🔎 Ищу места. Подожди немного...")

    try:
        places, error = await search_kakao(korean_query)

        if error:
            await message.answer(error)
            return

        result = format_results(original_text, korean_query, places)

        # Telegram ограничивает длину одного сообщения.
        if len(result) <= 4000:
            await message.answer(result)
        else:
            for start in range(0, len(result), 3500):
                await message.answer(result[start:start + 3500])

    except asyncio.TimeoutError:
        await message.answer(
            "Поиск занял слишком много времени. Попробуй ещё раз."
        )
    except aiohttp.ClientError:
        logging.exception("Kakao request failed")
        await message.answer(
            "Не удалось связаться с Kakao. Попробуй позже."
        )
    except Exception:
        logging.exception("Unexpected search error")
        await message.answer(
            "Произошла ошибка при поиске. Попробуй позже."
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
