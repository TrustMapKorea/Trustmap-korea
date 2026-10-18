import os
import re
import json
import asyncio
import logging
import sqlite3
from contextlib import closing
from difflib import SequenceMatcher

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
ADMIN_TELEGRAM_ID = os.getenv("ADMIN_TELEGRAM_ID", "").strip()

dp = Dispatcher()
CONVERSATION_HISTORY = {}
USER_FLOWS = {}
SEARCH_TASKS = {}
MAX_HISTORY_MESSAGES = 12

CATEGORIES = [
    ["🔎 Поиск мест", "🏥 Медицина"],
    ["🍽️ Кафе и рестораны", "🛍️ Магазины"],
    ["🚗 Авто и запчасти", "🚙 Аренда машины"],
    ["🏠 Недвижимость", "💼 Работа"],
    ["💄 Красота и уход", "👶 Товары для детей"],
    ["🧸 Игрушки", "🐾 Товары для животных"],
    ["🔧 Бытовые услуги", "🏨 Отели"],
    ["📍 Достопримечательности", "💰 Сравнение цен"],
    ["🧖 Бани и сауны", "🎮 Компьютерные клубы"],
    ["🤖 ИИ-помощник", "🌐 Язык / Language"],
    ["💬 Отзыв о боте"],
    ["🧹 Очистить чат"],
]

CITIES = {
    "чхонан": "천안", "чонан": "천안", "чханан": "천안", "cheonan": "천안",
    "сеул": "서울", "seoul": "서울", "пусан": "부산", "busan": "부산",
    "инчхон": "인천", "incheon": "인천", "тэгу": "대구", "daegu": "대구",
    "тэджон": "대전", "daejeon": "대전", "сувон": "수원", "suwon": "수원",
    "пхёнтхэк": "평택", "pyeongtaek": "평택", "соннам": "성남", "seongnam": "성남",
    "кванджу": "광주", "gwangju": "광주",
}
CITY_LABELS = {
    "천안": "Чхонан", "서울": "Сеул", "부산": "Пусан", "인천": "Инчхон",
    "대구": "Тэгу", "대전": "Тэджон", "수원": "Сувон", "평택": "Пхёнтхэк",
    "성남": "Соннам", "광주": "Кванджу",
}
CITY_CALLBACKS = {
    "cheonan": "천안", "seoul": "서울", "busan": "부산", "incheon": "인천",
    "daegu": "대구", "daejeon": "대전", "suwon": "수원", "pyeongtaek": "평택",
    "seongnam": "성남", "gwangju": "광주",
}

TERMS = {
    "кафе": "카페", "кофейня": "카페", "кофейни": "카페", "кофе": "카페",
    "ресторан": "음식점", "рестораны": "음식점", "еда": "음식점",
    "бар": "바", "бары": "바", "паб": "펍", "караоке": "노래방",
    "больница": "병원", "больницы": "병원", "клиника": "의원",
    "клиники": "의원", "стоматолог": "치과", "стоматология": "치과",
    "аптека": "약국", "аптеки": "약국", "магазин": "매장", "магазины": "매장",
    "супермаркет": "마트", "супермаркеты": "마트",
    "магазин одежды": "의류 매장", "одежда": "의류 매장",
    "женская одежда": "여성 의류", "мужская одежда": "남성 의류",
    "детская одежда": "아동복", "детский магазин": "아동용품점",
    "детские товары": "유아용품", "игрушка": "장난감", "игрушки": "장난감",
    "магазин игрушек": "장난감 가게", "магазины игрушек": "장난감 가게",
    "автосервис": "자동차 정비소", "сто": "자동차 정비소",
    "автозапчасти": "자동차 부품", "запчасти": "자동차 부품",
    "аренда машины": "렌터카", "аренду машины": "렌터카",
    "аренда авто": "렌터카", "аренда автомобиля": "렌터카",
    "аренду автомобиля": "렌터카", "прокат машин": "렌터카",
    "прокат автомобиля": "렌터카", "машина напрокат": "렌터카",
    "аренда квартиры": "부동산", "аренда жилья": "부동산",
    "снять квартиру": "부동산", "недвижимость": "부동산",
    "работа": "일자리", "вакансии": "일자리",
    "парикмахерская": "미용실", "салон красоты": "미용실",
    "отель": "호텔", "гостиница": "호텔", "ветеринар": "동물병원",
    "зоомагазин": "반려동물용품", "достопримечательности": "관광명소",
    "электроника": "전자제품", "спортивный магазин": "스포츠용품",
    "прачечная": "세탁소", "уборка": "청소 서비스", "сантехник": "배관",
    "парк": "공원", "парки": "공원", "музей": "박물관", "бассейн": "수영장",
    "спортзал": "헬스장", "баня": "찜질방", "бани": "찜질방",
    "сауна": "사우나", "сауны": "사우나", "спа": "스파",
    "компьютерный клуб": "PC방", "компьютерные клубы": "PC방", "пк клуб": "PC방",
}
STOPWORDS = {
    "в", "во", "на", "по", "для", "у", "около", "рядом", "мне", "найти",
    "найди", "покажи", "ищу", "нужен", "нужна", "нужно", "есть", "самый",
    "самая", "самое", "дешевый", "дешевая", "недорогой", "недорогая",
    "лучший", "лучшая", "лучшие", "the", "in", "near", "find", "show",
    "please", "городе", "город", "корее", "южной", "машину", "машины", "или", "ли", "and", "or",
    "авто", "автомобиль", "аренда", "аренду", "прокат", "хочу", "купить",
}
PLACE_HINTS = set(TERMS.keys()) | {
    "игрушки", "игрушка", "аренда машины", "аренда автомобиля",
    "прокат машин", "магазин игрушек", "детские товары", "недвижимость",
    "снять квартиру", "компьютерные клубы", "бани", "сауны",
}
AI_STARTS = (
    "как ", "почему ", "что ", "кто ", "когда ", "зачем ", "можно ли ",
    "помоги ", "объясни ", "переведи ", "посоветуй ", "how ", "why ",
    "what ", "who ", "when ", "help ", "translate ", "explain ",
)
AI_PHRASES = (
    "как сказать", "что значит", "переведи на корейский", "переведи на русский",
    "объясни мне", "помоги мне", "как правильно", "что делать если",
    "как работает", "can you help", "translate into korean", "what does it mean",
)
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

