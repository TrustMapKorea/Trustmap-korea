
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
    ["🔎 Поиск мест", "🏥 Медицина"],
    ["🍽️ Кафе и рестораны", "🛍️ Магазины"],
    ["🚗 Авто и запчасти", "🏠 Недвижимость"],
    ["💼 Работа", "💄 Красота и уход"],
    ["👶 Товары для детей", "🐾 Товары для животных"],
    ["🔧 Бытовые услуги", "🏨 Отели"],
    ["📍 Достопримечательности", "💰 Сравнение цен"],
    ["🤖 ИИ-помощник", "🌐 Язык / Language"],
]

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
    "стоматологию": "치과",
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
    "найди", "найти", "покажи", "пожалуйста", "мне",
    "лучший", "лучшая", "лучшие", "недорогой", "недорогая",
    "недорогие", "дешевый", "дешевая", "дешевые",
    "the", "in", "near", "find", "show", "please",
}

PLACE_HINTS = set(TERMS.keys()) | {
    "больницы", "стоматология", "стоматологию",
    "аптеки", "магазины", "рестораны",
    "кафе", "запчасти", "автосервис",
}

# Слова и выражения, указывающие на вопрос к ИИ,
# а не на прямой поиск заведения.
AI_STARTS = (
    "как ", "почему ", "зачем ", "что ", "кто ",
    "где находится ", "объясни ", "расскажи ",
    "подскажи ", "помоги ", "переведи ",
    "перевод ", "напиши ", "составь ",
    "посоветуй ", "можешь ", "можно ли ",
    "сколько стоит ", "чем отличается ",
    "how ", "why ", "what ", "who ", "where ",
    "explain ", "translate ", "help me ",
    "tell me ", "can you ", "could you ",
    "please explain ", "please translate ",
)

AI_PHRASES = (
    "как вежливо",
    "как попросить",
    "как сказать",
    "как написать",
    "как спросить",
    "что значит",
    "что означает",
    "переведи на корейский",
    "переведи на русский",
    "по-корейски сказать",
    "по-русски объясни",
    "помоги разобраться",
    "объясни мне",
    "как это работает",
    "how to say",
    "how do i",
    "how can i",
    "what does it mean",
    "translate into korean",
)

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

def looks_like_ai_question(text):
    q = text.lower().replace("ё", "е").strip()

    if q.startswith("/ai"):
        return True

    if any(q.startswith(start) for start in AI_STARTS):
        return True

    if any(phrase in q for phrase in AI_PHRASES):
        return True

    # Вопросы с вопросительным знаком и пояснительными формулировками
    if "?" in q and any(
        word in q for word in (
            "как", "почему", "что", "можно", "помоги",
            "how", "why", "what", "can you",
        )
    ):
        return True

    return False

def translate_query(text):
    query = text.lower().replace("ё", "е")

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

        if re.search(r"[가-힣]", word):
            translated.append(word)
            continue

        city_word = word
        for ending in (
            "ами", "ями", "ого", "ему", "ах", "ях",
            "ом", "ам", "ям", "а", "у", "е", "ы", "и",
        ):
            if (
                city_word.endswith(ending)
                and len(city_word) > len(ending) + 2
            ):
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
    q = text.lower().replace("ё", "е").strip()

    # Вопросы об услугах сначала направляем ИИ.
    if looks_like_ai_question(q):
        return False

    words = re.findall(r"[a-zа-яё가-힣]+", q)

    has_place = any(
        hint in q for hint in PLACE_HINTS
    )

    has_city = any(
        similarity(word, city) >= 0.68
        for word in words
        for city in CITIES
    )

    # Поиск места должен содержать категорию заведения
    # или явное название услуги.
    return has_place or (
        has_city and any(
            word in q for word in (
                "найди", "найти", "покажи", "поиск",
                "find", "show", "search",
            )
        )
    )

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
                return None, "Kakao не принял ключ API. Проверь его настройки."
            if response.status == 403:
                return None, (
                    "Kakao отклонил запрос (HTTP 403). "
                    "Проверь доступ к Local API."
                )
            if response.status != 200:
                return None, f"Ошибка поиска Kakao: HTTP {response.status}."

            data = await response.json()
            return data.get("documents", []), None

