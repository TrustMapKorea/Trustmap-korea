import os
import re
import json
import asyncio
import logging
import sqlite3
from contextlib import closing
from difflib import SequenceMatcher
from urllib.parse import quote_plus

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
# Telegram callback_data is limited to 64 bytes. Place IDs are kept in a short-lived
# per-user cache; callbacks contain only the cache index.
PLACE_RESULTS = {}
JOB_RESULTS = {}
MAX_PLACE_RESULTS_PER_USER = 30

# Curated photo spots inspired by publicly visible posts from the Instagram accounts
# named by the bot owner. Recheck the venue/address before travelling; availability may change.
PHOTO_SPOTS = {
    "pins": {
        "name": "Pins Coffee · 핀스커피",
        "city": "Чхонан",
        "address": "충남 천안시 동남구 해솔1길 27-29",
        "vibe": "Сезонный сад и фотозоны; особенно красиво в сезон цветения.",
        "source": "@_yh.yhh",
        "map_query": "핀스커피 천안",
    },
    "river": {
        "name": "River Nine · 리버나인",
        "city": "Намъянджу",
        "address": "경기 남양주시 화도읍 북한강로 1630-18",
        "vibe": "Вид на реку Пукханган и просторная зелёная территория.",
        "source": "@_yh.yhh",
        "map_query": "리버나인 남양주",
    },
    "seaer": {
        "name": "Seaer Pool Villa · 시어풀빌라",
        "city": "Кёнджу",
        "address": "경북 경주시 감포읍 감포로2길 54-3",
        "vibe": "Морские виды и необычный интерьер. Это жильё: уточни правила посещения и бронирования.",
        "source": "@_yh.yhh",
        "map_query": "시어풀빌라 경주",
    },
    "rainbow": {
        "name": "Rainbow Pension Espresso · 무지개펜션에스프레소",
        "city": "Кодже",
        "address": "경남 거제시 남부면 거제남서로 737",
        "vibe": "Кафе с видом на побережье и панорамными окнами.",
        "source": "@_yh.yhh",
        "map_query": "무지개펜션에스프레소 거제",
    },
    "portrait": {
        "name": "Portrait Coffee Bar",
        "city": "Сеул · Мангвон-дон",
        "address": "서울 마포구 포은로8길 32 1층",
        "vibe": "Небольшое кафе с фотогеничным интерьером; подходит для фото за чашкой кофе.",
        "source": "@my_season___",
        "map_query": "Portrait Coffee Bar 망원동",
    },
}

CATEGORIES = [
    ["🔎 Поиск мест", "🏥 Медицина"],
    ["🍽️ Кафе и рестораны", "🛍️ Магазины"],
    ["🏪 Сети магазинов", "💊 Круглосуточные аптеки"],
    ["👘 Ханбок и традиционная одежда", "💬 Сообщество"],
    ["🚗 Авто и запчасти", "🚙 Аренда машины"],
    ["🏠 Недвижимость", "💼 Работа"],
    ["💄 Красота и уход", "👶 Товары для детей"],
    ["🧸 Игрушки", "🐾 Товары для животных"],
    ["🔧 Бытовые услуги", "🏨 Отели"],
    ["📍 Достопримечательности", "📸 Места для фото"],
    ["💰 Сравнение цен", "🧖 Бани и сауны"],
    ["🎮 Компьютерные клубы", "🤖 ИИ-помощник"],
    ["🌐 Язык / Language", "💬 Отзыв о боте"],
    ["⬅️ Назад в меню", "🧹 Очистить чат"],
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
    "daegu": "대구", "daejeon": "대전", "suwon": "수원",
    "pyeongtaek": "평택", "seongnam": "성남", "gwangju": "광주",
}
TERMS = {
    "кафе": "카페", "кофейня": "카페", "кофейни": "카페", "кофе": "카페",
    "ресторан": "음식점", "рестораны": "음식점", "еда": "음식점",
    "бар": "바", "бары": "바", "паб": "펍", "караоке": "노래방",
    "больница": "병원", "больницы": "병원", "клиника": "의원", "клиники": "의원",
    "стоматолог": "치과", "стоматология": "치과", "аптека": "약국", "аптеки": "약국",
    "магазин": "매장", "магазины": "매장", "супермаркет": "마트", "супермаркеты": "마트",
    "магазин одежды": "의류 매장", "одежда": "의류 매장", "женская одежда": "여성 의류",
    "мужская одежда": "남성 의류", "детская одежда": "아동복", "детский магазин": "아동용품점",
    "детские товары": "유아용품", "игрушка": "장난감", "игрушки": "장난감",
    "магазин игрушек": "장난감 가게", "магазины игрушек": "장난감 가게",
    "автосервис": "자동차 정비소", "сто": "자동차 정비소", "автозапчасти": "자동차 부품",
    "запчасти": "자동차 부품", "аренда машины": "렌터카", "аренду машины": "렌터카",
    "аренда авто": "렌터카", "аренда автомобиля": "렌터카", "аренду автомобиля": "렌터카",
    "прокат машин": "렌터카", "прокат автомобиля": "렌터카", "машина напрокат": "렌터카",
    "аренда квартиры": "부동산", "аренда жилья": "부동산", "снять квартиру": "부동산",
    "недвижимость": "부동산", "работа": "일자리", "вакансии": "일자리",
    "парикмахерская": "미용실", "салон красоты": "미용실", "отель": "호텔", "гостиница": "호텔",
    "ветеринар": "동물병원", "зоомагазин": "반려동물용품", "достопримечательности": "관광명소",
    "электроника": "전자제품", "спортивный магазин": "스포츠용품", "прачечная": "세탁소",
    "уборка": "청소 서비스", "сантехник": "배관", "парк": "공원", "парки": "공원",
    "музей": "박물관", "бассейн": "수영장", "спортзал": "헬스장", "баня": "찜질방",
    "бани": "찜질방", "сауна": "사우나", "сауны": "사우나", "спа": "스파",
    "компьютерный клуб": "PC방", "компьютерные клубы": "PC방", "пк клуб": "PC방",
}
STOPWORDS = {
    "в", "во", "на", "по", "для", "у", "около", "рядом", "мне", "найти", "найди",
    "покажи", "ищу", "нужен", "нужна", "нужно", "есть", "самый", "самая", "самое",
    "дешевый", "дешевая", "недорогой", "недорогая", "лучший", "лучшая", "лучшие", "the",
    "in", "near", "find", "show", "please", "городе", "город", "корее", "южной", "машину",
    "машины", "или", "ли", "and", "or", "авто", "автомобиль", "аренда", "аренду", "прокат",
    "хочу", "купить", "пожалуйста", "работа", "вакансии", "ищу", "найти",
}
PLACE_HINTS = set(TERMS.keys()) | {
    "игрушки", "игрушка", "магазин игрушек", "детские товары",
    "компьютерные клубы", "бани", "сауны"
}
AI_STARTS = (
    "как ", "почему ", "что ", "кто ", "когда ", "зачем ", "можно ли ", "помоги ",
    "объясни ", "переведи ", "посоветуй ", "how ", "why ", "what ", "who ", "when ",
    "help ", "translate ", "explain ",
)
AI_PHRASES = (
    "как сказать", "что значит", "переведи на корейский", "переведи на русский",
    "объясни мне", "помоги мне", "как правильно", "что делать если",
    "как работает", "can you help", "translate into korean", "what does it mean",
)
RATING_DIMENSIONS = {
    "overall": "Общая оценка", "quality": "Качество товара / услуги", "food": "Вкус еды",
    "speed": "Скорость обслуживания / выполнения", "waiting": "Время ожидания",
    "service": "Обслуживание и вежливость", "value": "Цена / качество",
    "atmosphere": "Атмосфера и комфорт", "cleanliness": "Чистота",
    "communication": "Общение и объяснения",
}
MEDICAL_QUERIES = [
    "병원", "종합병원", "대학병원", "의원", "내과", "소아과", "치과",
    "약국", "응급실", "이비인후과", "안과", "피부과"
]
EMERGENCY_QUERIES = ["응급실", "응급의료기관", "119안전센터"]

# Typical Korean housing types and their search keywords.
HOUSING_TYPES = {
    "housing:apartment": ("🏢 Апартаменты / 아파트", "아파트"),
    "housing:villa": ("🏘️ Вилла / 빌라", "빌라"),
    "housing:studio": ("🚪 Студия / 원룸", "원룸"),
    "housing:two": ("🏠 Две комнаты / 투룸", "투룸"),
    "housing:officetel": ("🏙️ Офистель / 오피스텔", "오피스텔"),
    "housing:house": ("🏡 Дом / 단독주택", "단독주택"),
    "housing:any": ("🔎 Любой тип жилья", "부동산"),
}
HOUSING_DEALS = {
    "deal:monthly": ("월세 — ежемесячная аренда", "monthly"),
    "deal:jeonse": ("전세 — чонсе, крупный залог", "jeonse"),
    "deal:sale": ("매매 — покупка", "sale"),
    "deal:any": ("🔎 Любой вариант", "any"),
}
MONTHLY_PRESETS = [
    ("До 300 000 ₩", 300000), ("До 400 000 ₩", 400000),
    ("До 500 000 ₩", 500000), ("До 600 000 ₩", 600000),
    ("До 700 000 ₩", 700000), ("До 1 000 000 ₩", 1000000),
]
DEPOSIT_PRESETS = [
    ("Без залога", 0), ("До 1 млн ₩", 1000000), ("До 3 млн ₩", 3000000),
    ("До 5 млн ₩", 5000000), ("До 10 млн ₩", 10000000),
    ("До 20 млн ₩", 20000000),
]


