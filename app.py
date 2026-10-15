import os
import re
import asyncio
import logging
from difflib import SequenceMatcher

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
KAKAO_KEY = os.getenv("KAKAO_REST_API_KEY")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
AI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

dp = Dispatcher()

CATEGORIES = [
    ["🏥 Больницы и аптеки", "🚗 СТО и запчасти"],
    ["🏠 Недвижимость", "💼 Работа"],
    ["🛍️ Магазины и цены", "📍 Достопримечательности"],
    ["🔧 Услуги", "🤖 ИИ-помощник"],
]

# Категории для поиска в Kakao.
TERMS = {
    "кафе": "카페",
    "кофейня": "카페",
    "ресторан": "음식점",
    "рестораны": "음식점",
    "еда": "음식점",
    "больница": "병원",
    "больницы": "병원",
    "клиника": "병원",
    "стоматолог": "치과",
    "стоматология": "치과",
    "аптека": "약국",
    "аптеки": "약국",
    "магазин": "매장",
    "магазины": "매장",
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
    "электроника": "전자제품",
    "электроника магазин": "전자제품",
    "спортивный магазин": "스포츠용품",
    "спорттовары": "스포츠용품",
    "прачечная": "세탁소",
    "уборка": "청소 서비스",
    "сантехник": "배관",
    "доставка": "배달",
    "банк": "은행",
    "банкомат": "ATM",
    "почта": "우체국",
    "детский сад": "어린이집",
    "школа": "학교",
    "парк": "공원",
    "музей": "박물관",
    "бассейн": "수영장",
    "спортзал": "헬스장",
}

# Варианты написания названий городов.
CITIES = {
    "чхонан": "천안",
    "чонан": "천안",
    "чханан": "천안",
    "cheonan": "천안",
    "сеул": "서울",
    "seoul": "서울",
    "пусан": "부산",
    "busan": "부산",
    "инчхон": "인천",
    "incheon": "인천",
    "тэгу": "대구",
    "daegu": "대구",
    "тэджон": "대전",
    "daejeon": "대전",
    "сувон": "수원",
    "suwon": "수원",
    "пхёнтхэк": "평택",
    "pyeongtaek": "평택",
    "соннам": "성남",
    "seongnam": "성남",
    "кванджу": "광주",
    "gwangju": "광주",
}

STOPWORDS = {
    "в", "во", "на", "около", "возле", "рядом", "с", "по",
    "найди", "найти", "покажи", "пожалуйста", "мне", "лучший",
    "лучшая", "лучшие", "недорогой", "недорогая", "хороший",
    "хорошая", "хорошие", "the", "in", "near", "find", "show",
}

PLACE_HINTS = {
    "кафе", "кофейня", "ресторан", "еда", "больница", "клиника",
    "стоматолог", "стоматология", "аптека", "магазин", "супермаркет",
    "детские товары", "детский магазин", "косметика", "мебель",
    "автосервис", "сто", "автозапчасти", "запчасти",
    "парикмахерская", "салон красоты", "отель", "гостиница",
    "ветеринар", "ветклиника", "зоомагазин", "достопримечательность",
    "достопримечательности", "электроника", "спорттовары",
    "прачечная", "уборка", "сантехник", "банк", "банкомат",
    "почта", "детский сад", "школа", "парк", "музей", "бассейн",
    "спортзал",
}

CATEGORY_DESCRIPTIONS = [
    ("카페", "Кафе или кофейня"),
    ("음식점", "Ресторан или заведение питания"),
    ("병원", "Больница или медицинская клиника"),
    ("치과", "Стоматологическая клиника"),
    ("약국", "Аптека"),
    ("마트", "Супермаркет"),
    ("호텔", "Отель или гостиница"),
    ("미용실", "Парикмахерская или салон красоты"),
    ("동물병원", "Ветеринарная клиника"),
    ("자동차", "Автомобильные услуги или товары"),
    ("관광", "Туристическое место"),
    ("가구", "Мебельный магазин"),
    ("화장품", "Магазин косметики"),
    ("유아용품", "Магазин детских товаров"),
    ("전자제품", "Магазин электроники"),
    ("스포츠용품", "Спортивные товары"),
    ("세탁소", "Прачечная"),
    ("공원", "Парк"),
    ("박물관", "Музей"),
    ("학교", "Школа"),
]