async def ask_ai(question):
    if not OPENAI_KEY:
        return (
            "🤖 ИИ пока не подключён.\n"
            "Проверь OPENAI_API_KEY в Environment на Render."
        )

    url = "https://api.openai.com/v1/responses"
    headers = {
        "Authorization": f"Bearer {OPENAI_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": AI_MODEL,
        "instructions": (
            "Ты — ИИ-помощник TrustMap Korea. Отвечай на русском, "
            "английском или корейском в зависимости от языка пользователя. "
            "Помогай с жизнью в Южной Корее, переводами, покупками, "
            "повседневными вопросами и поиском услуг. Исправляй очевидные "
            "опечатки и старайся понять смысл сообщения. Если пользователь "
            "просит найти реальные места, не выдумывай названия, адреса, "
            "цены, рейтинги или часы работы. Объясняй, когда данные требуют "
            "проверки. На медицинские, юридические и иммиграционные вопросы "
            "отвечай осторожно и советуй проверять официальные источники. "
            "Отвечай понятно, дружелюбно и по существу."
        ),
        "input": question,
        "max_output_tokens": 700,
        "store": False,
    }

    timeout = aiohttp.ClientTimeout(total=45)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                url, headers=headers, json=payload
            ) as response:
                if response.status == 401:
                    logging.error("OpenAI authentication failed")
                    return "ИИ не принял API-ключ. Проверь OPENAI_API_KEY в Render."
                if response.status == 429:
                    return (
                        "ИИ временно недоступен: проверь лимиты и оплату "
                        "OpenAI API."
                    )
                if response.status != 200:
                    logging.error("OpenAI API error: HTTP %s", response.status)
                    return f"Ошибка ИИ-сервиса: HTTP {response.status}."

                data = await response.json()

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

    descriptions = [
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

    for korean, russian in descriptions:
        if korean in category:
            return russian

    return "Категория: " + (category.strip() or "не указана")


def format_results(original_query, korean_query, places):
    if not places:
        return (
            "🇰🇷 TRUSTMAP KOREA\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🔎 РЕЗУЛЬТАТЫ ПОИСКА\n\n"
            f"😔 По запросу «{original_query}» ничего не найдено.\n\n"
            f"🇰🇷 Поиск на корейском: {korean_query}\n\n"
            "💡 Попробуй указать город и услугу.\n"
            "Например: стоматология в Чхонане."
        )

    lines = [
        "🇰🇷 TRUSTMAP KOREA",
        "━━━━━━━━━━━━━━━━━━",
        "🔎 РЕЗУЛЬТАТЫ ПОИСКА",
        f"💬 Твой запрос: {original_query}",
        "━━━━━━━━━━━━━━━━━━",
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
            f"\n📍 МЕСТО № {i}\n"
            f"🏢 {name}\n"
            "──────────────────\n"
            f"🏷️ Категория: {description}\n"
            f"🗺️ Адрес: {address}\n"
            f"☎️ Телефон: {phone}\n"
        )

        if link:
            item += f"🔗 Карта и подробности: {link}\n"

        item += (
            "⭐ Отзывы TrustMap: пока нет оценок "
            "пользователей."
        )

        lines.append(item)

    lines.append(
        "\n━━━━━━━━━━━━━━━━━━\n"
        "ℹ️ Источник данных: Kakao.\n"
        "Перед посещением проверь адрес и часы работы.\n\n"
        "💙 TrustMap Korea — находи нужное с уверенностью!"
    )

    return "\n\n".join(lines)


async def send_long_message(message, text):
    for start_index in range(0, len(text), 3500):
        await message.answer(text[start_index:start_index + 3500])

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "Добро пожаловать в TrustMap Korea! 🇰🇷\n\n"
        "Я помогу искать места и услуги в Южной Корее, переводить "
        "фразы и отвечать на повседневные вопросы.\n\n"
        "Примеры:\n"
        "• кафе в Чхонане\n"
        "• стоматология в Сеуле\n"
        "• аптека в Пусане\n"
        "• Как вежливо попросить помощь по-корейски?\n\n"
        "Для вопросов используй обычное сообщение или /ai.\n"
        "Для поиска мест пиши название услуги и город.",
        reply_markup=make_keyboard(),
    )

@dp.message(Command("help"))
async def help_command(message: Message):
    await message.answer(
        "TrustMap Korea 🇰🇷\n\n"
        "🔎 Поиск мест: «кафе в Чхонане».\n"
        "🤖 ИИ: /ai Как сказать спасибо по-корейски?\n\n"
        "Можно задавать обычные вопросы и писать с опечатками."
    )

@dp.message(Command("ai"))
async def ai_command(message: Message):
    question = (message.text or "").partition(" ")[2].strip()

    if not question:
        await message.answer(
            "🤖 Напиши вопрос после /ai.\n"
            "Например: /ai Как вежливо спросить дорогу по-корейски?"
        )
        return

    await message.answer("🤖 ИИ-помощник готовит ответ...")
    await send_long_message(message, await ask_ai(question))

@dp.message()
async def handle_message(message: Message):
    text = (message.text or "").strip()

    if not text:
        return

    if text == "🤖 ИИ-помощник":
        await message.answer(
            "🤖 Напиши любой вопрос обычным сообщением.\n"
            "Например: Как сказать «спасибо» по-корейски?\n"
            "Также можно использовать /ai перед вопросом."
        )
        return

    for row in CATEGORIES:
        if text in row:
            await message.answer(
                f"Раздел: {text}\n\n"
                "Напиши конкретный вопрос или название места и город.\n"
                "Например: стоматология в Чхонане."
            )
            return

    # Сначала определяем намерение: вопрос или поиск заведения.
    if looks_like_ai_question(text):
        await message.answer("🤖 Передаю вопрос ИИ-помощнику...")
        await send_long_message(message, await ask_ai(text))
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
            await send_long_message(message, result)

        except asyncio.TimeoutError:
            await message.answer(
                "Поиск занял слишком много времени. Попробуй позже."
            )
        except aiohttp.ClientError:
            logging.exception("Kakao connection error")
            await message.answer(
                "Не удалось связаться с Kakao. Попробуй позже."
            )
        except Exception:
            logging.exception("Unexpected search error")
            await message.answer(
                "Произошла ошибка поиска. Попробуй позже."
            )

        return

    # Все остальные сообщения передаём ИИ.
    await message.answer("🤖 Передаю вопрос ИИ-помощнику...")
    await send_long_message(message, await ask_ai(text))

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