def db():
    return closing(sqlite3.connect(DATABASE_PATH, timeout=20))


def init_db():
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT, place_id TEXT NOT NULL, place_name TEXT NOT NULL,
            user_id TEXT NOT NULL, dimension TEXT NOT NULL, score INTEGER NOT NULL CHECK(score BETWEEN 1 AND 5),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(place_id,user_id,dimension))""")
        conn.execute("""CREATE TABLE IF NOT EXISTS search_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, query TEXT NOT NULL,
            korean_query TEXT NOT NULL, results_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT NOT NULL, message_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(chat_id,message_id))""")
        conn.execute("""CREATE TABLE IF NOT EXISTS bot_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, username TEXT,
            language_code TEXT, feedback_type TEXT NOT NULL, message TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS community_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, username TEXT,
            message TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS user_job_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, username TEXT,
            message TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
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


def is_job_query(text):
    q = normalize(text)
    terms = ("ваканс", "работ", "подработ", "трудоустрой", "зарплат", "работник",
             "работу", "работать", "일자리", "구인", "채용", "아르바이트", "알바")
    return any(term in q for term in terms) or q == "💼 работа"


def is_place_search(text):
    q = normalize(text)
    if any(x in q for x in ("сколько стоит", "что значит", "как сказать", "переведи", "почему", "объясни")):
        return False
    if is_job_query(text):
        return False
    return any(hint in q for hint in PLACE_HINTS) or (
        bool(find_city(q)) and any(w in q for w in ("найди", "найти", "покажи", "поиск", "find", "show", "search"))
    )


def make_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=x) for x in row] for row in CATEGORIES],
        resize_keyboard=True
    )


def city_keyboard():
    items = [
        ("📍 Чхонан", "cheonan"), ("🏙️ Сеул", "seoul"), ("🌊 Пусан", "busan"),
        ("✈️ Инчхон", "incheon"), ("🌆 Тэгу", "daegu"), ("🏙️ Тэджон", "daejeon"),
        ("🏘️ Сувон", "suwon"), ("📍 Пхёнтхэк", "pyeongtaek"),
        ("🏙️ Соннам", "seongnam"), ("📍 Кванджу", "gwangju")
    ]
    rows = [[InlineKeyboardButton(text=t, callback_data=f"city:{k}") for t, k in items[i:i+2]]
            for i in range(0, len(items), 2)]
    rows += [
        [InlineKeyboardButton(text="✍️ Другой город", callback_data="city:other")],
        [InlineKeyboardButton(text="🌏 Искать по Корее", callback_data="city:nationwide")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="city:cancel")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def preference_keyboard():
    options = [
        ("💸 Самый дешёвый", "cheap"), ("⚖️ Средний бюджет", "mid"),
        ("💎 Дорогой / премиум", "premium"), ("🔎 Любой вариант", "any")
    ]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=f"budget:{v}") for t, v in options[:2]],
        [InlineKeyboardButton(text=t, callback_data=f"budget:{v}") for t, v in options[2:]],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="city:cancel")]
    ])


JOB_TYPES = {
    "official": ("🏢 Официальная работа", "официальная работа, трудоустройство по договору"),
    "factory": ("🏭 Завод / производство", "работа на заводе или производстве"),
    "office": ("💻 Офис", "офисная работа"),
    "cafe": ("☕ Кафе / ресторан", "работа в кафе или ресторане"),
    "parttime": ("🧾 Арбайт / подработка", "официальная подработка (арбайт)"),
    "warehouse": ("📦 Склад / упаковка", "работа на складе, упаковка"),
    "cleaning": ("🧹 Уборка / клининг", "уборка или клининг"),
    "delivery": ("🚚 Доставка / водитель", "доставка или работа водителем"),
    "construction": ("🦺 Стройка", "строительные работы"),
    "care": ("🤝 Уход / помощь", "работа по уходу или помощь"),
    "other": ("🔎 Другая работа", "другая работа или подработка"),
}
JOB_SHIFTS = {
    "regular": ("📅 Постоянная работа", "постоянная работа"),
    "day": ("☀️ Только день", "только дневная смена"),
    "night": ("🌙 Только ночь", "только ночная смена"),
    "rotating": ("🔁 Сменный график", "сменный график"),
    "any": ("🕒 Любой график", "любой график"),
}
JOB_PAY = {
    "hourly11": ("От 11 000 ₩/час", "почасовая оплата от 11000 вон"),
    "hourly12": ("От 12 000 ₩/час", "почасовая оплата от 12000 вон"),
    "monthly25": ("От 2,5 млн ₩/мес.", "месячная зарплата от 2500000 вон"),
    "monthly30": ("От 3 млн ₩/мес.", "месячная зарплата от 3000000 вон"),
    "monthly35": ("От 3,5 млн ₩/мес.", "месячная зарплата от 3500000 вон"),
    "any": ("💰 Любая зарплата", "зарплата не ограничена"),
    "custom": ("✍️ Ввести свою сумму", "custom"),
}

def jobs_type_keyboard():
    items = list(JOB_TYPES.items())
    rows = []
    for i in range(0, len(items), 2):
        rows.append([InlineKeyboardButton(text=items[j][1][0], callback_data=f"jobs:type:{items[j][0]}")
                     for j in range(i, min(i + 2, len(items)))])
    rows += [[InlineKeyboardButton(text="➕ Добавить вакансию", callback_data="jobs:post")],
             [InlineKeyboardButton(text="❌ Отмена", callback_data="jobs:cancel")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def jobs_shift_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=JOB_SHIFTS[k][0], callback_data=f"jobs:shift:{k}")]
        for k in ("regular", "day", "night", "rotating", "any")
    ] + [[InlineKeyboardButton(text="❌ Отмена", callback_data="jobs:cancel")]])

