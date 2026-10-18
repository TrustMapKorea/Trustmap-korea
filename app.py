import os
import re
import asyncio
import logging
import sqlite3
from difflib import SequenceMatcher
from contextlib import closing

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
KAKAO_KEY = os.getenv("KAKAO_REST_API_KEY")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
AI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
DATABASE_PATH = os.getenv("DATABASE_PATH", "trustmap.db")

dp = Dispatcher()

CONVERSATION_HISTORY = {}
LAST_PLACE_SEARCH = {}
USER_FLOWS = {}
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
    "закусочные": "분식집", "компьютерный клуб": "PC방",
    "компьютерные клубы": "PC방", "компьютерный клубы": "PC방",
    "больница": "병원", "больницы": "병원", "клиника": "병원",
    "стоматолог": "치과", "стоматология": "치과", "стоматологию": "치과",
    "аптека": "약국", "аптеки": "약국", "магазин": "매장", "магазины": "매장",
    "магазин одежды": "의류 매장", "одежда": "의류 매장",
    "магазины одежды": "의류 매장", "женская одежда": "여성 의류",
    "мужская одежда": "남성 의류", "детская одежда": "아동복",
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
    "аренда квартиры": "부동산", "аренда квартир": "부동산",
    "аренда дома": "부동산", "аренда помещений": "상가 임대",
    "аренда помещения": "상가 임대", "коммерческое помещение": "상가 임대",
    "недвижимость": "부동산", "работа": "일자리", "вакансии": "일자리",
    "учёба": "학교", "учеба": "학교", "курсы": "학원",
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
    "недвижимость", "снять квартиру", "аренда квартиры", "аренда квартир",
    "аренда помещений", "работа", "одежда", "компьютерные клубы",
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

RATING_DIMENSIONS = {
    "overall": "Общая оценка",
    "food": "Еда / качество",
    "service": "Обслуживание",
    "value": "Цена и качество",
    "atmosphere": "Атмосфера",
}


