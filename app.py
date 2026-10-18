import os
import re
import asyncio
import logging
import sqlite3
import json
from difflib import SequenceMatcher
from contextlib import closing

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.dispatcher.middlewares.base import BaseMiddleware
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
    ["🧖 Бани и сауны", "🎮 Компьютерные клубы"],
    ["🤖 ИИ-помощник", "🌐 Язык / Language"],
    ["🧹 Очистить чат"],
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
    "компьютерный клуб": "PC방", "компьютерных клубов": "PC방", "пк клуб": "PC방",
    "баня": "찜질방", "бани": "찜질방", "баню": "찜질방", "бань": "찜질방",
    "сауна": "사우나", "сауны": "사우나", "сауну": "사우나",
    "спа": "스파", "джимджильбан": "찜질방", "ччимчильбан": "찜질방",
    "общественная баня": "목욕탕", "общественные бани": "목욕탕",
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
    "компьютерный клуб", "пк клуб", "баня", "бани", "сауна", "сауны",
    "джимджильбан", "ччимчильбан", "общественная баня", "спа",
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
    "quality": "Качество товара / услуги",
    "food": "Вкус еды",
    "speed": "Скорость обслуживания / выполнения",
    "waiting": "Время ожидания",
    "service": "Обслуживание и вежливость",
    "value": "Цена / качество",
    "atmosphere": "Атмосфера и комфорт",
    "cleanliness": "Чистота",
    "communication": "Общение и объяснения",
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS search_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                query TEXT NOT NULL,
                korean_query TEXT NOT NULL,
                results_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                message_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chat_id, message_id)
            )
        """)
        conn.commit()


def save_search_memory(user_id, query, korean_query, places):
    """Persist recent searches and real place links; this survives chat clearing."""
    compact_places = []
    for place in (places or [])[:15]:
        compact_places.append({
            "name": place.get("place_name", "Название не указано"),
            "address": place.get("road_address_name") or place.get("address_name") or "Адрес не указан",
            "phone": place.get("phone") or "",
            "url": place.get("place_url") or "",
            "id": str(place.get("id", "")),
        })
    try:
        with closing(sqlite3.connect(DATABASE_PATH)) as conn:
            conn.execute(
                "INSERT INTO search_memory (user_id, query, korean_query, results_json) VALUES (?, ?, ?, ?)",
                (str(user_id), str(query)[:500], str(korean_query)[:500], json.dumps(compact_places, ensure_ascii=False)),
            )
            # Keep the newest 100 search memories per user to limit database growth.
            conn.execute("""
                DELETE FROM search_memory WHERE user_id = ? AND id NOT IN (
                    SELECT id FROM search_memory WHERE user_id = ? ORDER BY id DESC LIMIT 100
                )
            """, (str(user_id), str(user_id)))
            conn.commit()
    except sqlite3.Error:
        logging.exception("Could not save search memory")


def get_search_memory_context(user_id, limit=8):
    try:
        with closing(sqlite3.connect(DATABASE_PATH)) as conn:
            rows = conn.execute(
                "SELECT query, korean_query, results_json, created_at FROM search_memory "
                "WHERE user_id = ? ORDER BY id DESC LIMIT ?", (str(user_id), limit)
            ).fetchall()
    except sqlite3.Error:
        logging.exception("Could not read search memory")
        return ""
    if not rows:
        return ""
    lines = ["СОХРАНЁННЫЕ ПОИСКИ ЭТОГО ПОЛЬЗОВАТЕЛЯ (это личная память TrustMap, не официальный рейтинг):"]
    for query, korean_query, raw_json, created_at in reversed(rows):
        lines.append(f"- Дата: {created_at}; запрос: {query}; корейский запрос: {korean_query}")
        try:
            places = json.loads(raw_json or "[]")
        except (TypeError, json.JSONDecodeError):
            places = []
        for place in places[:8]:
            line = f"  • {place.get('name', 'Место')}; адрес: {place.get('address', 'не указан')}"
            if place.get("phone"):
                line += f"; телефон: {place['phone']}"
            if place.get("url"):
                line += f"; ссылка: {place['url']}"
            lines.append(line)
    lines.append("Если пользователь спрашивает, что искал раньше, отвечай только по этим сохранённым данным. Если нужной записи нет, честно скажи, что она не сохранилась.")
    return "\n".join(lines)


def track_chat_message(chat_id, message_id):
    """Track recent message IDs so the clear button can delete what Telegram permits."""
    try:
        with closing(sqlite3.connect(DATABASE_PATH)) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO chat_messages (chat_id, message_id) VALUES (?, ?)",
                (str(chat_id), int(message_id)),
            )
            conn.execute("""
                DELETE FROM chat_messages WHERE chat_id = ? AND id NOT IN (
                    SELECT id FROM chat_messages WHERE chat_id = ? ORDER BY id DESC LIMIT 300
                )
            """, (str(chat_id), str(chat_id)))
            conn.commit()
    except sqlite3.Error:
        logging.exception("Could not track chat message")


class ChatMessageTrackingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, Message) and event.chat and event.message_id:
            track_chat_message(event.chat.id, event.message_id)
        return await handler(event, data)


_original_send_message = Bot.send_message


async def _tracked_send_message(self, chat_id, text, *args, **kwargs):
    sent = await _original_send_message(self, chat_id, text, *args, **kwargs)
    if sent and getattr(sent, "message_id", None) is not None:
        track_chat_message(chat_id, sent.message_id)
    return sent


# Track messages sent via Message.answer(), including callback-driven replies.
Bot.send_message = _tracked_send_message
dp.message.outer_middleware(ChatMessageTrackingMiddleware())


async def clear_tracked_chat(bot, chat_id):
    """Best-effort deletion of tracked recent messages in a private chat."""
    try:
        with closing(sqlite3.connect(DATABASE_PATH)) as conn:
            rows = conn.execute(
                "SELECT message_id FROM chat_messages WHERE chat_id = ? ORDER BY message_id DESC",
                (str(chat_id),),
            ).fetchall()
    except sqlite3.Error:
        logging.exception("Could not load chat messages for clearing")
        rows = []
    deleted = 0
    failed = 0
    for (message_id,) in rows:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=int(message_id))
            deleted += 1
        except Exception:
            # Telegram may reject old messages, protected/service messages, or IDs
            # the bot no longer has permission to delete. Continue with the rest.
            failed += 1
        await asyncio.sleep(0.04)
    try:
        with closing(sqlite3.connect(DATABASE_PATH)) as conn:
            conn.execute("DELETE FROM chat_messages WHERE chat_id = ?", (str(chat_id),))
            conn.commit()
    except sqlite3.Error:
        logging.exception("Could not clear tracked chat message IDs")
    return deleted, failed


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
    timeout = aiohttp.ClientTimeout(total=25)
    results = []
    seen = set()
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Kakao returns at most 15 results per page. Fetch up to 3 pages (45 results).
            for page in range(1, 4):
                params = {"query": query, "size": 15, "page": page}
                async with session.get(url, headers=headers, params=params) as response:
                    if response.status == 401:
                        return None, "Kakao не принял API-ключ. Проверь его настройки."
                    if response.status == 403:
                        return None, "Kakao отклонил запрос (HTTP 403). Проверь доступ к Local API."
                    if response.status != 200:
                        logging.error("Kakao API error HTTP %s", response.status)
                        return None, f"Ошибка поиска Kakao: HTTP {response.status}."
                    data = await response.json()
                documents = data.get("documents", [])
                for place in documents:
                    place_id = str(place.get("id", ""))
                    key = place_id or (place.get("place_name"), place.get("address_name"))
                    if key not in seen:
                        seen.add(key)
                        results.append(place)
                meta = data.get("meta", {})
                if not documents or meta.get("is_end", True):
                    break
        return results, None
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
    memory_context = get_search_memory_context(user_id)
    instructions = AI_INSTRUCTIONS
    if memory_context:
        instructions += "\n\n" + memory_context
    payload = {
        "model": AI_MODEL, "instructions": instructions,
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
        ("찜질방", "Корейская баня / ччимчильбан"), ("목욕탕", "Общественная баня"),
        ("사우나", "Сауна"), ("스파", "СПА-центр"),
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


def rating_dimensions_for_place(place):
    """Return rating dimensions relevant to the kind of place."""
    category = normalize(" ".join([
        str(place.get("category_name", "")),
        str(place.get("place_name", "")),
    ]))
    food_words = ("카페", "음식점", "식당", "restaurant", "cafe", "кафе", "ресторан")
    medical_words = ("병원", "의원", "치과", "약국", "clinic", "hospital", "doctor", "медицин", "больниц", "клиник", "аптек")
    if any(word in category for word in food_words):
        keys = ("overall", "food", "speed", "service", "value", "atmosphere", "cleanliness")
    elif any(word in category for word in medical_words):
        keys = ("overall", "quality", "waiting", "service", "communication", "cleanliness", "value")
    else:
        keys = ("overall", "quality", "speed", "service", "value")
    return [(key, RATING_DIMENSIONS[key]) for key in keys]


def review_keyboard(place_id, place=None):
    dimensions = rating_dimensions_for_place(place or {})
    rows = []
    for i in range(0, len(dimensions), 2):
        rows.append([
            InlineKeyboardButton(
                text=f"⭐ {label}", callback_data=f"rate:{place_id}:{key}"
            ) for key, label in dimensions[i:i + 2]
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def rating_dimensions_keyboard(place_id):
    # Compatibility fallback for older inline buttons.
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
        for key in RATING_DIMENSIONS:
            if key != "overall" and key in summary:
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

    q_normalized = normalize(query)
    city_ko = next((city for city in set(CITIES.values()) if city in korean_query), "")
    variants = [korean_query]
    is_bath_search = any(word in q_normalized for word in ("баня", "бани", "сауна", "сауны", "джимджильбан", "ччимчильбан", "스파", "찜질방", "목욕탕", "사우나"))
    is_pc_search = any(word in q_normalized for word in ("компьютерный клуб", "компьютерные клубы", "пк клуб", "pc방", "피시방"))
    if city_ko and is_bath_search:
        variants = [f"찜질방 {city_ko}", f"목욕탕 {city_ko}", f"사우나 {city_ko}", f"스파 {city_ko}"]
    elif city_ko and is_pc_search:
        variants = [f"PC방 {city_ko}", f"피시방 {city_ko}", f"인터넷카페 {city_ko}"]

    places = []
    seen_ids = set()
    error = None
    for variant in variants:
        found, search_error = await search_kakao(variant)
        if search_error:
            error = search_error
            break
        for place in found or []:
            place_id = str(place.get("id", ""))
            key = place_id or (place.get("place_name"), place.get("address_name"))
            if key not in seen_ids:
                seen_ids.add(key)
                places.append(place)
        if len(places) >= 45:
            places = places[:45]
            break
    if not error:
        save_search_memory(user_id, query, " | ".join(variants), places)
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
        )
        if overall:
            caption += f"💙 Оценка TrustMap: {overall[0]:.1f}/5 ({overall[1]} оценок)\n"
        else:
            caption += "💙 Оценка TrustMap: пока нет оценок\n"
        if link:
            caption += f"\n🔗 Карта: {link}"
        keyboard = review_keyboard(place_id, place) if place_id else None
        await message.answer(caption, reply_markup=keyboard, disable_web_page_preview=False)
    await message.answer("💙 Оценки под карточками — личные отзывы пользователей TrustMap.")


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



def city_keyboard():
    """Inline city choices so users can select a city without typing it."""
    cities = [
        ("📍 Чхонан", "cheonan"), ("🏙️ Сеул", "seoul"),
        ("🌊 Пусан", "busan"), ("✈️ Инчхон", "incheon"),
        ("🌆 Тэгу", "daegu"), ("🏙️ Тэджон", "daejeon"),
        ("🏘️ Сувон", "suwon"), ("📍 Пхёнтхэк", "pyeongtaek"),
        ("🏙️ Соннам", "seongnam"), ("📍 Кванджу", "gwangju"),
    ]
    rows = [[InlineKeyboardButton(text=label, callback_data=f"city:{key}")
             for label, key in cities[i:i + 2]] for i in range(0, len(cities), 2)]
    rows.append([InlineKeyboardButton(text="✍️ Ввести другой город", callback_data="city:other")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="city:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


CITY_CALLBACKS = {
    "cheonan": "천안", "seoul": "서울", "busan": "부산", "incheon": "인천",
    "daegu": "대구", "daejeon": "대전", "suwon": "수원", "pyeongtaek": "평택",
    "seongnam": "성남", "gwangju": "광주",
}



def housing_keyboard(stage):
    options = {
        "budget": [
            ("💰 До 50만 ₩/мес.", "under50"),
            ("💰 50–80만 ₩/мес.", "50to80"),
            ("💰 80–120만 ₩/мес.", "80to120"),
            ("💰 От 120만 ₩/мес.", "over120"),
            ("✍️ Другое / свой бюджет", "other"),
        ],
        "type": [
            ("🏢 Квартира (아파트)", "apartment"),
            ("🏙️ Офистель (오피스텔)", "officetel"),
            ("🏠 Вилла / студия (빌라/원룸)", "villa"),
            ("🔎 Любой тип", "any"),
            ("✍️ Другое", "other"),
        ],
        "rooms": [
            ("🚪 Студия / 1 комната", "one"),
            ("🚪🚪 2 комнаты", "two"),
            ("🚪🚪🚪 3 и больше", "threeplus"),
            ("🔎 Неважно", "any"),
            ("✍️ Другое", "other"),
        ],
        "furnished": [
            ("🛋️ С мебелью", "yes"),
            ("🏚️ Без мебели", "no"),
            ("🔎 Неважно", "any"),
            ("✍️ Другое", "other"),
        ],
    }
    choices = options.get(stage, [])
    rows = [[InlineKeyboardButton(text=label, callback_data=f"home:{stage}:{value}")]
            for label, value in choices]
    if stage != "city":
        rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="home:cancel:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def start_housing_flow(message, user_id):
    user_id = str(user_id)
    LAST_PLACE_SEARCH.pop(user_id, None)
    CONVERSATION_HISTORY.pop(user_id, None)
    USER_FLOWS[user_id] = {"kind": "housing", "stage": "budget", "values": {}}
    await message.answer(
        "🏠 Подберём варианты поиска жилья. Выбери максимальную месячную аренду:",
        reply_markup=housing_keyboard("budget"),
    )


async def advance_housing_flow(message, user_id, stage, value):
    """Save one housing choice and show the next simple button step."""
    user_id = str(user_id)
    flow = USER_FLOWS.get(user_id)
    if not flow or flow.get("kind") != "housing":
        await message.answer("Начни поиск жилья заново: напиши «аренда квартиры».")
        return
    values = flow.setdefault("values", {})
    if stage == "budget":
        values["budget"] = {
            "under50": "월세 50만원 이하",
            "50to80": "월세 50-80만원",
            "80to120": "월세 80-120만원",
            "over120": "월세 120만원 이상",
        }.get(value, value)
        flow["stage"] = "type"
        await message.answer("🏠 Какой тип жилья нужен?", reply_markup=housing_keyboard("type"))
    elif stage == "type":
        values["type"] = {
            "apartment": "아파트", "officetel": "오피스텔",
            "villa": "빌라 원룸", "any": "부동산",
        }.get(value, value)
        flow["stage"] = "rooms"
        await message.answer("🚪 Сколько комнат?", reply_markup=housing_keyboard("rooms"))
    elif stage == "rooms":
        values["rooms"] = {
            "one": "원룸", "two": "방 2개", "threeplus": "방 3개 이상", "any": "",
        }.get(value, value)
        flow["stage"] = "furnished"
        await message.answer("🛋️ Нужна мебель?", reply_markup=housing_keyboard("furnished"))
    elif stage == "furnished":
        values["furnished"] = {
            "yes": "가구 있음", "no": "가구 없음", "any": "",
        }.get(value, value)
        flow["stage"] = "city"
        await message.answer("📍 Выбери город, где ищем жильё:", reply_markup=city_keyboard())


async def finish_housing_flow(message, user_id, city_label, city_ko):
    user_id = str(user_id)
    flow = USER_FLOWS.get(user_id, {})
    values = flow.get("values", {})
    budget = values.get("budget", "")
    housing_type = values.get("type", "부동산")
    rooms = values.get("rooms", "")
    furnished = values.get("furnished", "")
    USER_FLOWS.pop(user_id, None)
    # Kakao Local finds real-estate offices/places, not verified live rental listings.
    query_parts = ["부동산", city_ko]
    if housing_type and housing_type != "부동산":
        query_parts.append(housing_type)
    query = " ".join(query_parts)
    await message.answer(
        f"🔎 Ищу агентства недвижимости в городе {city_label} по выбранным параметрам…\n"
        f"💰 Бюджет: {budget or 'не указан'}\n"
        f"🏠 Тип: {housing_type or 'любой'}\n"
        f"🚪 Комнаты: {rooms or 'неважно'}\n"
        f"🛋️ Мебель: {furnished or 'неважно'}\n\n"
        "ℹ️ Kakao Local показывает агентства и места, а не подтверждённые актуальные объявления аренды.",
    )
    places, error = await search_kakao(query)
    if not error:
        save_search_memory(user_id, f"агентства недвижимости в {city_label}", query, places or [])
    if error:
        await message.answer(error, reply_markup=make_keyboard())
        return
    if not places:
        await message.answer(
            f"😔 Агентства недвижимости по запросу в {city_label} не найдены. Попробуй другой город или тип жилья.",
            reply_markup=make_keyboard(),
        )
        return
    for i, place in enumerate(places, 1):
        place_id = str(place.get("id", ""))
        caption = (
            f"🏠 АГЕНТСТВО №{i}\n\n"
            f"🏢 {place.get('place_name', 'Название не указано')}\n"
            f"📍 {place.get('road_address_name') or place.get('address_name') or 'Адрес не указан'}\n"
            f"☎️ {place.get('phone') or 'Не указан'}"
        )
        if place.get("place_url"):
            caption += f"\n🗺️ Карта: {place['place_url']}"
        await message.answer(caption, reply_markup=review_keyboard(place_id, place) if place_id else None)
    await message.answer("💙 Оценки под карточками — личные отзывы пользователей TrustMap.", reply_markup=make_keyboard())


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


async def finish_clothing_flow(message, user_id, city_text):
    user_id = str(user_id)
    flow = USER_FLOWS.get(user_id, {})
    values = flow.get("values", {})
    audience = values.get("audience", "adult")
    gender = values.get("gender", "unisex")
    budget = values.get("budget", "any")
    city_ko = find_city(city_text) or city_text.strip()

    # Kakao keyword search is sensitive to overly specific queries. Try several
    # natural Korean variants instead of a single long phrase.
    if audience == "child":
        base_terms = ["아동복", "아동복 매장", "유아동 의류", "어린이 옷가게", "아동 의류 매장"]
    elif gender == "men":
        base_terms = ["남성 의류", "남성복 매장", "남자 옷가게", "의류 매장", "옷가게"]
    elif gender == "women":
        base_terms = ["여성 의류", "여성복 매장", "여자 옷가게", "의류 매장", "옷가게"]
    else:
        base_terms = ["의류 매장", "옷가게", "의류 쇼핑", "쇼핑몰"]

    # Keep the budget preference as a secondary query, not as a required keyword.
    if budget == "budget":
        base_terms = ["저렴한 " + term for term in base_terms] + base_terms
    elif budget == "brand":
        base_terms = ["브랜드 " + term for term in base_terms] + base_terms
    queries = []
    for term in base_terms:
        query = f"{term} {city_ko}".strip()
        if query not in queries:
            queries.append(query)

    USER_FLOWS.pop(user_id, None)
    await message.answer(f"🔎 Ищу магазины одежды в городе «{city_text}». Проверю несколько вариантов поиска...")
    places = []
    used_query = queries[0]
    for query in queries:
        found, error = await search_kakao(query)
        if error:
            await message.answer(error, reply_markup=make_keyboard())
            return
        if found:
            places, used_query = found, query
            break

    if not places:
        save_search_memory(user_id, f"магазины одежды в {city_text}", used_query, [])
        await message.answer(
            f"😔 Kakao не нашёл подходящие магазины одежды в городе «{city_text}» по нескольким вариантам запроса. "
            "Попробуй другой город или выбери «Любая» категория одежды.",
            reply_markup=make_keyboard(),
        )
        return

    LAST_PLACE_SEARCH[user_id] = used_query
    save_search_memory(user_id, f"магазины одежды в {city_text}", used_query, places)
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
        await message.answer(caption, reply_markup=review_keyboard(place_id, place) if place_id else None)
    await message.answer("Готово! Можешь выбрать другую категорию в меню.", reply_markup=make_keyboard())


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
        flow["stage"] = "city"
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            "📍 Выбери город для поиска магазинов одежды:",
            reply_markup=city_keyboard(),
        )
        await callback.answer("Выбор сохранён")
        return
    await callback.answer()


@dp.callback_query(F.data.startswith("home:"))
async def housing_callback(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer("Не удалось прочитать выбор.", show_alert=True)
        return
    _, stage, value = parts
    flow = USER_FLOWS.get(user_id)
    if value == "cancel":
        USER_FLOWS.pop(user_id, None)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer("Поиск отменён")
        return
    if not flow or flow.get("kind") != "housing" or flow.get("stage") != stage:
        await callback.answer("Этот шаг уже завершён. Начни поиск жилья заново.", show_alert=True)
        return
    if value == "other":
        flow["awaiting_custom"] = stage
        prompts = {
            "budget": "✍️ Напиши свой бюджет в месяц, например: 70만원 или 700000 вон.",
            "type": "✍️ Напиши нужный тип жилья своими словами.",
            "rooms": "✍️ Напиши количество комнат или пожелание.",
            "furnished": "✍️ Напиши пожелание по мебели.",
        }
        await callback.message.answer(prompts.get(stage, "✍️ Напиши свой вариант."))
        await callback.answer()
        return
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Выбор сохранён")
    await advance_housing_flow(callback.message, user_id, stage, value)


@dp.callback_query(F.data.startswith("city:"))
async def city_callback(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    choice = (callback.data or "").split(":", 1)[1]
    flow = USER_FLOWS.get(user_id)

    if choice == "cancel":
        USER_FLOWS.pop(user_id, None)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer("Поиск отменён")
        return

    if choice == "other":
        if flow and flow.get("stage") == "city":
            flow["allow_custom_city"] = True
        await callback.message.answer("✍️ Напиши название города сообщением.")
        await callback.answer()
        return

    city_ko = CITY_CALLBACKS.get(choice)
    if not city_ko:
        await callback.answer("Не удалось определить город. Попробуй ещё раз.", show_alert=True)
        return

    city_label = {
        "cheonan": "Чхонан", "seoul": "Сеул", "busan": "Пусан", "incheon": "Инчхон",
        "daegu": "Тэгу", "daejeon": "Тэджон", "suwon": "Сувон", "pyeongtaek": "Пхёнтхэк",
        "seongnam": "Соннам", "gwangju": "Кванджу",
    }[choice]
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer(f"Выбран город: {city_label}")

    if not flow or flow.get("stage") != "city":
        await callback.message.answer("Выбор города уже не связан с активным запросом. Напиши запрос заново.", reply_markup=make_keyboard())
        return

    if flow.get("kind") == "clothing":
        await finish_clothing_flow(callback.message, user_id, city_label)
        return

    if flow.get("kind") == "housing":
        await finish_housing_flow(callback.message, user_id, city_label, city_ko)
        return

    if flow.get("kind") == "search":
        original_query = flow.get("values", {}).get("query", "")
        USER_FLOWS.pop(user_id, None)
        await run_place_search(callback.message, f"{original_query} {city_ko}", user_id)
        return

    USER_FLOWS.pop(user_id, None)
    await callback.message.answer("Не удалось продолжить поиск. Попробуй начать его заново.", reply_markup=make_keyboard())


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
            "💙 Выбери показатель и поставь ему оценку:",
            reply_markup=rating_dimensions_keyboard(place_id),
        )
    elif dimension in RATING_DIMENSIONS:
        await callback.message.answer(
            f"💙 Оцени: {RATING_DIMENSIONS[dimension]}\n\n"
            "1 ⭐ — очень плохо · 2 ⭐ — плохо · 3 ⭐ — нормально · 4 ⭐ — хорошо · 5 ⭐ — отлично",
            reply_markup=score_keyboard(place_id, dimension),
        )
    else:
        await callback.answer("Этот показатель больше недоступен. Обнови поиск мест.", show_alert=True)
        return
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
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            "💙 Спасибо! Это личная оценка пользователя TrustMap, а не официальный отзыв заведения."
        )
        await callback.answer("Спасибо за отзыв!")
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
    is_menu_item = any(text in row for row in CATEGORIES)
    active_flow = USER_FLOWS.get(user_id)

    if text == "🧹 Очистить чат":
        CONVERSATION_HISTORY.pop(user_id, None)
        USER_FLOWS.pop(user_id, None)
        LAST_PLACE_SEARCH.pop(user_id, None)
        deleted, failed = await clear_tracked_chat(message.bot, message.chat.id)
        note = ""
        if failed:
            note = f"\n\nℹ️ Telegram не разрешил удалить {failed} старых или недоступных сообщений."
        await message.answer(
            "🧹 Начинаем с чистого листа!\n\n"
            f"Удалено сообщений из чата: {deleted}.{note}\n\n"
            "🧠 Сохранённые поиски мест, адреса и ссылки остались в памяти TrustMap. Можешь спросить: «Помнишь, какую аптеку я искал?».\n\n"
            "Новый диалог готов 👇",
            reply_markup=make_keyboard(),
        )
        return

    if any(phrase in q for phrase in ("помнишь", "что я искал раньше", "что я искала раньше", "мой прошлый поиск", "предыдущий поиск")):
        memory = get_search_memory_context(user_id)
        if memory:
            await message.answer("🧠 Проверяю сохранённую память…")
            await send_long_message(message, await ask_ai(text, message.from_user.id))
        else:
            await message.answer("🧠 Пока у меня нет сохранённых поисков. Когда найдём место через поиск TrustMap, я смогу сохранить его название, адрес и ссылку для будущих вопросов.")
        return

    # При выборе «Другое» принимаем свободный ответ и продолжаем текущий сценарий.
    if active_flow and active_flow.get("kind") == "housing" and active_flow.get("awaiting_custom") and not is_menu_item:
        custom_stage = active_flow.pop("awaiting_custom")
        await advance_housing_flow(message, user_id, custom_stage, text)
        return

    # Продолжаем активный сценарий, если пользователь отвечает на вопрос о городе.
    if active_flow and active_flow.get("stage") == "city" and not is_menu_item:
        # Если вместо города прислали новый запрос, запускаем новый запрос отдельно.
        # Any fresh place-search message replaces the pending query, even if it already contains a city.
        if is_place_search(text):
            USER_FLOWS.pop(user_id, None)
        else:
            city_ko = find_city(text)
            if not city_ko and active_flow.get("allow_custom_city"):
                city_ko = text.strip()
            if not city_ko:
                await message.answer(
                    "Не распознал город. Выбери его кнопкой ниже или введи, например, Чхонан, Сеул или Пусан.",
                    reply_markup=city_keyboard(),
                )
                return
            if active_flow.get("kind") == "clothing":
                await finish_clothing_flow(message, user_id, text)
                return
            if active_flow.get("kind") == "housing":
                await finish_housing_flow(message, user_id, text, city_ko)
                return
            if active_flow.get("kind") == "search":
                original_query = active_flow.get("values", {}).get("query", "")
                USER_FLOWS.pop(user_id, None)
                await run_place_search(message, f"{original_query} {city_ko}", user_id)
                return

    # Не даём предыдущему поиску влиять на новое самостоятельное сообщение.
    LAST_PLACE_SEARCH.pop(user_id, None)

    if text == "🤖 ИИ-помощник":
        USER_FLOWS.pop(user_id, None)
        await message.answer("🤖 Напиши любой вопрос обычным сообщением. Я отвечу на языке сообщения.")
        return
    if text == "🌐 Язык / Language":
        USER_FLOWS.pop(user_id, None)
        await message.answer("🌐 Можно писать по-русски, по-английски или по-корейски. Я отвечу на языке сообщения.")
        return

    for row in CATEGORIES:
        if text in row:
            USER_FLOWS.pop(user_id, None)
            if text == "🔎 Поиск мест":
                await message.answer("🔎 Напиши, что ищешь. Если город не указан, я уточню его.")
            elif text == "🏥 Медицина":
                await message.answer("🏥 Напиши, что нужно найти. Если город не указан, я уточню его.")
            elif text == "💰 Сравнение цен":
                await message.answer("💰 Напиши товар или услугу и, по возможности, бюджет. Если город нужен для поиска, я уточню его.")
            elif text == "🛍️ Магазины":
                await message.answer("🛍️ Что ищем? Например: «одежду», «детские товары» или «косметику».")
            elif text == "🧖 Бани и сауны":
                USER_FLOWS[user_id] = {"kind": "search", "stage": "city", "values": {"query": "бани сауны ччимчильбан"}}
                await message.answer("🧖 Найдём бани, ччимчильбаны и сауны. Выбери город:", reply_markup=city_keyboard())
            elif text == "🎮 Компьютерные клубы":
                USER_FLOWS[user_id] = {"kind": "search", "stage": "city", "values": {"query": "компьютерные клубы PC방"}}
                await message.answer("🎮 Найдём компьютерные клубы (PC방). Выбери город:", reply_markup=city_keyboard())
            elif text == "🏠 Недвижимость":
                await start_housing_flow(message, user_id)
            else:
                await message.answer(
                    f"{text}\n\nНапиши, что именно нужно найти. Если для поиска нужен город, я спрошу его отдельно."
                )
            return

    if any(word in q for word in (
        "аренда квартиры", "аренду квартиры", "снять квартиру", "снять жилье", "снять жильё",
        "аренда жилья", "квартира в аренду", "жилье в аренду", "жильё в аренду",
        "аренда дома", "снять дом", "monthly rent", "rent an apartment", "apartment for rent",
    )) or text == "🏠 Недвижимость":
        await start_housing_flow(message, user_id)
        return

    if any(word in q for word in ("одежду", "одежда", "магазин одежды", "женская одежда",
                                  "мужская одежда", "детская одежда", "clothes", "clothing")):
        USER_FLOWS.pop(user_id, None)
        await start_clothing_flow(message, user_id)
        return

    if is_place_search(text):
        if not find_city(text):
            USER_FLOWS[user_id] = {
                "kind": "search",
                "stage": "city",
                "values": {"query": text},
            }
            await message.answer(
                "📍 Выбери город для поиска. Если твоего города нет в списке, нажми «Ввести другой город».",
                reply_markup=city_keyboard(),
            )
            return
        await run_place_search(message, text, user_id)
        return

    USER_FLOWS.pop(user_id, None)
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