def jobs_pay_keyboard():
    keys = ("hourly11", "hourly12", "monthly25", "monthly30", "monthly35", "any", "custom")
    rows = []
    for i in range(0, len(keys), 2):
        rows.append([InlineKeyboardButton(text=JOB_PAY[k][0], callback_data=f"jobs:pay:{k}") for k in keys[i:i+2]])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="jobs:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def job_results_keyboard(jobs):
    rows = []
    for i, job in enumerate(jobs[:8]):
        title = (job.get("title") or f"Вариант {i+1}").strip()
        if len(title) > 48:
            title = title[:45] + "..."
        rows.append([InlineKeyboardButton(text=f"📄 {i+1}. {title}", callback_data=f"jobresult:{i}")])
    rows.append([InlineKeyboardButton(text="🔎 Новый поиск", callback_data="jobs:restart")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def housing_type_keyboard():
    rows = [[InlineKeyboardButton(text=label, callback_data=key)]
            for key, (label, _) in HOUSING_TYPES.items()]
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="housing:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def housing_deal_keyboard():
    rows = [[InlineKeyboardButton(text=label, callback_data=key)]
            for key, (label, _) in HOUSING_DEALS.items()]
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="housing:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def housing_price_keyboard(kind):
    presets = MONTHLY_PRESETS if kind == "monthly" else DEPOSIT_PRESETS
    prefix = "monthlyprice" if kind == "monthly" else "deposit"
    rows = [[InlineKeyboardButton(text=label, callback_data=f"{prefix}:{amount}")]
            for label, amount in presets]
    rows.append([InlineKeyboardButton(text="✍️ Ввести свою сумму", callback_data=f"{prefix}:custom")])
    rows.append([InlineKeyboardButton(text="🔎 Любая сумма", callback_data=f"{prefix}:any")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="housing:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def save_search_memory(user_id, query, korean_query, places):
    compact = [{
        "name": p.get("place_name", "Название не указано"),
        "address": p.get("road_address_name") or p.get("address_name") or "Адрес не указан",
        "phone": p.get("phone") or "", "url": p.get("place_url") or "", "id": str(p.get("id", ""))
    } for p in (places or [])[:20]]
    try:
        with db() as conn:
            conn.execute(
                "INSERT INTO search_memory(user_id,query,korean_query,results_json) VALUES(?,?,?,?)",
                (str(user_id), str(query)[:500], str(korean_query)[:500], json.dumps(compact, ensure_ascii=False))
            )
            conn.execute(
                "DELETE FROM search_memory WHERE user_id=? AND id NOT IN "
                "(SELECT id FROM search_memory WHERE user_id=? ORDER BY id DESC LIMIT 100)",
                (str(user_id), str(user_id))
            )
            conn.commit()
    except sqlite3.Error:
        logging.exception("Could not save search memory")


def get_search_memory_context(user_id, limit=8):
    try:
        with db() as conn:
            rows = conn.execute(
                "SELECT query,korean_query,results_json,created_at FROM search_memory "
                "WHERE user_id=? AND created_at >= datetime('now', '-7 days') "
                "ORDER BY id DESC LIMIT ?", (str(user_id), limit)
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
            conn.execute(
                "DELETE FROM chat_messages WHERE chat_id=? AND id NOT IN "
                "(SELECT id FROM chat_messages WHERE chat_id=? ORDER BY id DESC LIMIT 300)",
                (str(chat_id), str(chat_id))
            )
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


async def clear_chat(bot, chat_id):
    try:
        with db() as conn:
            ids = conn.execute(
                "SELECT message_id FROM chat_messages WHERE chat_id=? ORDER BY message_id DESC",
                (str(chat_id),)
            ).fetchall()
    except sqlite3.Error:
        ids = []
    failed = 0
    for (mid,) in ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=int(mid))
        except Exception:
            failed += 1
        await asyncio.sleep(0.04)
    try:
        with db() as conn:
            conn.execute("DELETE FROM chat_messages WHERE chat_id=?", (str(chat_id),))
            conn.commit()
    except sqlite3.Error:
        logging.exception("Could not reset message tracking")
    return len(ids) - failed, failed


async def search_kakao(query):
    if not KAKAO_KEY:
        return None, "Поиск не настроен: отсутствует KAKAO_REST_API_KEY в Render."
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_KEY}"}
    results, seen = [], set()
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as session:
            for page in range(1, 4):
                async with session.get(
                    url, headers=headers, params={"query": query, "size": 15, "page": page}
                ) as resp:
                    if resp.status == 401:
                        return None, "Kakao не принял ключ API. Проверь KAKAO_REST_API_KEY."
                    if resp.status == 403:
                        return None, "Kakao запретил запрос (HTTP 403). Проверь доступ к Local API."
                    if resp.status != 200:
                        logging.error("Kakao HTTP %s", resp.status)
                        return None, f"Ошибка поиска Kakao: HTTP {resp.status}."
                    data = await resp.json()
                for place in data.get("documents", []):
                    pid = str(place.get("id", "")) or (place.get("place_name"), place.get("address_name"))
                    if pid not in seen:
                        seen.add(pid)
                        results.append(place)
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
                "SELECT dimension,AVG(score),COUNT(*) FROM reviews WHERE place_id=? GROUP BY dimension",
                (str(place_id),)
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
        [InlineKeyboardButton(text=f"{n} ⭐", callback_data=f"score:{place_id}:{dimension}:{n}")
         for n in range(1, 6)],
        [InlineKeyboardButton(text="↩️ Отмена", callback_data="rate:cancel:cancel")]
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
        ("자동차", "Автомобильные услуги"), ("관광", "Достопримечательность")
    ]
    for key, label in pairs:
        if key in cat:
            return label
    return place.get("category_name") or place.get("category_group_name") or "Категория не указана"


def photo_spots_keyboard():
    rows = [
        [InlineKeyboardButton(text="🌸 Pins Coffee · Чхонан", callback_data="photo:pins")],
        [InlineKeyboardButton(text="🌿 River Nine · Намъянджу", callback_data="photo:river")],
        [InlineKeyboardButton(text="🌊 Seaer Pool Villa · Кёнджу", callback_data="photo:seaer")],
        [InlineKeyboardButton(text="📷 Rainbow Pension · Кодже", callback_data="photo:rainbow")],
        [InlineKeyboardButton(text="☕ Portrait Coffee Bar · Сеул", callback_data="photo:portrait")],
        [InlineKeyboardButton(text="🔄 Обновить список", callback_data="photo:list")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def photo_spots_text():
    return (
        "📸 МЕСТА ДЛЯ КРАСИВЫХ ФОТО\n"
        "Подборка по публичным публикациям Instagram\n\n"
        "Выбери место — покажу адрес, идею для фото и карту.\n"
        "📍 Адреса указаны на корейском, чтобы их было проще скопировать в навигатор."
    )


def photo_spot_detail(spot):
    map_url = "https://map.kakao.com/link/search/" + quote_plus(spot["map_query"])
    naver_url = "https://map.naver.com/p/search/" + quote_plus(spot["map_query"])
    return (
        f"📸 {spot['name']}\n"
        f"📍 Район: {spot['city']}\n"
        f"🗺️ Адрес: {spot['address']}\n\n"
        f"✨ Для фото: {spot['vibe']}\n"
        f"🔎 Источник подборки: Instagram {spot['source']}\n\n"
        f"🗺️ Kakao Map: {map_url}\n"
        f"🧭 Naver Map: {naver_url}\n\n"
        "ℹ️ Перед поездкой проверь часы работы, доступ для посетителей и сезонность."
    )


def price_label(pref):
    return {"cheap": "самый дешёвый вариант", "mid": "средний бюджет",
            "premium": "дорогой / премиум", "any": "любой бюджет"}.get(pref, "не указан")


def budget_search_terms(query, pref):
    q, city, ko = normalize(query), find_city(query) or "", translate_query(query)
    if pref == "cheap":
        if any(x in q for x in ("игруш", "toy")):
            return [f"저렴한 장난감 가게 {city}".strip(), f"장난감 가게 {city}".strip()]
        if any(x in q for x in ("аренд", "прокат", "машин", "авто", "rent", "car")):
            return [f"저렴한 렌터카 {city}".strip(), f"렌터카 {city}".strip()]
    if pref == "premium":
        if any(x in q for x in ("игруш", "toy")):
            return [f"고급 장난감 매장 {city}".strip(), f"장난감 가게 {city}".strip()]
        if any(x in q for x in ("аренд", "прокат", "машин", "авто", "rent", "car")):
            return [f"고급 렌터카 {city}".strip(), f"렌터카 {city}".strip()]
    return [ko]


def build_search_queries(query, budget):
    city, qnorm = find_city(query) or "", normalize(query)
    if any(w in qnorm for w in ("응급", "скорая", "неотлож", "экстренн")):
        terms = EMERGENCY_QUERIES[:3]
    elif any(w in qnorm for w in ("медицин", "больниц", "клиник", "аптек", "стомат", "врач", "병원", "의원")):
        terms = MEDICAL_QUERIES[:8]
    elif any(w in qnorm for w in ("кафе", "кофейн", "ресторан", "음식점", "카페")):
        terms = ["카페", "음식점", "식당"]
    elif any(w in qnorm for w in ("автосервис", "автозапчаст", "запчаст", "авто и запчасти", "자동차 정비", "자동차 부품")):
        terms = ["자동차 정비소", "자동차 수리", "자동차 부품"]
    elif any(w in qnorm for w in ("магазин", "магазины", "супермаркет", "마트")):
        terms = ["마트", "매장", "슈퍼마켓"]
    elif any(w in qnorm for w in ("отель", "гостиниц", "호텔")):
        terms = ["호텔", "모텔", "게스트하우스"]
    elif any(w in qnorm for w in ("салон красоты", "парикмах", "красоты", "미용실")):
        terms = ["미용실", "헤어샵", "네일샵"]
    elif any(w in qnorm for w in ("аренд", "прокат", "렌터카")):
        return list(dict.fromkeys(budget_search_terms(query, budget)))
    else:
        terms = budget_search_terms(query, budget)
    return list(dict.fromkeys(f"{term} {city}".strip() for term in terms))


AI_INSTRUCTIONS = (
    "Ты — ИИ-помощник TrustMap Korea для жизни в Южной Корее. Отвечай на языке пользователя. "
    "Используй контекст переписки и исправляй очевидные опечатки. Не выдумывай адреса, цены, "
    "рейтинги, часы работы, законы, вакансии, работодателей или официальные правила. Отличай оценки TrustMap "
    "от официальных рейтингов. Для медицинских, юридических и иммиграционных тем отвечай осторожно. "
    "При угрозе жизни в Южной Корее укажи номер 119. Будь практичным: предлагай пошаговые действия, "
    "корейские фразы с переводом и ссылки на первоисточники. Для меняющейся информации ищи свежие источники, "
    "если доступен веб-поиск. Не обещай полный охват интернета и не выдумывай источники."
)


async def ask_ai(question, user_id, extra_instructions=""):
    if not OPENAI_KEY:
        return "🤖 ИИ не подключён: проверь OPENAI_API_KEY в Render."
    history = CONVERSATION_HISTORY.setdefault(str(user_id), [])
    instructions = AI_INSTRUCTIONS
    memory = get_search_memory_context(user_id)
    if memory:
        instructions += "\n\n" + memory
    if extra_instructions:
        instructions += "\n\n" + extra_instructions
    payload = {
        "model": AI_MODEL,
        "instructions": instructions + "\n\nДля актуальных вопросов используй встроенный веб-поиск, если он доступен. "
        "Ищи по нескольким релевантным запросам, предпочитай официальные источники и указывай прямые ссылки. "
        "Если поиск не сработал, честно сообщи об этом.",
        "input": history[-MAX_HISTORY_MESSAGES:] + [{"role": "user", "content": question}],
        "max_output_tokens": 1800, "store": False,
        "tools": [{"type": "web_search"}], "tool_choice": "auto"
    }
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=100)) as session:
            async with session.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
                json=payload
            ) as resp:
                if resp.status in (400, 404, 422):
                    body = (await resp.text())[:500]
                    if "web_search" in body or "tool" in body.lower():
                        payload.pop("tools", None)
                        payload.pop("tool_choice", None)
                        async with session.post(
                            "https://api.openai.com/v1/responses",
                            headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
                            json=payload
                        ) as retry:
                            if retry.status != 200:
                                logging.error("OpenAI retry HTTP %s: %s", retry.status, (await retry.text())[:300])
                                return f"Ошибка ИИ-сервиса: HTTP {retry.status}."
                            data = await retry.json()
                    else:
                        logging.error("OpenAI HTTP %s: %s", resp.status, body)
                        return f"Ошибка ИИ-сервиса: HTTP {resp.status}."
                elif resp.status == 401:
                    return "OpenAI не принял API-ключ. Проверь OPENAI_API_KEY в Render."
                elif resp.status == 429:
                    return "ИИ временно недоступен: проверь лимиты и оплату OpenAI API."
                elif resp.status != 200:
                    logging.error("OpenAI HTTP %s: %s", resp.status, (await resp.text())[:300])
                    return f"Ошибка ИИ-сервиса: HTTP {resp.status}."
                else:
                    data = await resp.json()
        answer = "\n".join(
            c.get("text", "") for item in data.get("output", []) if item.get("type") == "message"
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


async def ask_jobs_ai(query, user_id):
    prompt = (
        "Найди реальные, публично доступные вакансии в Южной Корее по параметрам: " + query + ". "
        "Используй веб-поиск. Ищи Work24, Saramin, JobKorea, Albamon, AlbaCheonguk, открытые страницы "
        "работодателей и публичные объявления. Верни до 8 конкретных вакансий. Каждую вакансию начинай "
        "отдельным блоком с заголовком в формате 'Вакансия 1 — должность / работодатель'. Внутри каждого блока "
        "отдельными строками укажи: тип работы; работодатель; город и точный адрес, если опубликован; зарплата; "
        "дневная/ночная/сменная работа; телефон работодателя, только если публично указан; требования; дата объявления; "
        "прямая ссылка на оригинал. Неизвестные поля помечай 'Не указано в объявлении'. Не выдумывай вакансии, "
        "адреса, телефоны, зарплаты, даты или ссылки. Если конкретных вакансий нет, скажи это прямо и дай ссылки "
        "на подходящие поисковые страницы."
    )
    return await ask_ai(prompt, user_id, extra_instructions=(
        "РЕЖИМ ПОИСКА ВАКАНСИЙ. Показывай только конкретные вакансии, которые реально видны в доступных "
        "публичных источниках. Контакты работодателя показывай только если они опубликованы самим работодателем. "
        "Не обещай полный охват интернета и не раскрывай личные данные соискателей."
    ))

def job_search_links(query):
    q = quote_plus(query)
    return (
        "\n\n🔎 Дополнительные сайты поиска вакансий:\n"
        "Work24: https://www.work24.go.kr/\n"
        "Saramin: https://www.saramin.co.kr/\n"
        "JobKorea: https://www.jobkorea.co.kr/\n"
        "Albamon (арбайт): https://www.albamon.com/\n"
        "AlbaCheonguk (арбайт): https://www.alba.co.kr/\n"
        f"Naver: https://search.naver.com/search.naver?query={q}%20%EC%B1%84%EC%9A%A9"
    )

def split_job_results(text):
    matches = list(re.finditer(r"(?im)^\s*(?:вакансия\s*)?\d+[.)—:-]\s*[^\n]+", text))
    jobs = []
    if matches:
        for i, match in enumerate(matches[:8]):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            block = text[match.start():end].strip()
            first = block.splitlines()[0].strip().lstrip("#*- ")
            title = re.sub(r"(?i)^вакансия\s*\d*\s*[—:-]?\s*", "", first)
            jobs.append({"title": title[:80] or f"Вариант {i+1}", "details": block})
    elif text.strip():
        jobs.append({"title": "Посмотреть результаты поиска", "details": text.strip()})
    return jobs[:8]

async def finish_jobs_search(message, uid, city):
    flow = USER_FLOWS.get(uid)
    if not flow or flow.get("kind") != "jobs":
        return
    values = flow.get("values", {})
    type_text = JOB_TYPES.get(values.get("job_type", "other"), JOB_TYPES["other"])[1]
    shift_text = JOB_SHIFTS.get(values.get("shift", "any"), JOB_SHIFTS["any"])[1]
    pay_text = values.get("pay_text", JOB_PAY["any"][1])
    city_text = CITY_LABELS.get(city, city) if city != "전국" else "вся Южная Корея"
    query = (f"{type_text}; график: {shift_text}; желаемая зарплата: {pay_text}; город: {city_text}. "
             "Ищи объявления, соответствующие параметрам, и не выдумывай данные.")
    USER_FLOWS.pop(uid, None)
    await message.answer("🔎 Ищу вакансии по выбранным параметрам…")
    result = await ask_jobs_ai(query, message.from_user.id)
    jobs = split_job_results(result)
    JOB_RESULTS[uid] = jobs
    if not jobs:
        await send_long(message, result + job_search_links(query))
        return
    await message.answer(
        f"💼 Результаты поиска\n📍 {city_text}\nНайдено вариантов: {len(jobs)}. Нажми на вариант, чтобы открыть подробности.\n"
        "Адрес и телефон будут указаны только если они есть в исходном объявлении.",
        reply_markup=job_results_keyboard(jobs), disable_web_page_preview=True
    )
    await send_long(message, job_search_links(query))


async def send_long(message, text):
    for i in range(0, len(text), 3500):
        await message.answer(text[i:i+3500], disable_web_page_preview=True)


def place_list_keyboard(user_id, places):
    uid = str(user_id)
    cache = PLACE_RESULTS.setdefault(uid, {})
    cache.clear()
    rows = []
    for idx, place in enumerate(places[:MAX_PLACE_RESULTS_PER_USER]):
        key = str(idx)
        cache[key] = place
        name = (place.get("place_name") or "Название не указано").strip()
        # Telegram button text should be concise.
        if len(name) > 48:
            name = name[:45] + "…"
        rows.append([InlineKeyboardButton(text=f"📍 {name}", callback_data=f"place:{key}")])
    rows.append([InlineKeyboardButton(text="🔄 Новый поиск", callback_data="places:new")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def place_detail_text(place):
    pid = str(place.get("id", ""))
    summary = get_review_summary(pid) if pid else {}
    overall = summary.get("overall")
    address = place.get("road_address_name") or place.get("address_name") or "Адрес не указан в источнике"
    phone = place.get("phone") or "Телефон не указан в источнике"
    lines = [
        "🇰🇷 TRUSTMAP KOREA",
        "",
        f"🏢 {place.get('place_name', 'Название не указано')}",
        f"🏷️ {describe_category(place)}",
        f"📍 Адрес: {address}",
        f"☎️ Телефон: {phone}",
    ]
    if place.get("place_url"):
        lines.append(f"🗺️ Карта: {place['place_url']}")
    if overall:
        lines.append(f"💙 Оценка TrustMap: {overall[0]:.1f}/5 на основе {overall[1]} оценок")
    else:
        lines.append("💙 Оценка TrustMap: пока нет пользовательских оценок")
    for dim, (avg, count) in summary.items():
        if dim != "overall":
            lines.append(f"  • {RATING_DIMENSIONS.get(dim, dim)}: {avg:.1f}/5 ({count})")
    lines += [
        "",
        "ℹ️ Данные о месте получены из Kakao. Цены и часы работы могут отсутствовать или меняться.",
        "Выбери показатель ниже, чтобы оставить оценку."
    ]
    return "\n".join(lines)


async def start_place_search(message, query, user_id, budget="any"):
    uid = str(user_id)
    cancel_user_search(uid)

    async def runner():
        current = asyncio.current_task()
        try:
            await run_place_search(message, query, user_id, budget)
        except asyncio.CancelledError:
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


async def run_place_search(message, query, user_id, budget="any"):
    city_ko = find_city(query)
    search_queries = build_search_queries(query, budget)
    await message.answer("⏳ Обрабатывается запрос…")
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
        for place in found or []:
            pid = str(place.get("id", "")) or (place.get("place_name"), place.get("address_name"))
            if pid not in seen:
                seen.add(pid)
                places.append(place)
        if len(places) >= MAX_PLACE_RESULTS_PER_USER:
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
    PLACE_RESULTS[str(user_id)] = {}
    keyboard = place_list_keyboard(user_id, places)
    await message.answer(
        f"🇰🇷 TRUSTMAP KOREA\n\n"
        f"🔎 Найдено мест: {min(len(places), MAX_PLACE_RESULTS_PER_USER)}\n"
        f"Запрос: {query}\n\n"
        "Выбери место из списка, чтобы открыть адрес, телефон и оценки:",
        reply_markup=keyboard,
        disable_web_page_preview=True
    )


FEEDBACK_LABELS = {
    "like": "Что нравится", "dislike": "Что не нравится",
    "idea": "Идея / предложение", "bug": "Ошибка в боте"
}


def feedback_kind_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="😍 Что нравится", callback_data="feedback:like")],
        [InlineKeyboardButton(text="🙁 Что не нравится", callback_data="feedback:dislike")],
        [InlineKeyboardButton(text="💡 Идея / предложение", callback_data="feedback:idea")],
        [InlineKeyboardButton(text="🐞 Ошибка в боте", callback_data="feedback:bug")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="feedback:cancel")]
    ])