def init_db():
    with closing(sqlite3.connect(DATABASE_PATH)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                place_id TEXT NOT NULL,
                place_name TEXT NOT NULL,
                user_id TEXT NOT NULL,
                dimension TEXT NOT NULL,
                score INTEGER NOT NULL CHECK(score BETWEEN 1 AND 5),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(place_id, user_id, dimension)
            )
        """)
        conn.commit()


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
    for russian, korean in sorted(TERMS.items(), key=lambda item: len(item[0]), reverse=True):
        query = re.sub(r"(?<!\w)" + re.escape(russian) + r"(?!\w)", korean, query)
    words = re.findall(r"[a-zа-яё가-힣]+", query)
    translated = []
    for word in words:
        if re.search(r"[가-힣]", word):
            translated.append(word)
            continue
        if word in STOPWORDS:
            continue
        city_match, best_score = None, 0
        for city, korean in CITIES.items():
            score = similarity(word, city)
            if score > best_score:
                best_score, city_match = score, korean
        if best_score >= 0.72 and city_match:
            translated.append(city_match)
            continue
        term_match, term_score = None, 0
        for russian, korean in TERMS.items():
            if " " in russian:
                continue
            score = similarity(word, russian)
            if score > term_score:
                term_score, term_match = score, korean
        translated.append(term_match if term_score >= 0.78 and term_match else word)
    return " ".join(translated).strip()


def is_place_search(text):
    q = normalize(text)
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
    "Ты — ИИ-помощник TrustMap Korea для жизни в Южной Корее. Отвечай на языке "
    "пользователя: русском, английском или корейском. Используй контекст предыдущих "
    "сообщений и не задавай повторно вопросы, на которые уже ответили. Если человек "
    "просит найти конкретные места, приложение может запустить поиск Kakao и показать "
    "кнопки выбора параметров. Если данных действительно не хватает, задай один "
    "конкретный вопрос. Исправляй очевидные опечатки. Не выдумывай адреса, цены, "
    "рейтинги, часы работы, законы или официальные правила. Официальные оценки и "
    "оценки пользователей всегда различай. На медицинские, юридические и иммиграционные "
    "темы отвечай осторожно."
)


async def ask_ai(question, user_id):
    if not OPENAI_KEY:
        return "🤖 ИИ пока не подключён. Проверь OPENAI_API_KEY в Environment на Render."
    history = CONVERSATION_HISTORY.setdefault(str(user_id), [])
    input_messages = history[-MAX_HISTORY_MESSAGES:] + [{"role": "user", "content": question}]
    payload = {
        "model": AI_MODEL, "instructions": AI_INSTRUCTIONS,
        "input": input_messages, "max_output_tokens": 1000, "store": False,
    }
    headers = {"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"}
    timeout = aiohttp.ClientTimeout(total=60)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                "https://api.openai.com/v1/responses", headers=headers, json=payload
            ) as response:
                if response.status == 401:
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
        ("의류", "Магазин одежды"), ("PC방", "Компьютерный клуб"),
        ("렌터카", "Аренда автомобилей"), ("부동산", "Недвижимость"),
    ]
    for korean, russian in descriptions:
        if korean in category:
            return russian
    return "Категория: " + (category.strip() or "не указана")


def get_review_summary(place_id):
    with closing(sqlite3.connect(DATABASE_PATH)) as conn:
        rows = conn.execute(
            "SELECT dimension, AVG(score), COUNT(*) FROM reviews "
            "WHERE place_id = ? GROUP BY dimension", (str(place_id),)
        ).fetchall()
    return {row[0]: (float(row[1]), int(row[2])) for row in rows}


def review_keyboard(place_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Оценить место", callback_data=f"rate:{place_id}:menu")],
    ])


def rating_dimensions_keyboard(place_id):
    rows = []
    for key, label in RATING_DIMENSIONS.items():
        rows.append([InlineKeyboardButton(
            text=f"⭐ {label}", callback_data=f"rate:{place_id}:{key}"
        )])
    rows.append([InlineKeyboardButton(text="↩️ Отмена", callback_data="rate:cancel:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def score_keyboard(place_id, dimension):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{n} ⭐", callback_data=f"score:{place_id}:{dimension}:{n}")
         for n in range(1, 6)],
        [InlineKeyboardButton(text="↩️ Отмена", callback_data="rate:cancel:cancel")],
    ])


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
        place_id = str(place.get("id", ""))
        item = (
            f"\n📍 МЕСТО № {i}\n🏢 {name}\n"
            f"🏷️ Категория: {describe_category(place)}\n"
            f"🗺️ Адрес: {address}\n☎️ Телефон: {phone}\n"
        )
        if link:
            item += f"🔗 Карта и подробности: {link}\n"
        # Kakao Local keyword endpoint does not provide a dependable official rating/photo field.
        item += "🏅 Официальный рейтинг: Kakao Local API его не предоставил.\n"
        summary = get_review_summary(place_id) if place_id else {}
        overall = summary.get("overall")
        if overall:
            item += f"💙 TrustMap: {overall[0]:.1f}/5 ({overall[1]} оценок)\n"
        else:
            item += "💙 TrustMap: пока нет оценок пользователей.\n"
        for key in ("food", "service", "value", "atmosphere"):
            if key in summary:
                item += f"  • {RATING_DIMENSIONS[key]}: {summary[key][0]:.1f}/5 ({summary[key][1]})\n"
        lines.append(item.rstrip())
    lines.append(
        "\n━━━━━━━━━━━━━━━━━━\nℹ️ Источник адресов и карточек: Kakao. "
        "Фотографии и официальные оценки доступны не для каждого места. "
        "Проверь детали перед посещением.\n💙 TrustMap Korea"
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
    if not places:
        await send_long_message(message, format_results(query, korean_query, places))
        return
    for i, place in enumerate(places, start=1):
        name = place.get("place_name", "Название не указано")
        address = place.get("road_address_name") or place.get("address_name") or "Адрес не указан"
        phone = place.get("phone") or "Не указан"
        link = place.get("place_url", "")
        place_id = str(place.get("id", ""))
        summary = get_review_summary(place_id) if place_id else {}
        overall = summary.get("overall")
        official = "не предоставлен Kakao Local API"
        caption = (
            f"🇰🇷 TRUSTMAP KOREA · МЕСТО №{i}\n\n"
            f"🏢 {name}\n"
            f"🏷️ {describe_category(place)}\n"
            f"📍 {address}\n"
            f"☎️ {phone}\n"
            f"🏅 Официальный рейтинг: {official}\n"
        )
        if overall:
            caption += f"💙 Оценка TrustMap: {overall[0]:.1f}/5 ({overall[1]} оценок)\n"
        else:
            caption += "💙 Оценка TrustMap: пока нет оценок\n"
        for key in ("food", "service", "value", "atmosphere"):
            if key in summary:
                caption += f"• {RATING_DIMENSIONS[key]}: {summary[key][0]:.1f}/5 ({summary[key][1]})\n"
        if link:
            caption += f"\n🔗 Карта: {link}"
        keyboard = review_keyboard(place_id) if place_id else None
        await message.answer(caption, reply_markup=keyboard, disable_web_page_preview=False)
    await message.answer(
        "ℹ️ Данные о местах получены из Kakao. Фотографии и официальные рейтинги "
        "этот метод API может не предоставлять. Оценки TrustMap — отдельные оценки наших пользователей."
    )


def clothing_keyboard(stage):
    if stage == "audience":
        choices = [
            ("👶 Детская", "child"), ("🧑 Взрослая", "adult"),
        ]
    elif stage == "gender":
        choices = [
            ("👔 Мужская", "men"), ("👗 Женская", "women"), ("👕 Унисекс", "unisex"),
        ]
    else:
        choices = [
            ("💰 Недорого", "budget"), ("✨ Брендовая", "brand"), ("🔎 Любая", "any"),
        ]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=f"cloth:{stage}:{value}")
         for label, value in choices[i:i + 2]]
        for i in range(0, len(choices), 2)
    ])



async def start_clothing_flow(message, user_id):
    user_id = str(user_id)

    # Удаляем старый запрос, чтобы он не вмешивался в выбор одежды.
    LAST_PLACE_SEARCH.pop(user_id, None)

    # Сохраняем новый сценарий выбора одежды.
    USER_FLOWS[user_id] = {
        "kind": "clothing",
        "stage": "audience",
        "values": {},
    }

    await message.answer(
        "👕 Подберём магазины одежды!\n\nДля кого ищем?",
        reply_markup=clothing_keyboard("audience"),
    )


async def finish_clothing_flow(callback, user_id):
    flow = USER_FLOWS.get(str(user_id), {})
    values = flow.get("values", {})
    audience = values.get("audience", "adult")
    gender = values.get("gender", "any")
    budget = values.get("budget", "any")
    audience_ko = "아동복" if audience == "child" else "성인 의류"
    gender_ko = {"men": "남성", "women": "여성", "unisex": "유니섹스"}.get(gender, "")
    budget_ko = {"budget": "저렴한", "brand": "브랜드", "any": ""}.get(budget, "")
    terms = " ".join(x for x in [budget_ko, gender_ko, audience_ko, "매장"] if x)
    city = values.get("city")
    if city:
        terms += " " + city
    USER_FLOWS.pop(str(user_id), None)
    await callback.message.answer(f"🔎 Ищу реальные магазины: {terms}\nПодожди немного...")
    places, error = await search_kakao(terms)
    if error:
        await callback.message.answer(error)
        return
    if not places:
        await callback.message.answer(
            f"😔 Магазины по запросу «{terms}» не найдены. "
            "Попробуй выбрать другой город или написать город отдельным сообщением.",
            reply_markup=make_keyboard(),
        )
        return
    LAST_PLACE_SEARCH[str(user_id)] = terms
    for i, place in enumerate(places, 1):
        place_id = str(place.get("id", ""))
        summary = get_review_summary(place_id) if place_id else {}
        overall = summary.get("overall")
        caption = (
            f"👗 МАГАЗИН №{i}\n\n"
            f"🏢 {place.get('place_name', 'Название не указано')}\n"
            f"📍 {place.get('road_address_name') or place.get('address_name') or 'Адрес не указан'}\n"
            f"☎️ {place.get('phone') or 'Не указан'}\n"
        )
        if overall:
            caption += f"💙 TrustMap: {overall[0]:.1f}/5 ({overall[1]} оценок)\n"
        else:
            caption += "💙 TrustMap: пока нет оценок\n"
        if place.get("place_url"):
            caption += f"🗺️ {place['place_url']}"
        await callback.message.answer(
            caption, reply_markup=review_keyboard(place_id) if place_id else None
        )
    await callback.message.answer("Готово! Можешь выбрать другую категорию в меню.", reply_markup=make_keyboard())


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "🇰🇷 TRUSTMAP KOREA\n━━━━━━━━━━━━━━━━━━\n\n"
        "💙 Добро пожаловать! Твой помощник для жизни в Южной Корее.\n\n"
        "🔎 Поиск мест • 🏥 Медицина • 🍽️ Кафе и рестораны\n"
        "🛍️ Магазины • 🚗 Авто • 🏠 Недвижимость • 💼 Работа\n"
        "🏨 Отели • 📍 Достопримечательности • 🤖 ИИ-помощник\n\n"
        "Примеры: «бары в Чхонане», «аренда машины в Чхонане», "
        "«найди женскую одежду».\n\n"
        "Нажимай кнопки или пиши обычным сообщением.",
        reply_markup=make_keyboard(),
    )


@dp.message(Command("help"))
async def help_command(message: Message):
    await message.answer(
        "TrustMap Korea 🇰🇷\n\n"
        "🔎 Поиск мест: «кафе в Чхонане».\n"
        "👗 Одежда: «найди одежду» — появятся кнопки выбора.\n"
        "🚗 Аренда: «аренда машины в Чхонане».\n"
        "🤖 ИИ: /ai Как сказать спасибо по-корейски?\n"
        "Оценки TrustMap — это отзывы пользователей, не официальный рейтинг."
    )


@dp.message(Command("ai"))
async def ai_command(message: Message):
    question = (message.text or "").partition(" ")[2].strip()
    if not question:
        await message.answer("Напиши вопрос после /ai. Например: /ai Как сказать спасибо по-корейски?")
        return
    if any(word in normalize(question) for word in ("одежду", "одежда", "магазин одежды", "clothes", "clothing")):
        await start_clothing_flow(message, message.from_user.id)
        return
    await message.answer("🤖 ИИ-помощник готовит ответ...")
    await send_long_message(message, await ask_ai(question, message.from_user.id))


@dp.callback_query(F.data.startswith("cloth:"))
async def clothing_callback(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer("Не удалось прочитать выбор.", show_alert=True)
        return
    _, stage, value = parts
    flow = USER_FLOWS.get(user_id)
    if not flow or flow.get("kind") != "clothing":
        await callback.answer("Начни поиск заново: напиши «найди одежду».", show_alert=True)
        return
    values = flow["values"]
    if stage == "audience":
        values["audience"] = value
        flow["stage"] = "gender"
        await callback.message.edit_text("👕 Какой отдел нужен?", reply_markup=clothing_keyboard("gender"))
    elif stage == "gender":
        values["gender"] = value
        flow["stage"] = "budget"
        await callback.message.edit_text("💳 Какой вариант предпочитаешь?", reply_markup=clothing_keyboard("budget"))
    elif stage == "budget":
        values["budget"] = value
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer("Выбор сохранён")
        await finish_clothing_flow(callback, user_id)
        return
    await callback.answer()


@dp.callback_query(F.data.startswith("rate:"))
async def rating_callback(callback: CallbackQuery):
    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer("Некорректная кнопка.", show_alert=True)
        return
    _, place_id, dimension = parts
    if place_id == "cancel":
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer("Отменено")
        return
    if dimension == "menu":
        await callback.message.answer(
            "💙 Какую сторону места хочешь оценить?",
            reply_markup=rating_dimensions_keyboard(place_id),
        )
    elif dimension in RATING_DIMENSIONS:
        await callback.message.answer(
            f"Поставь оценку: {RATING_DIMENSIONS[dimension]}",
            reply_markup=score_keyboard(place_id, dimension),
        )
    await callback.answer()


@dp.callback_query(F.data.startswith("score:"))
async def score_callback(callback: CallbackQuery):
    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        await callback.answer("Некорректная оценка.", show_alert=True)
        return
    _, place_id, dimension, score_text = parts
    try:
        score = int(score_text)
    except ValueError:
        await callback.answer("Некорректная оценка.", show_alert=True)
        return
    if dimension not in RATING_DIMENSIONS or score not in range(1, 6):
        await callback.answer("Некорректная оценка.", show_alert=True)
        return
    place_name = "Место Kakao ID " + place_id
    # Один пользователь может обновлять собственную оценку каждой категории.
    try:
        with closing(sqlite3.connect(DATABASE_PATH)) as conn:
            conn.execute(
                """INSERT INTO reviews (place_id, place_name, user_id, dimension, score)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(place_id, user_id, dimension)
                   DO UPDATE SET score=excluded.score, created_at=CURRENT_TIMESTAMP""",
                (place_id, place_name, str(callback.from_user.id), dimension, score),
            )
            conn.commit()
        summary = get_review_summary(place_id)
        average, count = summary.get(dimension, (float(score), 1))
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            f"💙 Спасибо за оценку!\n{RATING_DIMENSIONS[dimension]}: {score}/5\n"
            f"Средняя оценка TrustMap по этой категории: {average:.1f}/5 ({count} оценок).\n\n"
            "Это рейтинг пользователей TrustMap, не официальный рейтинг заведения."
        )
        await callback.answer("Оценка сохранена")
    except sqlite3.Error:
        logging.exception("Could not save review")
        await callback.answer("Не удалось сохранить оценку. Попробуй позже.", show_alert=True)


@dp.message()
async def handle_message(message: Message):
    text = (message.text or "").strip()
    if not text:
        return
    user_id = str(message.from_user.id)
    q = normalize(text)

    # Каждое новое текстовое сообщение — новый запрос.
    # Не позволяем предыдущему поиску автоматически влиять на текущий.
    LAST_PLACE_SEARCH.pop(user_id, None)

    # Если пользователь написал новое сообщение во время сценария одежды,
    # отменяем незавершённый сценарий. Кнопки одежды обрабатываются callback-ами.
    USER_FLOWS.pop(user_id, None)

    if text == "🤖 ИИ-помощник":
        await message.answer("🤖 Напиши вопрос обычным сообщением. Я буду учитывать контекст переписки.")
        return
    if text == "🌐 Язык / Language":
        await message.answer("🌐 Можно писать по-русски, по-английски или по-корейски. Я отвечу на языке сообщения.")
        return

    for row in CATEGORIES:
        if text in row:
            if text == "🔎 Поиск мест":
                await message.answer("🔎 Напиши, что ищешь и в каком городе. Например: кафе в Чхонане.")
            elif text == "🏥 Медицина":
                await message.answer("🏥 Напиши, что нужно найти и в каком городе. Например: стоматология в Сеуле.")
            elif text == "💰 Сравнение цен":
                await message.answer("💰 Напиши товар или услугу, город и бюджет. Фактические цены нужно проверять у продавца.")
            elif text == "🛍️ Магазины":
                await message.answer("🛍️ Что ищем? Например: «найди одежду» — появятся кнопки выбора.")
            else:
                await message.answer(
                    f"{text}\n\nНапиши, что именно нужно найти и в каком городе. "
                    "Для одежды доступны интерактивные кнопки выбора."
                )
            return

    if any(word in q for word in ("одежду", "одежда", "магазин одежды", "clothes", "clothing")):
        await start_clothing_flow(message, user_id)
        return

    # Не объединяем новое сообщение с LAST_PLACE_SEARCH:
    # это и вызывало повторный запуск старого запроса.

    if is_place_search(text):
        await run_place_search(message, text, user_id)
        return

    await message.answer("🤖 Передаю сообщение ИИ-помощнику...")
    await send_long_message(message, await ask_ai(text, message.from_user.id))


async def main():
    if not TOKEN:
        raise RuntimeError("Не задан TELEGRAM_BOT_TOKEN")
    init_db()
    bot = Bot(token=TOKEN)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
