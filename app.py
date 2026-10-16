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

# ВНИМАНИЕ: история ИИ хранится в памяти процесса Render.
# После перезапуска/нового деплоя история очистится.
CONVERSATION_HISTORY = {}
LAST_PLACE_SEARCH = {}
MAX_HISTORY_MESSAGES = 12

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
    "кафе": "카페", "кофейня": "카페", "кофейни": "카페", "кофе": "카페",
    "ресторан": "음식점", "рестораны": "음식점", "еда": "음식점",
    "бар": "바", "бары": "바", "баров": "바", "паб": "펍", "пабы": "펍",
    "пабов": "펍", "ночной клуб": "나이트클럽", "ночные клубы": "나이트클럽",
    "клуб": "클럽", "клубы": "클럽", "караоке": "노래방",
    "караоке-бар": "노래방", "пивной бар": "맥주집", "винный бар": "와인바",
    "лаунж": "라운지", "лаунж-бар": "라운지바", "закусочная": "분식집",
    "закусочные": "분식집",
    "больница": "병원", "больницы": "병원", "клиника": "병원",
    "стоматолог": "치과", "стоматология": "치과", "стоматологию": "치과",
    "аптека": "약국", "аптеки": "약국", "магазин": "매장", "магазины": "매장",
    "супермаркет": "마트", "супермаркеты": "마트",
    "детский магазин": "아동용품점", "детские товары": "유아용품",
    "косметика": "화장품", "мебель": "가구점",
    "автосервис": "자동차 정비소", "сто": "자동차 정비소",
    "автозапчасти": "자동차 부품", "запчасти": "자동차 부품",
    "парикмахерская": "미용실", "салон красоты": "미용실",
    "отель": "호텔", "гостиница": "호텔", "ветеринар": "동물병원",
    "ветклиника": "동물병원", "зоомагазин": "반려동물용품",
    "достопримечательности": "관광명소", "достопримечательность": "관광명소",
    "электроника": "전자제품", "спортивный магазин": "스포츠용품",
    "спорттовары": "스포츠용품", "прачечная": "세탁소", "уборка": "청소 서비스",
    "сантехник": "배관", "доставка": "배달", "банк": "은행", "банкомат": "ATM",
    "почта": "우체국", "детский сад": "어린이집", "школа": "학교",
    "парк": "공원", "музей": "박물관", "бассейн": "수영장", "спортзал": "헬스장",
    "аренда машины": "렌터카", "аренду машины": "렌터카",
    "аренда авто": "렌터카", "аренду авто": "렌터카",
    "прокат автомобиля": "렌터카", "прокат машин": "렌터카",
    "аренда автомобиля": "렌터카", "аренду автомобиля": "렌터카",
    "аренда жилья": "부동산", "снять квартиру": "부동산",
    "недвижимость": "부동산", "работа": "일자리",
}

CITIES = {
    "чхонан": "천안", "чонан": "천안", "чханан": "천안", "cheonan": "천안",
    "сеул": "서울", "seoul": "서울", "пусан": "부산", "busan": "부산",
    "инчхон": "인천", "incheon": "인천", "тэгу": "대구", "daegu": "대구",
    "тэджон": "대전", "daejeon": "대전", "сувон": "수원", "suwon": "수원",
    "пхёнтхэк": "평택", "pyeongtaek": "평택", "соннам": "성남", "seongnam": "성남",
    "кванджу": "광주", "gwangju": "광주",
}

STOPWORDS = {
    "в", "во", "на", "по", "для", "у", "около", "рядом", "мне", "найти",
    "найди", "покажи", "ищу", "нужен", "нужна", "нужно", "есть", "самый",
    "самая", "самое", "недорогой", "недорогая", "дешевый", "дешевая",
    "лучший", "лучшая", "лучшие", "the", "in", "near", "find", "show", "please",
    "городе", "город", "корее", "южной", "южная", "машину", "машины",
    "авто", "автомобиль", "автомобиля", "аренда", "аренду", "прокат",
}