# Для медицинской категории ищем несколько типов учреждений.
MEDICAL_QUERIES = [
    "병원", "종합병원", "대학병원", "의원", "내과", "소아과",
    "치과", "약국", "응급실", "이비인후과", "안과", "피부과",
]
EMERGENCY_QUERIES = ["응급실", "응급의료기관", "119안전센터"]


def db():
    return closing(sqlite3.connect(DATABASE_PATH, timeout=20))


def init_db():
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            place_id TEXT NOT NULL, place_name TEXT NOT NULL,
            user_id TEXT NOT NULL, dimension TEXT NOT NULL,
            score INTEGER NOT NULL CHECK(score BETWEEN 1 AND 5),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(place_id, user_id, dimension))""")
        conn.execute("""CREATE TABLE IF NOT EXISTS search_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
            query TEXT NOT NULL, korean_query TEXT NOT NULL,
            results_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT NOT NULL,
            message_id INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(chat_id, message_id))""")
        conn.execute("""CREATE TABLE IF NOT EXISTS bot_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
            username TEXT, language_code TEXT, feedback_type TEXT NOT NULL,
            message TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        conn.commit()


def normalize(text):
    return re.sub(r"\s+", " ", (text or "").lower().replace("ё", "е")).strip()


def similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()


def find_city(text):
    q = normalize(text)
    for korean in set(CITIES.values()):
        if korean in q:
            return korean
    for city, korean in sorted(CITIES.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(r"(?<!\w)" + re.escape(city) + r"(?!\w)", q):
            return korean
    for word in re.findall(r"[a-zа-яё]+", q):
        for city, korean in CITIES.items():
            if similarity(word, city) >= 0.82:
                return korean
    return None


def translate_query(text):
    q = normalize(text)
    for russian, korean in sorted(TERMS.items(), key=lambda item: len(item[0]), reverse=True):
        q = re.sub(r"(?<!\w)" + re.escape(russian) + r"(?!\w)", korean, q)
    words, out = re.findall(r"[a-zа-яё가-힣]+", q), []
    for word in words:
        if re.search(r"[가-힣]", word):
            out.append(word)
        elif word in STOPWORDS:
            continue
        else:
            city_match, city_score = None, 0
            for city, korean in CITIES.items():
                score = similarity(word, city)
                if score > city_score:
                    city_match, city_score = korean, score
            if city_match and city_score >= 0.72:
                out.append(city_match)
                continue
            term_match, term_score = None, 0
            for term, korean in TERMS.items():
                if " " in term:
                    continue
                score = similarity(word, term)
                if score > term_score:
                    term_match, term_score = korean, score
            out.append(term_match if term_match and term_score >= 0.80 else word)
    return " ".join(out).strip()


def is_place_search(text):
    q = normalize(text)
    if any(x in q for x in (
        "сколько стоит", "что значит", "как сказать", "переведи", "почему", "объясни"
    )):
        return False
    return any(hint in q for hint in PLACE_HINTS) or (
        bool(find_city(q)) and any(w in q for w in (
            "найди", "найти", "покажи", "поиск", "find", "show", "search"
        ))
    )


def make_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=x) for x in row] for row in CATEGORIES],
        resize_keyboard=True,
    )


def city_keyboard():
    items = [
        ("📍 Чхонан", "cheonan"), ("🏙️ Сеул", "seoul"),
        ("🌊 Пусан", "busan"), ("✈️ Инчхон", "incheon"),
        ("🌆 Тэгу", "daegu"), ("🏙️ Тэджон", "daejeon"),
        ("🏘️ Сувон", "suwon"), ("📍 Пхёнтхэк", "pyeongtaek"),
        ("🏙️ Соннам", "seongnam"), ("📍 Кванджу", "gwangju"),
    ]
    rows = [[InlineKeyboardButton(text=t, callback_data=f"city:{k}") for t, k in items[i:i+2]]
            for i in range(0, len(items), 2)]
    rows += [[InlineKeyboardButton(text="✍️ Другой город", callback_data="city:other")],
             [InlineKeyboardButton(text="🌏 Искать по Корее", callback_data="city:nationwide")],
             [InlineKeyboardButton(text="❌ Отмена", callback_data="city:cancel")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def preference_keyboard():
    options = [
        ("💸 Самый дешёвый", "cheap"), ("⚖️ Средний бюджет", "mid"),
        ("💎 Дорогой / премиум", "premium"), ("🔎 Любой вариант", "any"),
    ]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=f"budget:{v}") for t, v in options[:2]],
        [InlineKeyboardButton(text=t, callback_data=f"budget:{v}") for t, v in options[2:]],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="city:cancel")],
    ])


def save_search_memory(user_id, query, korean_query, places):
    compact = [{
        "name": p.get("place_name", "Название не указано"),
        "address": p.get("road_address_name") or p.get("address_name") or "Адрес не указан",
        "phone": p.get("phone") or "", "url": p.get("place_url") or "",
        "id": str(p.get("id", "")),
    } for p in (places or [])[:20]]
    try:
        with db() as conn:
            conn.execute(
                "INSERT INTO search_memory(user_id,query,korean_query,results_json) VALUES(?,?,?,?)",
                (str(user_id), str(query)[:500], str(korean_query)[:500],
                 json.dumps(compact, ensure_ascii=False))
            )
            conn.execute("""DELETE FROM search_memory WHERE user_id=? AND id NOT IN
                (SELECT id FROM search_memory WHERE user_id=? ORDER BY id DESC LIMIT 100)""",
                (str(user_id), str(user_id)))
            conn.commit()
    except sqlite3.Error:
        logging.exception("Could not save search memory")