@dp.callback_query(F.data.startswith("jobs:"))
async def jobs_callback(callback: CallbackQuery):
    uid = str(callback.from_user.id)
    parts = (callback.data or "").split(":")
    action = parts[1] if len(parts) > 1 else ""
    choice = parts[2] if len(parts) > 2 else ""
    if action == "cancel":
        USER_FLOWS.pop(uid, None)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer("Поиск отменён")
        return
    if action == "restart":
        USER_FLOWS[uid] = {"kind": "jobs", "stage": "type", "values": {}}
        await callback.message.answer("💼 Какую работу ищем?", reply_markup=jobs_type_keyboard())
        await callback.answer()
        return
    if action == "post":
        USER_FLOWS[uid] = {"kind": "jobs_submit", "stage": "message", "values": {}}
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            "➕ Отправь одним сообщением текст вакансии: должность, город, адрес, зарплата, график и публичный контакт работодателя. "
            "Не публикуй чужие личные данные. Объявление сохранится на проверку перед публикацией."
        )
        await callback.answer()
        return
    flow = USER_FLOWS.get(uid)
    if not flow or flow.get("kind") != "jobs":
        await callback.answer("Этот выбор уже не активен. Нажми «Работа» заново.", show_alert=True)
        return
    if action == "type" and choice in JOB_TYPES:
        flow["values"]["job_type"] = choice
        flow["stage"] = "shift"
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("🕒 Какой график тебе подходит?", reply_markup=jobs_shift_keyboard())
        await callback.answer()
        return
    if action == "shift" and choice in JOB_SHIFTS:
        flow["values"]["shift"] = choice
        flow["stage"] = "pay"
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("💰 Какая зарплата тебя устроит?", reply_markup=jobs_pay_keyboard())
        await callback.answer()
        return
    if action == "pay" and choice in JOB_PAY:
        if choice == "custom":
            flow["stage"] = "pay_custom"
            await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.answer("✍️ Напиши желаемую зарплату (например, 13 000 вон/час или от 3 000 000 вон в месяц).")
            await callback.answer()
            return
        flow["values"]["pay_text"] = JOB_PAY[choice][1]
        flow["stage"] = "city"
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("📍 В каком городе искать вакансии?", reply_markup=city_keyboard())
        await callback.answer()
        return
    await callback.answer("Неизвестный выбор. Начни поиск заново.", show_alert=True)