PLACE_HINTS = set(TERMS.keys()) | {
    "больницы", "стоматология", "стоматологию", "аптеки", "магазины",
    "рестораны", "бары", "баров", "пабы", "пабов", "ночные клубы",
    "караоке-бар", "аренда машины", "аренда авто", "прокат автомобиля",
    "прокат машин", "аренда автомобиля", "аренду машины", "аренду авто",
    "недвижимость", "снять квартиру", "работа",
}

AI_STARTS = (
    "как ", "почему ", "что ", "кто ", "когда ", "зачем ", "можно ли ",
    "помоги ", "объясни ", "переведи ", "посоветуй ", "сколько стоит ",
    "где находится ", "how ", "why ", "what ", "who ", "when ", "help ",
    "translate ", "explain ",
)

AI_PHRASES = (
    "как сказать", "что значит", "переведи на корейский", "переведи на русский",
    "объясни мне", "помоги мне", "как правильно", "что делать если",
    "как работает", "can you help", "translate into korean", "what does it mean",
)

FOLLOWUP_ONLY = {
    "чхонан", "чонан", "чханан", "cheonan", "сеул", "seoul", "пусан", "busan",
    "инчхон", "incheon", "тэгу", "daegu", "тэджон", "daejeon", "сувон", "suwon",
    "пхёнтхэк", "pyeongtaek", "на неделю", "на месяц", "на день", "подешевле",
    "дешевле", "недорого", "поближе", "рядом", "на выходные",
}


def make_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=item) for item in row] for row in CATEGORIES],
        resize_keyboard=True,
    )


def similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()


def normalize(text):
    return re.sub(r"\s+", " ", (text or "").lower().replace("ё", "е")).strip()


def looks_like_ai_question(text):
    q = normalize(text)
    if q.startswith("/ai"):
        return True
    if any(q.startswith(start) for start in AI_STARTS):
        return True
    if any(phrase in q for phrase in AI_PHRASES):
        return True
    if "?" in q and any(word in q for word in (
        "как", "почему", "что", "можно", "помоги", "how", "why", "what", "can you"
    )):
        return True
    return False


def find_city(text):
    q = normalize(text)
    for city, korean in sorted(CITIES.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(r"(?<!\w)" + re.escape(city) + r"(?!\w)", q):
            return korean
    words = re.findall(r"[a-zа-яё]+", q)
    for word in words:
        for city, korean in CITIES.items():
            if similarity(word, city) >= 0.82:
                return korean
    return None


def translate_query(text):
    query = normalize(text)
    # Сначала заменяем многословные выражения, например «аренда машины».
    for russian, korean in sorted(TERMS.items(), key=lambda item: len(item[0]), reverse=True):
        query = re.sub(r"(?<!\w)" + re.escape(russian) + r"(?!\w)", korean, query)

    # Убираем русские служебные слова, но сохраняем уже переведённые корейские термины.
    words = re.findall(r"[a-zа-яё가-힣]+", query)
    translated = []
    for word in words:
        if re.search(r"[가-힣]", word):
            translated.append(word)
            continue
        if word in STOPWORDS:
            continue

        city_match = None
        best_score = 0
        for city, korean in CITIES.items():
            score = similarity(word, city)
            if score > best_score:
                best_score, city_match = score, korean
        if best_score >= 0.72 and city_match:
            translated.append(city_match)
            continue

        term_match = None
        term_score = 0
        for russian, korean in TERMS.items():
            if " " in russian:
                continue
            score = similarity(word, russian)
            if score > term_score:
                term_score, term_match = score, korean
        if term_score >= 0.78 and term_match:
            translated.append(term_match)
        else:
            translated.append(word)
    return " ".join(translated).strip()


def is_place_search(text):
    q = normalize(text)
    # A city-only reply can continue the user's previous place-search request.
    return any(hint in q for hint in PLACE_HINTS) or (
        bool(find_city(q)) and any(word in q for word in (
            "найди", "найти", "покажи", "поиск", "find", "show", "search"
        ))
    )


async def search_kakao(query):
    if not KAKAO_KEY:
        return None, "Поиск не настроен: отсутствует ключ Kakao."
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_KEY}"}
    params = {"query": query, "size": 5, "page": 1}
    timeout = aiohttp.ClientTimeout(total=15)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status == 401:
                    return None, "Kakao не принял API-ключ. Проверь его настройки."
                if response.status == 403:
                    return None, "Kakao отклонил запрос (HTTP 403). Проверь доступ к Local API."
                if response.status != 200:
                    logging.error("Kakao API error HTTP %s", response.status)
                    return None, f"Ошибка поиска Kakao: HTTP {response.status}."
                data = await response.json()
                return data.get("documents", []), None
    except asyncio.TimeoutError:
        return None, "Поиск занял слишком много времени. Попробуй позже."
    except aiohttp.ClientError:
        logging.exception("Kakao connection error")
        return None, "Не удалось связаться с Kakao. Попробуй позже."