def make_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=item) for item in row]
            for row in CATEGORIES
        ],
        resize_keyboard=True,
    )

def similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()

def translate_query(text):
    query = text.lower().replace("ё", "е")

    # Сначала заменяем многословные категории.
    for russian, korean in sorted(
        TERMS.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if " " in russian:
            query = re.sub(
                r"(?<!\w)" + re.escape(russian) + r"(?!\w)",
                korean,
                query,
            )

    words = re.findall(r"[a-zа-я가-힣]+", query)
    translated = []

    for word in words:
        if word in STOPWORDS:
            continue

        # Уже корейское слово оставляем без изменения.
        if re.search(r"[가-힣]", word):
            translated.append(word)
            continue

        # Распознаём города с окончаниями и опечатками.
        city_word = word
        for ending in ("ами", "ями", "ого", "ему", "ами", "ями",
                       "ах", "ях", "ом", "ам", "ям", "а", "у",
                       "е", "ы", "и"):
            if city_word.endswith(ending) and len(city_word) > len(ending) + 2:
                city_word = city_word[:-len(ending)]
                break

        city_match = None
        best_score = 0

        for name, korean in CITIES.items():
            score = max(
                similarity(word, name),
                similarity(city_word, name),
            )
            if score > best_score:
                best_score = score
                city_match = korean

        if best_score >= 0.68 and city_match:
            translated.append(city_match)
            continue

        # Исправляем распространённые опечатки в названиях услуг.
        term_match = None
        term_score = 0

        for russian, korean in TERMS.items():
            if " " in russian:
                continue
            score = similarity(word, russian)
            if score > term_score:
                term_score = score
                term_match = korean

        if term_score >= 0.76 and term_match:
            translated.append(term_match)
        else:
            translated.append(word)

    return " ".join(translated).strip()

def is_place_search(text):
    lower = text.lower().replace("ё", "е")
    if any(hint in lower for hint in PLACE_HINTS):
        return True
    if any(city in lower for city in CITIES):
        return True
    if re.search(r"[가-힣]", text):
        return True
    return False

async def search_kakao(query):
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

async def ask_ai(question):
    if not OPENAI_KEY:
        return (
            "🤖 ИИ-помощник пока не подключён.\n\n"
            "Нужно добавить OPENAI_API_KEY в Environment на Render. "
            "Ключ создаётся в кабинете OpenAI API. "
            "Использование API может быть платным."
        )

    url = "https://api.openai.com/v1/responses"
    headers = {
        "Authorization": f"Bearer {OPENAI_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": AI_MODEL,
        "instructions": (
            "Ты — TrustMap Korea, полезный русскоязычный помощник по жизни "
            "в Южной Корее. Отвечай ясно и дружелюбно. Помогай с переводом "
            "русского на корейский и обратно, объясняй местные услуги, "
            "покупки, повседневные вопросы и поиск мест. Не выдумывай "
            "адреса, рейтинги, цены, часы работы или факты, которые не "
            "проверены. Если вопрос требует актуальных данных, честно "
            "предупреди, что их нужно проверить в надёжном источнике. "
            "На медицинские, юридические и иммиграционные вопросы отвечай "
            "осторожно и советуй официальные источники."
        ),
        "input": question,
        "max_output_tokens": 600,
        "store": False,
    }

    timeout = aiohttp.ClientTimeout(total=45)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                url, headers=headers, json=payload
            ) as response:
                if response.status == 401:
                    return "ИИ не принял API-ключ. Проверь OPENAI_API_KEY в Render."
                if response.status == 429:
                    return (
                        "ИИ временно недоступен: достигнут лимит запросов "
                        "или недостаточно средств на API-балансе."
                    )
                if response.status != 200:
                    logging.error(
                        "OpenAI API error: HTTP %s", response.status
                    )
                    return f"Ошибка ИИ-сервиса: HTTP {response.status}."

                data = await response.json()

        # Извлекаем текст ответа из Responses API.
        parts = []
        for item in data.get("output", []):
            if item.get("type") == "message":
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        parts.append(content.get("text", ""))

        answer = "\n".join(part for part in parts if part).strip()
        return answer or "ИИ не вернул текст. Попробуй задать вопрос иначе."

    except asyncio.TimeoutError:
        return "ИИ отвечает слишком долго. Попробуй ещё раз."
    except aiohttp.ClientError:
        logging.exception("OpenAI connection error")
        return "Не удалось подключиться к ИИ. Попробуй позже."