def get_search_memory_context(user_id, limit=8):
    try:
        with db() as conn:
            rows = conn.execute(
                "SELECT query,korean_query,results_json,created_at FROM search_memory "
                "WHERE user_id=? ORDER BY id DESC LIMIT ?", (str(user_id), limit)
            ).fetchall()
    except sqlite3.Error:
        logging.exception("Could not read search memory")
        return ""
    if not rows:
        return ""
    lines = ["СОХРАНЁННЫЕ ПОИСКИ ПОЛЬЗОВАТЕЛЯ:"]
    for query, ko, raw, created in reversed(rows):
        lines.append(f"- {created}: запрос «{query}»; поиск Kakao: {ko}")
        try:
            places = json.loads(raw or "[]")
        except (ValueError, TypeError):
            places = []
        for p in places[:5]:
            lines.append(f"  • {p.get('name')}; {p.get('address')}; {p.get('url','')}")
    lines.append("Не выдумывай сохранённые результаты. Если записи нет, скажи честно.")
    return "\n".join(lines)


def track_message(chat_id, message_id):
    try:
        with db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO chat_messages(chat_id,message_id) VALUES(?,?)",
                (str(chat_id), int(message_id))
            )
            conn.execute("""DELETE FROM chat_messages WHERE chat_id=? AND id NOT IN
                (SELECT id FROM chat_messages WHERE chat_id=? ORDER BY id DESC LIMIT 300)""",
                (str(chat_id), str(chat_id)))
            conn.commit()
    except sqlite3.Error:
        logging.exception("Could not track message")


class TrackingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, Message) and event.chat and event.message_id:
            track_message(event.chat.id, event.message_id)
        return await handler(event, data)


_original_send_message = Bot.send_message


async def _tracked_send_message(self, chat_id, text, *args, **kwargs):
    result = await _original_send_message(self, chat_id, text, *args, **kwargs)
    if result and getattr(result, "message_id", None):
        track_message(chat_id, result.message_id)
    return result


Bot.send_message = _tracked_send_message
dp.message.outer_middleware(TrackingMiddleware())


def cancel_user_search(user_id):
    uid = str(user_id)
    task = SEARCH_TASKS.get(uid)
    if task and not task.done():
        task.cancel()
    SEARCH_TASKS.pop(uid, None)


async def start_place_search(message, query, user_id, budget="any"):
    uid = str(user_id)
    cancel_user_search(uid)

    async def runner():
        current = asyncio.current_task()
        try:
            await run_place_search(message, query, user_id, budget)
        except asyncio.CancelledError:
            # Expected when the user starts another search.
            pass
        except Exception:
            logging.exception("Unhandled place-search error")
            try:
                await message.answer("⚠️ Во время поиска произошла ошибка. Попробуй ещё раз.")
            except Exception:
                pass
        finally:
            if SEARCH_TASKS.get(uid) is current:
                SEARCH_TASKS.pop(uid, None)

    task = asyncio.create_task(runner())
    SEARCH_TASKS[uid] = task


async def clear_chat(bot, chat_id):
    try:
        with db() as conn:
            ids = conn.execute(
                "SELECT message_id FROM chat_messages WHERE chat_id=? ORDER BY message_id DESC",
                (str(chat_id),)
            ).fetchall()
    except sqlite3.Error:
        ids = []
    deleted = failed = 0
    for (mid,) in ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=int(mid))
            deleted += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.04)
    try:
        with db() as conn:
            conn.execute("DELETE FROM chat_messages WHERE chat_id=?", (str(chat_id),))
            conn.commit()
    except sqlite3.Error:
        logging.exception("Could not reset message tracking")
    return deleted, failed


async def search_kakao(query):
    if not KAKAO_KEY:
        return None, "Поиск не настроен: отсутствует KAKAO_REST_API_KEY в Render."
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_KEY}"}
    results, seen = [], set()
    try:
        timeout = aiohttp.ClientTimeout(total=25)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for page in range(1, 4):
                async with session.get(
                    url, headers=headers,
                    params={"query": query, "size": 15, "page": page}
                ) as resp:
                    if resp.status == 401:
                        return None, "Kakao не принял ключ API. Проверь KAKAO_REST_API_KEY."
                    if resp.status == 403:
                        return None, "Kakao запретил запрос (HTTP 403). Проверь доступ к Local API."
                    if resp.status != 200:
                        logging.error("Kakao HTTP %s", resp.status)
                        return None, f"Ошибка поиска Kakao: HTTP {resp.status}."
                    data = await resp.json()
                for p in data.get("documents", []):
                    pid = str(p.get("id", "")) or (p.get("place_name"), p.get("address_name"))
                    if pid not in seen:
                        seen.add(pid)
                        results.append(p)
                if not data.get("documents") or data.get("meta", {}).get("is_end", True):
                    break
        return results, None
    except asyncio.CancelledError:
        raise
    except asyncio.TimeoutError:
        return None, "Поиск занял слишком много времени. Попробуй ещё раз."
    except aiohttp.ClientError:
        logging.exception("Kakao request failed")
        return None, "Не удалось связаться с Kakao. Попробуй позже."


def get_review_summary(place_id):
    try:
        with db() as conn:
            rows = conn.execute(
                "SELECT dimension,AVG(score),COUNT(*) FROM reviews "
                "WHERE place_id=? GROUP BY dimension", (str(place_id),)
            ).fetchall()
        return {r[0]: (float(r[1]), int(r[2])) for r in rows}
    except sqlite3.Error:
        logging.exception("Could not read reviews")
        return {}