AI_INSTRUCTIONS = (
    "Ты — полноценный ИИ-помощник TrustMap Korea для жизни в Южной Корее. "
    "Отвечай на языке пользователя: русском, английском или корейском. "
    "Отвечай содержательно и понятно: если вопрос сложный, объясняй пошагово, "
    "приводи полезные примеры и варианты. Не задавай повторно вопрос, на который "
    "пользователь уже ответил в истории переписки. Используй предыдущие сообщения, "
    "чтобы понимать короткие ответы вроде города, срока аренды, бюджета или "
    "«подешевле». Если данных действительно не хватает, задай один конкретный "
    "уточняющий вопрос, но не повторяй уже известные детали. Исправляй очевидные "
    "опечатки. Помогай с переводами, покупками, повседневными вопросами и услугами. "
    "Не выдумывай реальные адреса, цены, рейтинги, часы работы, законы или официальные "
    "правила; обозначай неопределённость и советуй проверять важные сведения в "
    "официальных источниках. На медицинские, юридические и иммиграционные темы "
    "отвечай осторожно. Если человек просит найти конкретные места, используй поиск "
    "TrustMap/Kakao, а не выдумывай результаты."
)


async def ask_ai(question, user_id):
    if not OPENAI_KEY:
        return "🤖 ИИ пока не подключён. Проверь OPENAI_API_KEY в Environment на Render."

    history = CONVERSATION_HISTORY.setdefault(str(user_id), [])
    # The Responses API accepts a list of role/content messages as input.
    input_messages = history[-MAX_HISTORY_MESSAGES:] + [
        {"role": "user", "content": question}
    ]
    payload = {
        "model": AI_MODEL,
        "instructions": AI_INSTRUCTIONS,
        "input": input_messages,
        "max_output_tokens": 1000,
        "store": False,
    }
    headers = {
        "Authorization": f"Bearer {OPENAI_KEY}",
        "Content-Type": "application/json",
    }
    timeout = aiohttp.ClientTimeout(total=60)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                "https://api.openai.com/v1/responses",
                headers=headers, json=payload
            ) as response:
                if response.status == 401:
                    logging.error("OpenAI authentication failed")
                    return "ИИ не принял API-ключ. Проверь OPENAI_API_KEY в Render."
                if response.status == 429:
                    return "ИИ временно недоступен: проверь лимиты и оплату OpenAI API."
                if response.status != 200:
                    body = await response.text()
                    logging.error("OpenAI API error HTTP %s: %s", response.status, body[:500])
                    return f"Ошибка ИИ-сервиса: HTTP {response.status}."
                data = await response.json()

        parts = []
        for item in data.get("output", []):
            if item.get("type") == "message":
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        parts.append(content.get("text", ""))
        answer = "\n".join(part for part in parts if part).strip()
        if not answer:
            return "ИИ не вернул текст. Попробуй задать вопрос иначе."

        history.extend([
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ])
        CONVERSATION_HISTORY[str(user_id)] = history[-MAX_HISTORY_MESSAGES:]
        return answer
    except asyncio.TimeoutError:
        return "ИИ отвечает слишком долго. Попробуй ещё раз."
    except aiohttp.ClientError:
        logging.exception("OpenAI connection error")
        return "Не удалось подключиться к ИИ. Попробуй позже."