@dp.callback_query(F.data.startswith("jobresult:"))
async def job_result_callback(callback: CallbackQuery):
    uid = str(callback.from_user.id)
    try:
        index = int((callback.data or "").split(":", 1)[1])
        job = JOB_RESULTS.get(uid, [])[index]
    except (ValueError, IndexError):
        await callback.answer("Результаты устарели. Запусти новый поиск.", show_alert=True)
        return
    await callback.message.answer("💼 " + job["title"] + "\n\n" + job["details"], disable_web_page_preview=True)
    await callback.answer()


@dp.callback_query(F.data.startswith("photo:"))
async def photo_spot_callback(callback: CallbackQuery):
    choice = (callback.data or "").split(":", 1)[1]
    if choice == "list":
        await callback.message.answer(photo_spots_text(), reply_markup=photo_spots_keyboard(), disable_web_page_preview=True)
        await callback.answer("Список мест обновлён")
        return
    spot = PHOTO_SPOTS.get(choice)
    if not spot:
        await callback.answer("Место не найдено. Открой список заново.", show_alert=True)
        return
    await callback.message.answer(photo_spot_detail(spot), disable_web_page_preview=True)
    await callback.answer()


@dp.callback_query(F.data == "places:new")
async def new_places_search_callback(callback: CallbackQuery):
    USER_FLOWS.pop(str(callback.from_user.id), None)
    await callback.message.answer("Напиши, что ищем и в каком городе. Например: «кафе в Чхонане».")
    await callback.answer()


@dp.callback_query(F.data.startswith("place:"))
async def place_detail_callback(callback: CallbackQuery):
    uid = str(callback.from_user.id)
    key = (callback.data or "").split(":", 1)[1]
    place = PLACE_RESULTS.get(uid, {}).get(key)
    if not place:
        await callback.answer("Этот список устарел. Запусти поиск заново.", show_alert=True)
        return
    pid = str(place.get("id", ""))
    keyboard = review_keyboard(pid, place) if pid else None
    await callback.message.answer(place_detail_text(place), reply_markup=keyboard, disable_web_page_preview=True)
    await callback.answer()


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
        f"✍️ Напиши одним сообщением: {FEEDBACK_LABELS[choice].lower()}. Можно подробно. "
        "Не отправляй пароли, номера документов или банковские данные."
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
                "SELECT id,user_id,username,feedback_type,message,created_at FROM bot_feedback "
                "ORDER BY id DESC LIMIT 30"
            ).fetchall()
    except sqlite3.Error:
        logging.exception("Could not read bot feedback")
        await message.answer("Не удалось прочитать отзывы из базы данных.")
        return
    if not rows:
        await message.answer("Пока отзывов о боте нет.")
        return
    current, chunks = "💬 ПОСЛЕДНИЕ ОТЗЫВЫ TRUSTMAP KOREA\n\n", []
    for rid, uid, username, kind, body, created in rows:
        item = (
            f"#{rid} · {created}\nТип: {FEEDBACK_LABELS.get(kind, kind)}\n"
            f"Пользователь: @{username or 'не указан'} (ID {uid})\n{body}\n\n━━━━━━━━━━━━\n\n"
        )
        if len(current) + len(item) > 3500:
            chunks.append(current)
            current = ""
        current += item
    if current:
        chunks.append(current)
    for chunk in chunks:
        await message.answer(chunk)


@dp.message(Command("clear"))
async def clear_command(message: Message):
    uid = str(message.from_user.id)
    cancel_user_search(uid)
    CONVERSATION_HISTORY.pop(uid, None)
    USER_FLOWS.pop(uid, None)
    PLACE_RESULTS.pop(uid, None)
    deleted, failed = await clear_chat(message.bot, message.chat.id)
    notice = "🧹 Чат очищен. Начнём заново."
    if failed:
        notice += f"\nНекоторые сообщения Telegram не разрешил удалить ({failed})."
    notice += "\nОценки мест, отзывы о боте и сохранённые поиски не удалены."
    await message.answer(notice, reply_markup=make_keyboard())


@dp.message(CommandStart())
async def start(message: Message):
    cancel_user_search(message.from_user.id)
    USER_FLOWS.pop(str(message.from_user.id), None)
    await message.answer(
        "🇰🇷 TRUSTMAP KOREA\n\n"
        "Помощник для жизни в Южной Корее.\n"
        "Ищи места, работу, магазины игрушек, аренду авто, медицину, жильё и услуги.\n"
        "Можно искать в конкретном городе или по Корее.\n"
        "Оценки пользователей объединяются в общий рейтинг.\n\n"
        "Примеры: «нужны недорогие игрушки в Чхонане» или "
        "«ищу работу на складе в Чхонане, зарплата от 3 млн вон».",
        reply_markup=make_keyboard()
    )


@dp.message(Command("help"))
async def help_command(message: Message):
    cancel_user_search(message.from_user.id)
    await message.answer(
        "Примеры запросов:\n• кафе в Чхонане\n• недорогие игрушки в Сеуле\n"
        "• аренда машины в Пусане\n• аптека в Инчхоне\n• больница в Чхонане\n"
        "• работа на складе в Чхонане с жильём\n"
        "• /ai Как сказать спасибо по-корейски?\n\n"
        "Для экстренной помощи в Корее звони 119. Оценки TrustMap — оценки пользователей, не официальный рейтинг.",
        reply_markup=make_keyboard()
    )


@dp.message(Command("ai"))
async def ai_command(message: Message):
    cancel_user_search(message.from_user.id)
    USER_FLOWS.pop(str(message.from_user.id), None)
    question = (message.text or "").partition(" ")[2].strip()
    if not question:
        await message.answer("Напиши вопрос после /ai.")
        return
    await message.answer("⏳ Обрабатывается запрос…")
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


def food_choice_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="☕ Только кафе", callback_data="food:cafe"),
         InlineKeyboardButton(text="🍽️ Только рестораны", callback_data="food:restaurant")],
        [InlineKeyboardButton(text="🔎 Кафе и рестораны", callback_data="food:both")],
        [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="nav:home")],
    ])


def chain_choice_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="emart", callback_data="chain:emart"),
         InlineKeyboardButton(text="GS25", callback_data="chain:gs25")],
        [InlineKeyboardButton(text="CU", callback_data="chain:cu"),
         InlineKeyboardButton(text="7-Eleven", callback_data="chain:seven")],
        [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="nav:home")],
    ])