def rating_dimensions_for_place(place):
    cat = normalize(str(place.get("category_name", "")) + " " + str(place.get("place_name", "")))
    if any(x in cat for x in ("카페", "음식점", "식당", "restaurant", "cafe")):
        keys = ("overall", "food", "speed", "service", "value", "atmosphere", "cleanliness")
    elif any(x in cat for x in ("병원", "의원", "치과", "약국", "clinic", "hospital")):
        keys = ("overall", "quality", "waiting", "service", "communication", "cleanliness", "value")
    else:
        keys = ("overall", "quality", "speed", "service", "value")
    return [(k, RATING_DIMENSIONS[k]) for k in keys]


def review_keyboard(place_id, place):
    dims = rating_dimensions_for_place(place)
    rows = [[InlineKeyboardButton(text=f"⭐ {label}", callback_data=f"rate:{place_id}:{key}")
             for key, label in dims[i:i+2]] for i in range(0, len(dims), 2)]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def score_keyboard(place_id, dimension):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{n} ⭐", callback_data=f"score:{place_id}:{dimension}:{n}") for n in range(1, 6)],
        [InlineKeyboardButton(text="↩️ Отмена", callback_data="rate:cancel:cancel")],
    ])


def describe_category(place):
    cat = (place.get("category_name", "") + " " + place.get("category_group_name", "")).lower()
    pairs = [
        ("pc방", "Компьютерный клуб"), ("찜질방", "Корейская баня / ччимчильбан"),
        ("사우나", "Сауна"), ("스파", "СПА"), ("렌터카", "Аренда автомобилей"),
        ("부동산", "Недвижимость"), ("장난감", "Игрушки"), ("병원", "Медицина"),
        ("의원", "Клиника"), ("치과", "Стоматология"), ("약국", "Аптека"),
        ("카페", "Кафе"), ("음식점", "Ресторан"), ("마트", "Магазин / супермаркет"),
        ("호텔", "Отель"), ("미용실", "Салон красоты"), ("동물병원", "Ветеринар"),
        ("자동차", "Автомобильные услуги"), ("관광", "Достопримечательность"),
    ]
    for key, label in pairs:
        if key in cat:
            return label
    return place.get("category_name") or place.get("category_group_name") or "Категория не указана"


def price_label(pref):
    return {
        "cheap": "самый дешёвый вариант", "mid": "средний бюджет",
        "premium": "дорогой / премиум", "any": "любой бюджет"
    }.get(pref, "не указан")


def budget_search_terms(query, pref):
    q = normalize(query)
    city = find_city(query) or ""
    ko = translate_query(query)
    if pref == "cheap":
        if any(x in q for x in ("игруш", "toy")):
            return [f"저렴한 장난감 가게 {city}".strip(), f"장난감 가게 {city}".strip()]
        if any(x in q for x in ("аренд", "прокат", "машин", "авто", "rent", "car")):
            return [f"저렴한 렌터카 {city}".strip(), f"렌터카 {city}".strip()]
    elif pref == "premium":
        if any(x in q for x in ("игруш", "toy")):
            return [f"고급 장난감 매장 {city}".strip(), f"장난감 가게 {city}".strip()]
        if any(x in q for x in ("аренд", "прокат", "машин", "авто", "rent", "car")):
            return [f"고급 렌터카 {city}".strip(), f"렌터카 {city}".strip()]
    return [ko]


def build_search_queries(query, budget):
    """Build several focused Korean keywords; Kakao keyword search works best with concise terms."""
    city = find_city(query) or ""
    qnorm = normalize(query)

    if any(word in qnorm for word in ("응급", "скорая", "неотлож", "экстренн")):
        terms = EMERGENCY_QUERIES[:3]
    elif any(word in qnorm for word in ("медицин", "больниц", "клиник", "аптек", "стомат", "врач", "병원", "의원")):
        terms = MEDICAL_QUERIES[:8]
    elif any(word in qnorm for word in ("кафе", "кофейн", "ресторан", "음식점", "카페")):
        terms = ["카페", "음식점", "식당"]
    elif any(word in qnorm for word in ("автосервис", "автозапчаст", "запчаст", "авто и запчасти", "자동차 정비", "자동차 부품")):
        terms = ["자동차 정비소", "자동차 수리", "자동차 부품"]
    elif any(word in qnorm for word in ("магазин", "магазины", "супермаркет", "마트")):
        terms = ["마트", "매장", "슈퍼마켓"]
    elif any(word in qnorm for word in ("отель", "гостиниц", "호텔")):
        terms = ["호텔", "모텔", "게스트하우스"]
    elif any(word in qnorm for word in ("салон красоты", "парикмах", "красоты", "미용실")):
        terms = ["미용실", "헤어샵", "네일샵"]
    elif any(word in qnorm for word in ("аренд", "прокат", "렌터카")):
        terms = budget_search_terms(query, budget)
        return list(dict.fromkeys(terms))
    else:
        terms = budget_search_terms(query, budget)
        # Keep the original translated query as a fallback, but avoid duplicate requests.
        return list(dict.fromkeys(q for q in terms if q.strip()))

    queries = [f"{term} {city}".strip() for term in terms]
    return list(dict.fromkeys(q for q in queries if q.strip()))


AI_INSTRUCTIONS = (
    "Ты — ИИ-помощник TrustMap Korea для жизни в Южной Корее. Отвечай на языке пользователя. "
    "Используй контекст переписки, исправляй очевидные опечатки. Не выдумывай адреса, цены, "
    "рейтинги, часы работы, законы или официальные правила. Отличай пользовательские оценки "
    "TrustMap от официальных рейтингов. Для медицинских, юридических и иммиграционных тем отвечай осторожно. "
    "При угрозе жизни в Южной Корее укажи, что номер экстренной помощи — 119."
)