def describe_category(place):
    category = place.get("category_name", "") + " " + place.get("category_group_name", "")
    descriptions = [
        ("카페", "Кафе или кофейня"), ("음식점", "Ресторан или заведение питания"),
        ("병원", "Больница или медицинская клиника"), ("치과", "Стоматологическая клиника"),
        ("약국", "Аптека"), ("마트", "Супермаркет"), ("호텔", "Отель или гостиница"),
        ("미용실", "Парикмахерская или салон красоты"), ("동물병원", "Ветеринарная клиника"),
        ("자동차", "Автомобильные услуги или товары"), ("관광", "Туристическое место"),
        ("가구", "Мебельный магазин"), ("화장품", "Магазин косметики"),
        ("유아용품", "Магазин детских товаров"), ("전자제품", "Магазин электроники"),
        ("스포츠용품", "Спортивные товары"), ("세탁소", "Прачечная"),
        ("공원", "Парк"), ("박물관", "Музей"), ("학교", "Школа"),
    ]
    for korean, russian in descriptions:
        if korean in category:
            return russian
    return "Категория: " + (category.strip() or "не указана")


def format_results(original_query, korean_query, places):
    if not places:
        return (
            "🇰🇷 TRUSTMAP KOREA\n━━━━━━━━━━━━━━━━━━\n"
            f"😔 По запросу «{original_query}» ничего не найдено.\n"
            f"🇰🇷 Поиск на корейском: {korean_query}\n\n"
            "Попробуй уточнить тип места или город."
        )
    lines = [
        "🇰🇷 TRUSTMAP KOREA", "━━━━━━━━━━━━━━━━━━", "🔎 РЕЗУЛЬТАТЫ ПОИСКА",
        f"💬 Твой запрос: {original_query}", "━━━━━━━━━━━━━━━━━━",
    ]
    for i, place in enumerate(places, start=1):
        name = place.get("place_name", "Название не указано")
        address = place.get("road_address_name") or place.get("address_name") or "Адрес не указан"
        phone = place.get("phone") or "Телефон не указан"
        link = place.get("place_url", "")
        item = (
            f"\n📍 МЕСТО № {i}\n🏢 {name}\n"
            f"🏷️ Категория: {describe_category(place)}\n"
            f"🗺️ Адрес: {address}\n☎️ Телефон: {phone}\n"
        )
        if link:
            item += f"🔗 Карта и подробности: {link}\n"
        item += "⭐ Отзывы TrustMap: пока нет оценок пользователей."
        lines.append(item)
    lines.append(
        "\n━━━━━━━━━━━━━━━━━━\nℹ️ Источник данных: Kakao. "
        "Проверь адрес и часы работы перед посещением.\n"
        "💙 TrustMap Korea — находи нужное с уверенностью!"
    )
    return "\n\n".join(lines)


async def send_long_message(message, text):
    for start_index in range(0, len(text), 3500):
        await message.answer(text[start_index:start_index + 3500])