@dp.callback_query(F.data == "nav:home")
async def nav_home_callback(callback: CallbackQuery):
    uid = str(callback.from_user.id)
    USER_FLOWS.pop(uid, None)
    cancel_user_search(uid)
    await callback.message.answer("🏠 Главное меню TrustMap Korea", reply_markup=make_keyboard())
    await callback.answer()


@dp.callback_query(F.data.startswith("food:"))
async def food_choice_callback(callback: CallbackQuery):
    uid = str(callback.from_user.id)
    choice = (callback.data or "").split(":", 1)[1]
    query = {"cafe": "카페", "restaurant": "음식점", "both": "카페 음식점"}.get(choice)
    if not query:
        await callback.answer("Не удалось определить выбор.", show_alert=True)
        return
    USER_FLOWS[uid] = {"kind": "special_search", "stage": "city", "values": {"query": query, "notice": "food"}}
    await callback.message.answer("📍 Выбери город или поиск по всей Корее:", reply_markup=city_keyboard())
    await callback.answer()


@dp.callback_query(F.data.startswith("chain:"))
async def chain_choice_callback(callback: CallbackQuery):
    uid = str(callback.from_user.id)
    choice = (callback.data or "").split(":", 1)[1]
    queries = {
        "emart": "이마트", "gs25": "GS25 편의점",
        "cu": "CU 편의점", "seven": "세븐일레븐 편의점",
    }
    query = queries.get(choice)
    if not query:
        await callback.answer("Не удалось определить сеть.", show_alert=True)
        return
    USER_FLOWS[uid] = {"kind": "special_search", "stage": "city", "values": {"query": query, "notice": "chain"}}
    await callback.message.answer("📍 В каком городе искать магазины этой сети?", reply_markup=city_keyboard())
    await callback.answer()


@dp.callback_query(F.data.startswith("community:"))
async def community_callback(callback: CallbackQuery):
    uid = str(callback.from_user.id)
    action = (callback.data or "").split(":", 1)[1]
    if action == "post":
        USER_FLOWS[uid] = {"kind": "community_post", "stage": "message", "values": {}}
        await callback.message.answer(
            "✍️ Напиши сообщение для сообщества: полезную информацию, новость или личный опыт. "
            "Не публикуй чужие телефоны, адреса проживания и другие личные данные. "
            "Публикация попадёт администратору на проверку."
        )
    elif action == "rules":
        await callback.message.answer(
            "📌 Правила сообщества: уважай участников; указывай город и дату, если это важно; "
            "отделяй личный опыт от проверенных фактов; не размещай спам, мошеннические предложения "
            "или чужие личные данные. Публикации пока проходят ручную проверку."
        )
    await callback.answer()


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
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer("Поиск по Корее")
        if flow.get("kind") == "housing":
            await begin_housing_city(callback.message, user_id, "전국")
            return
        if flow.get("kind") == "jobs":
            await finish_jobs_search(callback.message, user_id, "전국")
            return
        query = flow.get("values", {}).get("query", "")
        budget = flow.get("values", {}).get("budget", "any")
        USER_FLOWS.pop(user_id, None)
        await start_place_search(callback.message, query, user_id, budget)
        return
    city_ko = CITY_CALLBACKS.get(choice)
    if not city_ko:
        await callback.answer("Не удалось определить город.", show_alert=True)
        return
    if not flow or flow.get("stage") != "city":
        await callback.answer("Этот выбор города уже не активен. Напиши запрос заново.", show_alert=True)
        return
    if flow.get("kind") == "housing":
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer(f"Город: {CITY_LABELS.get(city_ko, city_ko)}")
        await begin_housing_city(callback.message, user_id, city_ko)
        return
    if flow.get("kind") == "jobs":
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer(f"Город: {CITY_LABELS.get(city_ko, city_ko)}")
        await finish_jobs_search(callback.message, user_id, city_ko)
        return
    query = flow.get("values", {}).get("query", "")
    budget = flow.get("values", {}).get("budget", "any")
    USER_FLOWS.pop(user_id, None)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer(f"Город: {CITY_LABELS.get(city_ko, city_ko)}")
    await start_place_search(callback.message, f"{query} {city_ko}", user_id, budget)


@dp.callback_query(F.data.startswith("deal:"))
async def housing_deal_callback(callback: CallbackQuery):
    uid = str(callback.from_user.id)
    choice = (callback.data or "").split(":", 1)[1]
    flow = USER_FLOWS.get(uid)
    key = f"deal:{choice}"
    if not flow or flow.get("kind") != "housing" or flow.get("stage") != "deal" or key not in HOUSING_DEALS:
        await callback.answer("Этот выбор уже не активен. Начни поиск жилья заново.", show_alert=True)
        return
    label, deal = HOUSING_DEALS[key]
    flow["values"]["deal_label"] = label
    flow["values"]["deal"] = deal
    flow["stage"] = "city"
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("📍 В каком городе искать жильё?", reply_markup=city_keyboard())
    await callback.answer()


@dp.callback_query(F.data.startswith("housing:"))
async def housing_callback(callback: CallbackQuery):
    uid = str(callback.from_user.id)
    raw_choice = callback.data or ""
    choice = raw_choice.split(":", 1)[1]
    flow = USER_FLOWS.get(uid)
    if choice == "cancel":
        USER_FLOWS.pop(uid, None)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer("Поиск жилья отменён")
        return
    if not flow or flow.get("kind") != "housing":
        await callback.answer("Начни поиск жилья заново.", show_alert=True)
        return
    if raw_choice in HOUSING_TYPES:
        label, korean = HOUSING_TYPES[raw_choice]
        flow["values"]["housing_type"] = label
        flow["values"]["housing_korean"] = korean
        flow["stage"] = "deal"
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("🏠 Какой вариант жилья интересует?", reply_markup=housing_deal_keyboard())
        await callback.answer()
        return
    await callback.answer("Неизвестный выбор.", show_alert=True)


async def begin_housing_city(message, uid, city):
    flow = USER_FLOWS.get(uid)
    if not flow or flow.get("kind") != "housing":
        return False
    flow["values"]["city"] = city
    deal = flow["values"].get("deal", "monthly")
    if deal == "monthly":
        flow["stage"] = "monthlyprice"
        await message.answer("💸 Какую ежемесячную оплату 월세 рассматриваешь?", reply_markup=housing_price_keyboard("monthly"))
    elif deal == "jeonse":
        flow["stage"] = "deposit"
        await message.answer("💰 Какой залог 보증금 / сумма 전세 подходит?", reply_markup=housing_price_keyboard("deposit"))
    elif deal == "sale":
        flow["stage"] = "saleprice"
        await message.answer("💰 Напиши максимальную цену покупки в вонах, например 200000000, или «любой бюджет».")
    else:
        flow["stage"] = "monthlyprice"
        await message.answer("💸 Выбери ежемесячную оплату 월세 или любой бюджет:", reply_markup=housing_price_keyboard("monthly"))
    return True


async def finish_housing_search(message, uid):
    flow = USER_FLOWS.get(uid)
    if not flow:
        return
    values = flow.get("values", {})
    city = values.get("city", "")
    deal = values.get("deal", "monthly")
    htype = values.get("housing_korean", "부동산")
    city_label = CITY_LABELS.get(city, city)
    if deal == "monthly":
        monthly = values.get("monthly_max")
        deposit = values.get("deposit_max")
        query = f"{city_label} {htype} 월세"
        if monthly is not None:
            query += f" 월세 {monthly}원 이하"
        if deposit is not None:
            query += f" 보증금 {deposit}원 이하"
    elif deal == "jeonse":
        query = f"{city_label} {htype} 전세"
        if values.get("deposit_max") is not None:
            query += f" 전세 {values['deposit_max']}원 이하"
    elif deal == "sale":
        query = f"{city_label} {htype} 매매"
        if values.get("sale_max") is not None:
            query += f" {values['sale_max']}원 이하"
    else:
        query = f"{city_label} {htype} 부동산"
    query += " 부동산 중개업소"
    USER_FLOWS.pop(uid, None)
    # Kakao returns agencies/places, not a verified database of active listings.
    await message.answer(
        "⏳ Обрабатывается запрос…\n"
        "Ищу агентства и доступные публичные результаты. Активные объявления частных владельцев "
        "будут доступны только там, где сайт открывает их без закрытого API или авторизации."
    )
    await search_housing_sources(message, query, uid, values)