async def ask_ai(question, user_id):
    if not OPENAI_KEY:
        return "🤖 ИИ не подключён: проверь OPENAI_API_KEY в Render."
    history = CONVERSATION_HISTORY.setdefault(str(user_id), [])
    instructions = AI_INSTRUCTIONS
    memory = get_search_memory_context(user_id)
    if memory:
        instructions += "\n\n" + memory
    payload = {
        "model": AI_MODEL, "instructions": instructions,
        "input": history[-MAX_HISTORY_MESSAGES:] + [{"role": "user", "content": question}],
        "max_output_tokens": 1000, "store": False
    }
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
            async with session.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
                json=payload
            ) as resp:
                if resp.status == 401:
                    return "OpenAI не принял API-ключ. Проверь OPENAI_API_KEY в Render."
                if resp.status == 429:
                    return "ИИ временно недоступен: проверь лимиты и оплату OpenAI API."
                if resp.status != 200:
                    logging.error("OpenAI HTTP %s: %s", resp.status, (await resp.text())[:300])
                    return f"Ошибка ИИ-сервиса: HTTP {resp.status}."
                data = await resp.json()
        answer = "\n".join(
            c.get("text", "") for item in data.get("output", [])
            if item.get("type") == "message"
            for c in item.get("content", []) if c.get("type") == "output_text"
        ).strip()
        if not answer:
            return "ИИ не вернул ответ. Попробуй задать вопрос иначе."
        history.extend([{"role": "user", "content": question}, {"role": "assistant", "content": answer}])
        CONVERSATION_HISTORY[str(user_id)] = history[-MAX_HISTORY_MESSAGES:]
        return answer
    except asyncio.TimeoutError:
        return "ИИ отвечает слишком долго. Попробуй ещё раз."
    except aiohttp.ClientError:
        logging.exception("OpenAI request failed")
        return "Не удалось подключиться к ИИ. Попробуй позже."


async def send_long(message, text):
    for i in range(0, len(text), 3500):
        await message.answer(text[i:i+3500])


async def run_place_search(message, query, user_id, budget="any"):
    city_ko = find_city(query)
    search_queries = build_search_queries(query, budget)
    await message.answer("🔎 Ищу места...")

    places, seen, used = [], set(), []
    current_task = asyncio.current_task()

    for search_query in search_queries:
        if current_task and current_task.cancelling():
            raise asyncio.CancelledError
        found, error = await search_kakao(search_query)
        if current_task and current_task.cancelling():
            raise asyncio.CancelledError
        if error:
            await message.answer(error)
            return
        used.append(search_query)
        for p in found or []:
            pid = str(p.get("id", "")) or (p.get("place_name"), p.get("address_name"))
            if pid not in seen:
                seen.add(pid)
                places.append(p)
        if len(places) >= 30:
            break

    save_search_memory(user_id, query, " | ".join(used), places)

    if not places:
        location = CITY_LABELS.get(city_ko, city_ko) if city_ko else "Южной Корее"
        await message.answer(
            f"😔 По запросу «{query}» в {location} Kakao не вернул результатов.\n"
            "Это не означает, что таких мест нет: попробуй более короткий запрос или другой город.",
            reply_markup=make_keyboard()
        )
        return

    for i, p in enumerate(places[:30], 1):
        if current_task and current_task.cancelling():
            raise asyncio.CancelledError
        pid = str(p.get("id", ""))
        summary = get_review_summary(pid) if pid else {}
        overall = summary.get("overall")
        caption = (
            f"🇰🇷 TRUSTMAP KOREA · МЕСТО №{i}\n\n"
            f"🏢 {p.get('place_name', 'Название не указано')}\n"
            f"🏷️ {describe_category(p)}\n"
            f"📍 {p.get('road_address_name') or p.get('address_name') or 'Адрес не указан'}\n"
            f"☎️ {p.get('phone') or 'Телефон не указан'}\n"
        )
        if p.get("place_url"):
            caption += f"🗺️ Карта: {p['place_url']}\n"
        if overall:
            caption += f"💙 Общая оценка TrustMap: {overall[0]:.1f}/5 · {overall[1]} оценок\n"
        else:
            caption += "💙 Общая оценка TrustMap: пока нет оценок\n"
        for dim, (avg, count) in summary.items():
            if dim != "overall":
                caption += f"  • {RATING_DIMENSIONS.get(dim, dim)}: {avg:.1f}/5 ({count})\n"
        caption += f"\n💰 Предпочтение по цене: {price_label(budget)}."
        caption += "\nℹ️ Цена не подтверждена Kakao; уточни её у заведения."
        await message.answer(caption, reply_markup=review_keyboard(pid, p) if pid else None)

    await message.answer(
        "💙 Средние оценки TrustMap общие для всех пользователей. "
        "Каждый пользователь может изменить свою оценку.",
        reply_markup=make_keyboard()
    )


def feedback_kind_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="😍 Что нравится", callback_data="feedback:like")],
        [InlineKeyboardButton(text="🙁 Что не нравится", callback_data="feedback:dislike")],
        [InlineKeyboardButton(text="💡 Идея / предложение", callback_data="feedback:idea")],
        [InlineKeyboardButton(text="🐞 Ошибка в боте", callback_data="feedback:bug")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="feedback:cancel")],
    ])


FEEDBACK_LABELS = {
    "like": "Что нравится", "dislike": "Что не нравится",
    "idea": "Идея / предложение", "bug": "Ошибка в боте",
}