def describe_category(place):
    category = (
        place.get("category_name", "") + " " +
        place.get("category_group_name", "")
    )
    for korean, russian in CATEGORY_DESCRIPTIONS:
        if korean in category:
            return russian
    return "Категория: " + (category.strip() or "не указана")

def format_results(original_query, korean_query, places):
    if not places:
        return (
            f"По запросу «{original_query}» ничего не найдено.\n\n"
            f"Поисковый запрос: {korean_query}\n"
            "Попробуй написать город и услугу отдельно или на корейском."
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

        item += (
            "⭐ Рейтинг: источник не предоставил подтверждённую оценку."
        )
        lines.append(item)

    lines.append(
        "ℹ️ Данные получены через Kakao. "
        "Проверь часы работы и актуальность информации перед посещением."
    )
    return "\n\n".join(lines)

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "Добро пожаловать в TrustMap Korea! 🇰🇷\n\n"
        "Я помогу искать места и услуги в Южной Корее, а также отвечать "
        "на повседневные вопросы.\n\n"
        "Примеры поиска:\n"
        "• кафе в Чхонане\n"
        "• стамотолог в Сеуле\n"
        "• аптека в Пусане\n\n"
        "Для обычных вопросов напиши сообщение или используй /ai.\n"
        "Для поиска мест можно писать по-русски или по-корейски.",
        reply_markup=make_keyboard(),
    )

@dp.message(Command("help"))
async def help_command(message: Message):
    await message.answer(
        "TrustMap Korea 🇰🇷\n\n"
        "Поиск мест: «кафе в Чхонане», «аптека в Сеуле».\n"
        "ИИ-помощник: /ai вопрос\n"
        "Пример: /ai Как вежливо спросить дорогу по-корейски?\n\n"
        "Можно писать с опечатками — бот постарается их распознать."
    )

@dp.message(Command("ai"))
async def ai_command(message: Message):
    question = (message.text or "").partition(" ")[2].strip()
    if not question:
        await message.answer(
            "🤖 Напиши вопрос после команды /ai.\n"
            "Например: /ai Как сказать «где аптека?» по-корейски?"
        )
        return

    await message.answer("🤖 ИИ-помощник готовит ответ...")
    answer = await ask_ai(question)
    for start_index in range(0, len(answer), 3500):
        await message.answer(answer[start_index:start_index + 3500])

@dp.message()
async def handle_message(message: Message):
    text = (message.text or "").strip()
    if not text:
        return

    if text == "🤖 ИИ-помощник":
        await message.answer(
            "🤖 Задай мне вопрос обычным сообщением или напиши:\n"
            "/ai Как сказать «спасибо» по-корейски?"
        )
        return

    for row in CATEGORIES:
        if text in row:
            await message.answer(
                f"Раздел: {text}\n\n"
                "Напиши конкретный запрос и город.\n"
                "Например: стоматолог в Чхонане."
            )
            return

    if is_place_search(text):
        korean_query = translate_query(text)
        await message.answer("🔎 Ищу места. Подожди немного...")

        try:
            places, error = await search_kakao(korean_query)
            if error:
                await message.answer(error)
                return

            result = format_results(text, korean_query, places)
            for start_index in range(0, len(result), 3500):
                await message.answer(result[start_index:start_index + 3500])
        except asyncio.TimeoutError:
            await message.answer("Поиск занял слишком много времени. Попробуй позже.")
        except aiohttp.ClientError:
            logging.exception("Kakao connection error")
            await message.answer("Не удалось связаться с Kakao. Попробуй позже.")
        except Exception:
            logging.exception("Unexpected search error")
            await message.answer("Произошла ошибка поиска. Попробуй позже.")
        return

    # Обычные вопросы направляем ИИ-помощнику.
    await message.answer("🤖 Передаю вопрос ИИ-помощнику...")
    answer = await ask_ai(text)
    for start_index in range(0, len(answer), 3500):
        await message.answer(answer[start_index:start_index + 3500])

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