async def search_housing_sources(message, query, user_id, values):
    # Search public web pages through OpenAI web search where available, then show Kakao agencies.
    # Kakao Local API itself does not provide rental-listing inventory.
    if OPENAI_KEY:
        prompt = (
            "Найди публично доступные объявления о жилье в Южной Корее по запросу: " + query + ". "
            "Ищи частные объявления и предложения агентств там, где страницы доступны публично: Naver Real Estate, "
            "Dabang, Zigbang, Peter Pan, сайты агентств и другие открытые сайты. Не утверждай, что проверил все сайты. "
            "Не обходи авторизацию, paywall, антибот-защиту или закрытые API. Для каждого найденного объявления укажи "
            "тип жилья, район, месячную оплату, 보증금/залог, 전세/чонсе или цену покупки, если они реально указаны, "
            "источник и прямую ссылку. Не выдумывай цены и ссылки. Если актуальные объявления не удалось достоверно "
            "получить, честно скажи и предложи агентства недвижимости из Kakao."
        )
        extra = (
            f"Параметры пользователя: {json.dumps(values, ensure_ascii=False)}. "
            "Если результат веб-поиска содержит ссылки на публичные объявления, включи их."
        )
        try:
            web_result = await ask_ai(prompt, user_id, extra)
            await send_long(message, "🏠 Публичные объявления, найденные через доступный веб-поиск:\n\n" + web_result)
        except Exception:
            logging.exception("Housing web search failed")
    # Also return real estate offices from Kakao Local, displayed as a compact list.
    found, error = await search_kakao(query)
    if error:
        await message.answer(error)
        return
    agencies = [p for p in (found or []) if "부동산" in (p.get("category_name", "") + p.get("place_name", ""))]
    if agencies:
        PLACE_RESULTS[str(user_id)] = {}
        await message.answer(
            "🏢 Агентства недвижимости из Kakao. Нажми на название, чтобы открыть контакты:",
            reply_markup=place_list_keyboard(user_id, agencies)
        )


@dp.callback_query(F.data.startswith("monthlyprice:"))
async def monthly_price_callback(callback: CallbackQuery):
    uid = str(callback.from_user.id)
    flow = USER_FLOWS.get(uid)
    if not flow or flow.get("kind") != "housing" or flow.get("stage") != "monthlyprice":
        await callback.answer("Этот выбор уже не активен.", show_alert=True)
        return
    raw = (callback.data or "").split(":", 1)[1]
    if raw == "custom":
        flow["stage"] = "monthly_custom"
        await callback.message.answer("✍️ Введи максимальную ежемесячную оплату в вонах, например 400000.")
        await callback.answer()
        return
    flow["values"]["monthly_max"] = None if raw == "any" else int(raw)
    flow["stage"] = "deposit"
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("💰 Какой залог 보증금 подходит?", reply_markup=housing_price_keyboard("deposit"))
    await callback.answer()