@dp.callback_query(F.data.startswith("feedback:"))
async def feedback_callback(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    choice = (callback.data or "").split(":", 1)[1]
    if choice == "cancel":
        USER_FLOWS.pop(user_id, None)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer("Отменено")
        return
    if choice not in FEEDBACK_LABELS:
        await callback.answer("Неизвестный вариант.", show_alert=True)
        return
    USER_FLOWS[user_id] = {"kind": "feedback", "stage": "message", "values": {"type": choice}}
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"✍️ Напиши одним сообщением: {FEEDBACK_LABELS[choice].lower()}.\n"
        "Можно написать подробно. Не отправляй пароли, номера документов или банковские данные."
    )
    await callback.answer()


@dp.message(Command("myid"))
async def my_id_command(message: Message):
    await message.answer(
        f"Твой Telegram ID: {message.from_user.id}\n"
        "Чтобы получать отзывы в личный Telegram, добавь это число в Render как переменную ADMIN_TELEGRAM_ID."
    )


@dp.message(Command("feedbacks"))
async def owner_feedbacks(message: Message):
    if not ADMIN_TELEGRAM_ID or str(message.from_user.id) != ADMIN_TELEGRAM_ID:
        await message.answer("Эта команда доступна только администратору бота.")
        return
    try:
        with db() as conn:
            rows = conn.execute(
                "SELECT id, user_id, username, feedback_type, message, created_at "
                "FROM bot_feedback ORDER BY id DESC LIMIT 30"
            ).fetchall()
    except sqlite3.Error:
        logging.exception("Could not read bot feedback")
        await message.answer("Не удалось прочитать отзывы из базы данных.")
        return
    if not rows:
        await message.answer("Пока отзывов о боте нет.")
        return
    chunks, current = [], "💬 ПОСЛЕДНИЕ ОТЗЫВЫ TRUSTMAP KOREA\n\n"
    for rid, uid, username, kind, body, created in rows:
        uname = f"@{username}" if username else "не указан"
        item = f"#{rid} · {created}\nТип: {FEEDBACK_LABELS.get(kind, kind)}\nПользователь: {uname} (ID {uid})\n{body}\n\n━━━━━━━━━━━━\n\n"
        if len(current) + len(item) > 3500:
            chunks.append(current)
            current = ""
        current += item
    if current:
        chunks.append(current)
    for chunk in chunks:
        await message.answer(chunk)


@dp.message(CommandStart())
async def start(message: Message):
    cancel_user_search(message.from_user.id)
    USER_FLOWS.pop(str(message.from_user.id), None)
    await message.answer(
        "🇰🇷 TRUSTMAP KOREA\n\nПомощник для жизни в Южной Корее.\n"
        "Ищи места, магазины игрушек, аренду авто, медицину, жильё и услуги.\n"
        "Можно искать в конкретном городе или попробовать поиск по Корее.\n"
        "Оценки пользователей объединяются в общий рейтинг.\n\n"
        "Пример: «нужны недорогие игрушки в Чхонане».",
        reply_markup=make_keyboard()
    )


@dp.message(Command("help"))
async def help_command(message: Message):
    cancel_user_search(message.from_user.id)
    await message.answer(
        "Примеры запросов:\n• кафе в Чхонане\n• недорогие игрушки в Сеуле\n"
        "• аренда машины в Пусане\n• аптека в Инчхоне\n• больница в Чхонане\n"
        "• /ai Как сказать спасибо по-корейски?\n\n"
        "Для экстренной помощи в Корее звони 119.\n"
        "Оценки TrustMap — оценки пользователей, не официальный рейтинг."
    )


@dp.message(Command("ai"))
async def ai_command(message: Message):
    cancel_user_search(message.from_user.id)
    USER_FLOWS.pop(str(message.from_user.id), None)
    question = (message.text or "").partition(" ")[2].strip()
    if not question:
        await message.answer("Напиши вопрос после /ai.")
        return
    await message.answer("🤖 ИИ готовит ответ…")
    await send_long(message, await ask_ai(question, message.from_user.id))