async def run_place_search(message, query, user_id):
    korean_query = translate_query(query)
    if not korean_query:
        await message.answer("Напиши, какое место или услугу ищешь и в каком городе.")
        return
    LAST_PLACE_SEARCH[str(user_id)] = query
    await message.answer("🔎 Ищу места. Подожди немного...")
    places, error = await search_kakao(korean_query)
    if error:
        await message.answer(error)
        return
    await send_long_message(message, format_results(query, korean_query, places))


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "🇰🇷 TRUSTMAP KOREA\n━━━━━━━━━━━━━━━━━━\n\n"
        "💙 Добро пожаловать! Твой помощник для жизни в Южной Корее.\n\n"
        "🔎 Поиск мест и услуг • 🏥 Медицина • 🍽️ Кафе и рестораны\n"
        "🛍️ Магазины • 🚗 Авто • 🏠 Недвижимость • 💼 Работа\n"
        "🏨 Отели • 📍 Достопримечательности • 🤖 ИИ-помощник\n\n"
        "Можно писать обычными сообщениями, например:\n"
        "• бары в Чхонане\n• аренда машины в Чхонане\n"
        "• как вежливо попросить помощь по-корейски?\n\n"
        "ИИ старается учитывать предыдущие сообщения в этой переписке.",
        reply_markup=make_keyboard(),
    )


@dp.message(Command("help"))
async def help_command(message: Message):
    await message.answer(
        "TrustMap Korea 🇰🇷\n\n"
        "🔎 Поиск мест: «кафе в Чхонане».\n"
        "🚗 Например: «аренда машины в Чхонане».\n"
        "🤖 ИИ: /ai Как сказать спасибо по-корейски?\n"
        "Можно писать по-русски, по-английски или по-корейски."
    )


@dp.message(Command("ai"))
async def ai_command(message: Message):
    question = (message.text or "").partition(" ")[2].strip()
    if not question:
        await message.answer("Напиши вопрос после /ai. Например: /ai Как сказать спасибо по-корейски?")
        return
    await message.answer("🤖 ИИ-помощник готовит ответ...")
    await send_long_message(message, await ask_ai(question, message.from_user.id))


@dp.message()
async def handle_message(message: Message):
    text = (message.text or "").strip()
    if not text:
        return
    user_id = str(message.from_user.id)
    q = normalize(text)

    if text == "🤖 ИИ-помощник":
        await message.answer("🤖 Напиши вопрос обычным сообщением. Я буду учитывать контекст переписки.")
        return
    if text in ("🌐 Язык / Language",):
        await message.answer("🌐 Можно писать по-русски, по-английски или по-корейски. Я отвечу на языке сообщения.")
        return

    for row in CATEGORIES:
        if text in row:
            if text == "🔎 Поиск мест":
                await message.answer("🔎 Напиши, что ищешь и в каком городе. Например: кафе в Чхонане.")
            elif text == "🏥 Медицина":
                await message.answer("🏥 Напиши, что нужно найти и в каком городе. Например: стоматология в Сеуле.")
            elif text == "💰 Сравнение цен":
                await message.answer("💰 Напиши товар или услугу, город и, если важно, бюджет. Фактические цены нужно проверять у продавца.")
            else:
                await message.answer(
                    f"{text}\n\nНапиши обычным сообщением, что именно нужно найти и в каком городе. "
                    "Я постараюсь помочь с поиском или объяснить следующие шаги."
                )
            return

    # Если пользователь ответил одним городом/условием на предыдущий поиск,
    # дополняем предыдущий запрос вместо того, чтобы терять исходный смысл.
    previous_search = LAST_PLACE_SEARCH.get(user_id)
    if previous_search and (q in FOLLOWUP_ONLY or (find_city(q) and len(q.split()) <= 3)):
        city = find_city(q)
        if city:
            city_name = next((name for name, korean in CITIES.items() if korean == city), q)
            combined = f"{previous_search} {city_name}"
        else:
            combined = f"{previous_search} {text}"
        await run_place_search(message, combined, user_id)
        return

    # Если в запросе есть услуга/место, ищем в Kakao.
    if is_place_search(text):
        await run_place_search(message, text, user_id)
        return

    await message.answer("🤖 Передаю сообщение ИИ-помощнику...")
    await send_long_message(message, await ask_ai(text, message.from_user.id))


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