@dp.callback_query(F.data.startswith("deposit:"))
async def deposit_callback(callback: CallbackQuery):
    uid = str(callback.from_user.id)
    flow = USER_FLOWS.get(uid)
    if not flow or flow.get("kind") != "housing" or flow.get("stage") != "deposit":
        await callback.answer("Этот выбор уже не активен.", show_alert=True)
        return
    raw = (callback.data or "").split(":", 1)[1]
    if raw == "custom":
        flow["stage"] = "deposit_custom"
        await callback.message.answer("✍️ Введи максимальный залог в вонах, например 5000000.")
        await callback.answer()
        return
    flow["values"]["deposit_max"] = None if raw == "any" else int(raw)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Параметры сохранены")
    await finish_housing_search(callback.message, uid)


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
        f"💙 Оцени: {RATING_DIMENSIONS[dim]}\n"
        "1 ⭐ — очень плохо · 2 ⭐ — плохо · 3 ⭐ — нормально · 4 ⭐ — хорошо · 5 ⭐ — отлично",
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
            conn.execute(
                "INSERT INTO reviews(place_id,place_name,user_id,dimension,score) VALUES(?,?,?,?,?) "
                "ON CONFLICT(place_id,user_id,dimension) DO UPDATE SET score=excluded.score,created_at=CURRENT_TIMESTAMP",
                (pid, "Место Kakao ID " + pid, str(callback.from_user.id), dim, score)
            )
            conn.commit()
        summary = get_review_summary(pid).get(dim)
        await callback.message.edit_reply_markup(reply_markup=None)
        if summary:
            await callback.message.answer(
                f"💙 Спасибо! Общая оценка «{RATING_DIMENSIONS[dim]}»: "
                f"{summary[0]:.1f}/5 на основе {summary[1]} оценок. Этот средний балл виден всем пользователям."
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
    cancel_user_search(uid)

    if text == "⬅️ Назад в меню":
        USER_FLOWS.pop(uid, None)
        cancel_user_search(uid)
        await message.answer("🏠 Главное меню TrustMap Korea", reply_markup=make_keyboard())
        return
    if text == "🧹 Очистить чат":
        CONVERSATION_HISTORY.pop(uid, None)
        USER_FLOWS.pop(uid, None)
        PLACE_RESULTS.pop(uid, None)
        JOB_RESULTS.pop(uid, None)
        deleted, failed = await clear_chat(message.bot, message.chat.id)
        extra = f"\nTelegram не разрешил удалить {failed} сообщений." if failed else ""
        await message.answer(
            f"🧹 Чат очищен. Удалено сообщений: {deleted}.{extra}\n"
            "Оценки, отзывы о боте и сохранённые поиски не удалены.",
            reply_markup=make_keyboard()
        )
        return
    if text == "🤖 ИИ-помощник":
        USER_FLOWS.pop(uid, None)
        await message.answer("Напиши любой вопрос обычным сообщением. Для актуальной информации я попробую использовать веб-поиск.")
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
                    f"Язык Telegram: {getattr(message.from_user,'language_code',None) or 'не указан'}\n\n"
                    f"{body[:3000]}\n\nЧитать сохранённые отзывы: /feedbacks"
                )
            except Exception:
                logging.exception("Could not notify bot owner about feedback")
        return

    # Community submissions are saved for moderation; they are not broadcast automatically.
    flow = USER_FLOWS.get(uid)
    if flow and flow.get("kind") == "community_post" and flow.get("stage") == "message":
        if len(text.strip()) < 5:
            await message.answer("Добавь немного больше информации (минимум 5 символов).")
            return
        username = message.from_user.username or None
        try:
            with db() as conn:
                cur = conn.execute(
                    "INSERT INTO community_posts(user_id,username,message) VALUES(?,?,?)",
                    (uid, username, text[:5000])
                )
                post_id = cur.lastrowid
                conn.commit()
            USER_FLOWS.pop(uid, None)
            await message.answer(
                "✅ Публикация отправлена на проверку. Она не появится у других пользователей, "
                "пока администратор её не проверит.",
                reply_markup=make_keyboard()
            )
            if ADMIN_TELEGRAM_ID:
                try:
                    await message.bot.send_message(
                        int(ADMIN_TELEGRAM_ID),
                        f"💬 ПУБЛИКАЦИЯ СООБЩЕСТВА НА ПРОВЕРКУ #{post_id}\\n"
                        f"От: @{username or 'без username'} (ID {uid})\\n\\n{text[:3500]}"
                    )
                except Exception:
                    logging.exception("Could not notify admin about community post")
        except sqlite3.Error:
            logging.exception("Could not save community post")
            USER_FLOWS.pop(uid, None)
            await message.answer("Не удалось сохранить публикацию. Попробуй позже.", reply_markup=make_keyboard())
        return

    # Accept user-submitted job ads for moderation before publication.
    flow = USER_FLOWS.get(uid)
    if flow and flow.get("kind") == "jobs_submit" and flow.get("stage") == "message":
        if len(text) < 15:
            await message.answer("Добавь чуть больше информации о вакансии (минимум 15 символов).")
            return
        username = message.from_user.username or None
        try:
            with db() as conn:
                cur = conn.execute(
                    "INSERT INTO user_job_posts(user_id,username,message) VALUES(?,?,?)",
                    (uid, username, text[:5000])
                )
                post_id = cur.lastrowid
                conn.commit()
            USER_FLOWS.pop(uid, None)
            await message.answer("✅ Вакансия отправлена на проверку. После проверки её можно будет добавить в общий список.", reply_markup=make_keyboard())
            if ADMIN_TELEGRAM_ID:
                try:
                    await message.bot.send_message(
                        int(ADMIN_TELEGRAM_ID),
                        f"➕ ВАКАНСИЯ НА ПРОВЕРКУ #{post_id}\nОт: @{username or 'без username'} (ID {uid})\n\n{text[:3500]}"
                    )
                except Exception:
                    logging.exception("Could not notify admin about user job post")
        except sqlite3.Error:
            logging.exception("Could not save user job post")
            USER_FLOWS.pop(uid, None)
            await message.answer("Не удалось сохранить вакансию. Попробуй позже.", reply_markup=make_keyboard())
        return

    # Continue custom salary and city stages before interpreting the text as a new query.
    flow = USER_FLOWS.get(uid)
    if flow and flow.get("kind") == "jobs" and flow.get("stage") == "pay_custom":
        flow["values"]["pay_text"] = text[:120]
        flow["stage"] = "city"
        await message.answer("📍 В каком городе искать вакансии?", reply_markup=city_keyboard())
        return
    if flow and flow.get("kind") == "jobs" and flow.get("stage") == "city":
        city = find_city(text)
        if not city and flow.get("allow_custom_city"):
            city = text.strip()
        if not city:
            await message.answer("Не распознал город. Выбери город кнопкой или нажми «Другой город».", reply_markup=city_keyboard())
            return
        await finish_jobs_search(message, uid, city)
        return
    if flow and flow.get("kind") == "housing":
        stage = flow.get("stage")
        if stage == "city":
            city = find_city(text) or text.strip()
            await begin_housing_city(message, uid, city)
            return
        if stage in ("monthly_custom", "deposit_custom", "saleprice"):
            raw = re.sub(r"[,\s₩원]", "", text.lower())
            if raw in ("любой бюджет", "любой", "без ограничений", "any", "не важно"):
                amount = None
            else:
                try:
                    amount = int(raw)
                    if amount < 0:
                        raise ValueError
                except ValueError:
                    await message.answer("Введи сумму цифрами в вонах, например 5000000, или напиши «любой бюджет».")
                    return
            if stage == "monthly_custom":
                flow["values"]["monthly_max"] = amount
                flow["stage"] = "deposit"
                await message.answer("💰 Какой залог 보증금 подходит?", reply_markup=housing_price_keyboard("deposit"))
                return
            if stage == "deposit_custom":
                flow["values"]["deposit_max"] = amount
                await finish_housing_search(message, uid)
                return
            flow["values"]["sale_max"] = amount
            await finish_housing_search(message, uid)
            return

    if text in [item for row in CATEGORIES for item in row]:
        USER_FLOWS.pop(uid, None)
        if text == "📸 Места для фото":
            await message.answer(photo_spots_text(), reply_markup=photo_spots_keyboard(), disable_web_page_preview=True)
            return
        if text == "🍽️ Кафе и рестораны":
            await message.answer("Что ищем?", reply_markup=food_choice_keyboard())
            return
        if text == "🏪 Сети магазинов":
            await message.answer("Выбери сеть магазинов:", reply_markup=chain_choice_keyboard())
            return
        if text == "💊 Круглосуточные аптеки":
            USER_FLOWS[uid] = {"kind": "special_search", "stage": "city", "values": {
                "query": "24시간 약국", "notice": "pharmacy24"
            }}
            await message.answer(
                "💊 Выбери город. Важно: Kakao может находить аптеки по запросу «24시간 약국», "
                "но не всегда подтверждает актуальные часы работы. Проверяй часы по телефону перед поездкой.",
                reply_markup=city_keyboard()
            )
            return
        if text == "👘 Ханбок и традиционная одежда":
            USER_FLOWS[uid] = {"kind": "special_search", "stage": "city", "values": {
                "query": "한복 대여", "notice": "hanbok"
            }}
            await message.answer("👘 В каком городе искать аренду ханбока?", reply_markup=city_keyboard())
            return
        if text == "💬 Сообщество":
            await message.answer(
                "💬 Сообщество TrustMap Korea\\n\\n"
                "Здесь можно предложить полезную новость или личный опыт. Сейчас публикации отправляются "
                "администратору на проверку; автоматической общей ленты и чата участников пока нет.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="➕ Предложить публикацию", callback_data="community:post")],
                    [InlineKeyboardButton(text="📌 Правила", callback_data="community:rules")],
                    [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="nav:home")],
                ])
            )
            return
        if text == "🏠 Недвижимость":
            USER_FLOWS[uid] = {"kind": "housing", "stage": "type", "values": {}}
            await message.answer("🏠 Какой тип жилья ищешь?", reply_markup=housing_type_keyboard())
            return
        if text == "💼 Работа":
            USER_FLOWS[uid] = {"kind": "jobs", "stage": "type", "values": {}}
            await message.answer("💼 Какую работу ищем?", reply_markup=jobs_type_keyboard())
            return
        category_queries = {
            "🔎 Поиск мест": None, "🏥 Медицина": "медицинские учреждения",
            "🍽️ Кафе и рестораны": "кафе или ресторан", "🛍️ Магазины": "магазин",
            "🚗 Авто и запчасти": "автосервис или автозапчасти", "🚙 Аренда машины": "аренда машины",
            "💄 Красота и уход": "салон красоты", "👶 Товары для детей": "детские товары",
            "🧸 Игрушки": "магазин игрушек", "🐾 Товары для животных": "зоомагазин",
            "🔧 Бытовые услуги": "бытовые услуги", "🏨 Отели": "отель",
            "📍 Достопримечательности": "достопримечательности", "💰 Сравнение цен": None,
            "🧖 Бани и сауны": "бани и сауны", "🎮 Компьютерные клубы": "компьютерные клубы",
        }
        preset = category_queries.get(text)
        if preset:
            if text in ("🧸 Игрушки", "🚙 Аренда машины"):
                USER_FLOWS[uid] = {"kind": "search", "stage": "budget", "values": {"query": preset, "budget": "any"}}
                await message.answer(f"{text}\n\n💰 Какой ценовой вариант предпочитаешь?", reply_markup=preference_keyboard())
            else:
                USER_FLOWS[uid] = {"kind": "search", "stage": "city", "values": {"query": preset, "budget": "any"}}
                await message.answer(f"{text}\n\n📍 Выбери город или поиск по всей Корее:", reply_markup=city_keyboard())
        else:
            await message.answer("Напиши, что именно ищем. Например: «недорогие игрушки в Чхонане».")
        return

    flow = USER_FLOWS.get(uid)
    if flow and flow.get("kind") == "search" and flow.get("stage") == "city":
        city_ko = find_city(text)
        if not city_ko and flow.get("allow_custom_city"):
            city_ko = text.strip()
        if city_ko:
            query = flow.get("values", {}).get("query", "")
            budget = flow.get("values", {}).get("budget", "any")
            USER_FLOWS.pop(uid, None)
            await start_place_search(message, f"{query} {city_ko}", uid, budget)
            return
        if not is_place_search(text):
            await message.answer("Не распознал город. Выбери его кнопкой, нажми «Другой город» или «Искать по Корее».", reply_markup=city_keyboard())
            return

    if any(x in q for x in ("помнишь", "что я искал раньше", "что я искала раньше", "предыдущий поиск", "мой прошлый поиск")):
        memory = get_search_memory_context(uid)
        if not memory:
            await message.answer("🧠 Пока нет сохранённых поисков. Сначала найди место через TrustMap.")
        else:
            await message.answer("⏳ Обрабатывается запрос…")
            await send_long(message, await ask_ai(text, message.from_user.id))
        return

    if is_job_query(text):
        await message.answer("⏳ Обрабатывается запрос…")
        result = await ask_jobs_ai(text, message.from_user.id)
        await send_long(message, result + job_search_links(text))
        await message.answer(
            "ℹ️ Перед откликом проверь оригинальное объявление. Не плати за обещание гарантированного трудоустройства или визы.",
            reply_markup=make_keyboard()
        )
        return

    if looks_like_ai(text):
        USER_FLOWS.pop(uid, None)
        await message.answer("⏳ Обрабатывается запрос…")
        await send_long(message, await ask_ai(text, message.from_user.id))
        return

    if is_place_search(text) or any(x in q for x in ("медицинские учреждения", "больница", "аптека", "клиника", "скорая помощь")):
        USER_FLOWS.pop(uid, None)
        needs_budget = any(x in q for x in ("игруш", "toy", "аренд", "прокат машин", "аренда авто", "аренда машины", "렌터카"))
        budget = "any"
        if needs_budget and not any(x in q for x in ("дешев", "недорог", "дорог", "премиум", "cheap", "premium")):
            USER_FLOWS[uid] = {"kind": "search", "stage": "budget", "values": {"query": text, "budget": "any"}}
            await message.answer("💰 Какой ценовой вариант предпочитаешь?", reply_markup=preference_keyboard())
            return
        if any(x in q for x in ("дешев", "недорог", "cheap")):
            budget = "cheap"
        elif any(x in q for x in ("дорог", "премиум", "premium", "люкс")):
            budget = "premium"
        elif any(x in q for x in ("средний бюджет", "средняя цена")):
            budget = "mid"
        await start_place_search(message, text, uid, budget)
        return

    USER_FLOWS.pop(uid, None)
    await message.answer("⏳ Обрабатывается запрос…")
    await send_long(message, await ask_ai(text, message.from_user.id))


async def daily_maintenance():
    """Remove stale search snapshots daily; place reviews and bot feedback are preserved.

    Search results are fetched from Kakao/web sources on each new search rather than reused
    as a permanent listing cache. Saved search snapshots are only conversational memory and expire after seven days.
    """
    while True:
        try:
            with db() as conn:
                conn.execute("DELETE FROM search_memory WHERE created_at < datetime('now', '-7 days')")
                conn.commit()
            logging.info("Daily maintenance complete: expired search snapshots cleaned; reviews preserved")
        except Exception:
            logging.exception("Daily maintenance failed")
        await asyncio.sleep(24 * 60 * 60)


async def main():
    if not TOKEN:
        raise RuntimeError("Не задан TELEGRAM_BOT_TOKEN в переменных окружения.")
    init_db()
    bot = Bot(token=TOKEN)
    maintenance_task = asyncio.create_task(daily_maintenance())
    try:
        await dp.start_polling(bot)
    finally:
        maintenance_task.cancel()
        try:
            await maintenance_task
        except asyncio.CancelledError:
            pass
        for task in list(SEARCH_TASKS.values()):
            if not task.done():
                task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