@dp.callback_query(F.data.startswith("budget:"))
async def budget_callback(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    cancel_user_search(user_id)
    flow = USER_FLOWS.get(user_id)
    if not flow or flow.get("kind") != "search" or flow.get("stage") != "budget":
        await callback.answer("Этот выбор уже не активен. Начни поиск заново.", show_alert=True)
        return
    pref = (callback.data or "").split(":", 1)[1]
    flow["values"]["budget"] = pref
    flow["stage"] = "city"
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("📍 Выбери город или поиск по Корее:", reply_markup=city_keyboard())
    await callback.answer("Предпочтение сохранено")


@dp.callback_query(F.data.startswith("city:"))
async def city_callback(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    cancel_user_search(user_id)
    choice = (callback.data or "").split(":", 1)[1]
    flow = USER_FLOWS.get(user_id)

    if choice == "cancel":
        USER_FLOWS.pop(user_id, None)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer("Поиск отменён")
        return

    if choice == "other":
        if flow:
            flow["allow_custom_city"] = True
        await callback.message.answer("✍️ Напиши город сообщением (например, Чхонан или Сеул).")
        await callback.answer()
        return

    if choice == "nationwide":
        if not flow:
            await callback.answer("Сначала выбери категорию или напиши запрос.", show_alert=True)
            return
        query = flow.get("values", {}).get("query", "")
        budget = flow.get("values", {}).get("budget", "any")
        USER_FLOWS.pop(user_id, None)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer("Поиск по Корее")
        await start_place_search(callback.message, query, user_id, budget)
        return

    city_ko = CITY_CALLBACKS.get(choice)
    if not city_ko:
        await callback.answer("Не удалось определить город.", show_alert=True)
        return
    if not flow or flow.get("stage") != "city":
        await callback.answer("Этот выбор города уже не активен. Напиши запрос заново.", show_alert=True)
        return
    query = flow.get("values", {}).get("query", "")
    budget = flow.get("values", {}).get("budget", "any")
    USER_FLOWS.pop(user_id, None)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer(f"Город: {CITY_LABELS.get(city_ko, city_ko)}")
    await start_place_search(callback.message, f"{query} {city_ko}", user_id, budget)


@dp.callback_query(F.data.startswith("rate:"))
async def rating_callback(callback: CallbackQuery):
    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer("Некорректная кнопка.", show_alert=True)
        return
    _, pid, dim = parts
    if pid == "cancel":
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer("Отменено")
        return
    if dim not in RATING_DIMENSIONS:
        await callback.answer("Этот показатель недоступен.", show_alert=True)
        return
    await callback.message.answer(
        f"💙 Оцени: {RATING_DIMENSIONS[dim]}\n1 ⭐ — очень плохо · 2 ⭐ — плохо · "
        "3 ⭐ — нормально · 4 ⭐ — хорошо · 5 ⭐ — отлично",
        reply_markup=score_keyboard(pid, dim)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("score:"))
async def score_callback(callback: CallbackQuery):
    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        await callback.answer("Некорректная оценка.", show_alert=True)
        return
    _, pid, dim, raw_score = parts
    try:
        score = int(raw_score)
    except ValueError:
        await callback.answer("Некорректная оценка.", show_alert=True)
        return
    if dim not in RATING_DIMENSIONS or score not in range(1, 6):
        await callback.answer("Некорректная оценка.", show_alert=True)
        return
    try:
        with db() as conn:
            conn.execute("""INSERT INTO reviews(place_id,place_name,user_id,dimension,score)
                VALUES(?,?,?,?,?) ON CONFLICT(place_id,user_id,dimension)
                DO UPDATE SET score=excluded.score,created_at=CURRENT_TIMESTAMP""",
                (pid, "Место Kakao ID " + pid, str(callback.from_user.id), dim, score))
            conn.commit()
        summary = get_review_summary(pid).get(dim)
        await callback.message.edit_reply_markup(reply_markup=None)
        if summary:
            await callback.message.answer(
                f"💙 Спасибо! Общая оценка «{RATING_DIMENSIONS[dim]}»: "
                f"{summary[0]:.1f}/5 на основе {summary[1]} оценок. "
                "Этот средний балл виден всем пользователям."
            )
        else:
            await callback.message.answer("💙 Спасибо! Оценка сохранена.")
        await callback.answer("Оценка сохранена")
    except sqlite3.Error:
        logging.exception("Could not save rating")
        await callback.answer("Не удалось сохранить оценку. Попробуй позже.", show_alert=True)


def looks_like_ai(text):
    q = normalize(text)
    if q.startswith("/ai"):
        return True
    if any(q.startswith(s) for s in AI_STARTS):
        return True
    if any(s in q for s in AI_PHRASES):
        return True
    return "?" in q and any(w in q for w in ("как", "почему", "что", "можно", "how", "why", "what"))


@dp.message()
async def handle_message(message: Message):
    text = (message.text or "").strip()
    if not text:
        return
    uid = str(message.from_user.id)
    q = normalize(text)

    # Any new user message cancels their currently running place search.
    cancel_user_search(uid)

    if text == "🧹 Очистить чат":
        CONVERSATION_HISTORY.pop(uid, None)
        USER_FLOWS.pop(uid, None)
        deleted, failed = await clear_chat(message.bot, message.chat.id)
        extra = f"\nTelegram не разрешил удалить {failed} сообщений." if failed else ""
        await message.answer(
            f"🧹 Начинаем заново. Удалено сообщений: {deleted}.{extra}\n"
            "Общие оценки заведений сохранены. История поиска для памяти тоже сохранена.\n"
            "Напиши новый запрос или выбери категорию.",
            reply_markup=make_keyboard()
        )
        return

    if text == "🤖 ИИ-помощник":
        USER_FLOWS.pop(uid, None)
        await message.answer("🤖 Напиши любой вопрос обычным сообщением.")
        return

    if text == "🌐 Язык / Language":
        USER_FLOWS.pop(uid, None)
        await message.answer("🌐 Пиши по-русски, по-английски или по-корейски. Я отвечу на языке сообщения.")
        return

    if text == "💬 Отзыв о боте" or q == "/feedback":
        USER_FLOWS[uid] = {"kind": "feedback_select", "stage": "type", "values": {}}
        await message.answer("💬 Помоги сделать TrustMap Korea лучше. Что хочешь сообщить?", reply_markup=feedback_kind_keyboard())
        return

    flow_now = USER_FLOWS.get(uid)
    if flow_now and flow_now.get("kind") == "feedback" and flow_now.get("stage") == "message":
        body = text.strip()
        if len(body) < 3:
            await message.answer("Напиши, пожалуйста, чуть подробнее (минимум 3 символа).")
            return
        kind = flow_now.get("values", {}).get("type", "idea")
        username = message.from_user.username or None
        try:
            with db() as conn:
                cur = conn.execute(
                    "INSERT INTO bot_feedback(user_id,username,language_code,feedback_type,message) VALUES(?,?,?,?,?)",
                    (uid, username, getattr(message.from_user, "language_code", None), kind, body[:4000])
                )
                feedback_id = cur.lastrowid
                conn.commit()
        except sqlite3.Error:
            logging.exception("Could not save bot feedback")
            await message.answer("Не удалось сохранить отзыв. Попробуй ещё раз позже.", reply_markup=make_keyboard())
            USER_FLOWS.pop(uid, None)
            return
        USER_FLOWS.pop(uid, None)
        await message.answer("💙 Спасибо! Отзыв сохранён. Он поможет сделать TrustMap Korea лучше.", reply_markup=make_keyboard())
        if ADMIN_TELEGRAM_ID:
            try:
                await message.bot.send_message(
                    int(ADMIN_TELEGRAM_ID),
                    f"💬 НОВЫЙ ОТЗЫВ TRUSTMAP KOREA #{feedback_id}\n"
                    f"Тип: {FEEDBACK_LABELS.get(kind, kind)}\n"
                    f"Пользователь: @{username or 'без username'} (ID {uid})\n"
                    f"Язык Telegram: {getattr(message.from_user, 'language_code', None) or 'не указан'}\n\n{body[:3500]}\n\n"
                    "Читать сохранённые отзывы: /feedbacks"
                )
            except Exception:
                logging.exception("Could not notify bot owner about feedback")
        return

    if text in [item for row in CATEGORIES for item in row]:
        USER_FLOWS.pop(uid, None)
        category_queries = {
            "🔎 Поиск мест": None,
            "🏥 Медицина": "медицинские учреждения",
            "🍽️ Кафе и рестораны": "кафе или ресторан",
            "🛍️ Магазины": "магазин",
            "🚗 Авто и запчасти": "автосервис или автозапчасти",
            "🚙 Аренда машины": "аренда машины",
            "🏠 Недвижимость": "агентства недвижимости",
            "💼 Работа": "агентства по трудоустройству",
            "💄 Красота и уход": "салон красоты",
            "👶 Товары для детей": "детские товары",
            "🧸 Игрушки": "магазин игрушек",
            "🐾 Товары для животных": "зоомагазин",
            "🔧 Бытовые услуги": "бытовые услуги",
            "🏨 Отели": "отель",
            "📍 Достопримечательности": "достопримечательности",
            "💰 Сравнение цен": None,
            "🧖 Бани и сауны": "бани и сауны",
            "🎮 Компьютерные клубы": "компьютерные клубы",
        }
        preset = category_queries.get(text)
        if preset:
            if text in ("🧸 Игрушки", "🚙 Аренда машины"):
                USER_FLOWS[uid] = {
                    "kind": "search", "stage": "budget",
                    "values": {"query": preset, "budget": "any"}
                }
                await message.answer(
                    f"{text}\n\n💰 Какой ценовой вариант предпочитаешь?",
                    reply_markup=preference_keyboard()
                )
            else:
                USER_FLOWS[uid] = {
                    "kind": "search", "stage": "city",
                    "values": {"query": preset, "budget": "any"}
                }
                await message.answer(
                    f"{text}\n\n📍 Выбери город или поиск по всей Корее:",
                    reply_markup=city_keyboard()
                )
        else:
            await message.answer("Напиши, что именно ищем. Например: «недорогие игрушки в Чхонане».")
        return

    flow = USER_FLOWS.get(uid)
    if flow and flow.get("stage") == "city":
        city_ko = find_city(text)
        if not city_ko and flow.get("allow_custom_city"):
            city_ko = text.strip()
        if city_ko:
            query = flow.get("values", {}).get("query", "")
            budget = flow.get("values", {}).get("budget", "any")
            USER_FLOWS.pop(uid, None)
            await start_place_search(message, f"{query} {city_ko}", uid, budget)
            return
        if is_place_search(text):
            USER_FLOWS.pop(uid, None)
        else:
            await message.answer(
                "Не распознал город. Выбери его кнопкой, нажми «Другой город» "
                "или «Искать по Корее».",
                reply_markup=city_keyboard()
            )
            return

    if any(x in q for x in (
        "помнишь", "что я искал раньше", "что я искала раньше",
        "предыдущий поиск", "мой прошлый поиск"
    )):
        memory = get_search_memory_context(uid)
        if not memory:
            await message.answer("🧠 Пока нет сохранённых поисков. Сначала найди место через TrustMap.")
        else:
            await message.answer("🧠 Проверяю сохранённые поиски…")
            await send_long(message, await ask_ai(text, message.from_user.id))
        return

    if looks_like_ai(text):
        USER_FLOWS.pop(uid, None)
        await message.answer("🤖 ИИ готовит ответ…")
        await send_long(message, await ask_ai(text, message.from_user.id))
        return

    if is_place_search(text) or any(
        term in q for term in ("медицинские учреждения", "больница", "аптека", "клиника", "скорая помощь")
    ):
        USER_FLOWS.pop(uid, None)
        needs_budget = any(x in q for x in (
            "игруш", "toy", "аренд", "прокат машин", "аренда авто", "аренда машины", "렌터카"
        ))
        budget = "any"
        if needs_budget and not any(x in q for x in (
            "дешев", "недорог", "дорог", "премиум", "cheap", "premium"
        )):
            USER_FLOWS[uid] = {
                "kind": "search", "stage": "budget", "values": {"query": text, "budget": "any"}
            }
            await message.answer("💰 Какой ценовой вариант предпочитаешь?", reply_markup=preference_keyboard())
            return
        if any(x in q for x in ("дешев", "недорог", "cheap")):
            budget = "cheap"
        elif any(x in q for x in ("дорог", "премиум", "premium", "люкс")):
            budget = "premium"
        elif any(x in q for x in ("средний бюджет", "средняя цена")):
            budget = "mid"

        # City is optional. If omitted, use Kakao's broader keyword search.
        await start_place_search(message, text, uid, budget)
        return

    USER_FLOWS.pop(uid, None)
    await message.answer("🤖 Передаю сообщение ИИ-помощнику…")
    await send_long(message, await ask_ai(text, message.from_user.id))


async def main():
    if not TOKEN:
        raise RuntimeError("Не задан TELEGRAM_BOT_TOKEN в переменных окружения.")
    init_db()
    bot = Bot(token=TOKEN)
    try:
        await dp.start_polling(bot)
    finally:
        # Stop any remaining background searches cleanly.
        for task in list(SEARCH_TASKS.values()):
            if not task.done():
                task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
