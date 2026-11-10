# -*- coding: utf-8 -*-
import os, json, random, csv, urllib.request
from datetime import datetime
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# ================= НАСТРОЙКИ =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
SHEET_CSV_URL = os.getenv("SHEET_CSV_URL")
ANALYTICS_FILE = "analytics.json"

session = AiohttpSession()
bot = Bot(token=BOT_TOKEN, session=session)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# ================= ФУНКЦИИ =================
def load_mk_data():
    try:
        req = urllib.request.Request(SHEET_CSV_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as response:
            csv_data = response.read().decode('utf-8')
        
        # Умное определение разделителя: если есть ';', используем его, иначе ','
        first_line = csv_data.split('\n')[0]
        delimiter = ';' if ';' in first_line else ','
        
        reader = csv.DictReader(csv_data.splitlines(), delimiter=delimiter)
        
        # ОТЛАДКА: Печатаем заголовки, чтобы видеть их в логах Bothost
        print(f"🔍 DEBUG: Заголовки в таблице: {reader.fieldnames}")
        
        data = []
        for row in reader:
            try:
                # Приводим все ключи к нижнему регистру и убираем пробелы для надёжности
                clean_row = {k.strip().lower(): v.strip() for k, v in row.items() if k}
                
                name = clean_row.get('name', '')
                category = clean_row.get('category', '')
                link = clean_row.get('link', '')
                
                if not name or not category:
                    continue
                    
                data.append({"link": link, "name": name, "category": category})
            except Exception as e:
                continue
        
        print(f"✅ DEBUG: Успешно загружено {len(data)} мастер-классов")
        return data
    except Exception as e:
        print(f"❌ Ошибка загрузки таблицы: {e}")
        return []

def find_mk(category, limit=3, exclude_ids=None):
    data = load_mk_data()
    exclude_ids = exclude_ids or []
    filtered = [item for item in data if item["category"].lower() == category.lower() and item["link"] not in exclude_ids]
    return random.sample(filtered, limit) if len(filtered) > limit else filtered

def format_card(mk, number=1):
    lines = [f"<b>{number}. {mk['name']}</b>", f"Категория: {mk['category']}", ""]
    if mk.get('link'):
        lines.append(f"🔗 <a href='{mk['link']}'>Пост в канале</a>")
    return "\n".join(lines)

def log_action(user_id, username, action, category=""):
    record = {"time": datetime.now().isoformat(), "user_id": user_id, "username": username, "action": action, "category": category}
    records = []
    if os.path.exists(ANALYTICS_FILE):
        try:
            with open(ANALYTICS_FILE, 'r', encoding='utf-8') as f: records = json.load(f)
        except: records = []
    records.append(record)
    with open(ANALYTICS_FILE, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

# ================= МЕНЮ =================
def get_main_keyboard():
    categories = [
        ("🍳 Кулинария", "Кулинария"), ("🎨 Арт", "Арт"), ("🧶 Рукоделие", "Рукоделие"),
        ("🏺 Керамика", "Керамика"), ("💎 Ювелирка", "Ювелирка"), ("🌸 Флористика", "Флористика"),
        ("🎭 Необычное", "Необычное"), ("💃 Танцы", "Танцы"), ("🎵 Музыка", "Музыка"),
        ("📸 Фото", "Фото"), ("👶 Детский", "Детский"), ("📋 Разное", "Разное"),
    ]
    # Делаем по 2 кнопки в ряд для компактности (как вы просили)
    buttons = []
    for i in range(0, len(categories), 2):
        row = [InlineKeyboardButton(text=categories[i][0], callback_data=f"cat_{categories[i][1]}")]
        if i + 1 < len(categories):
            row.append(InlineKeyboardButton(text=categories[i+1][0], callback_data=f"cat_{categories[i+1][1]}"))
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ================= ОБРАБОТЧИКИ =================
@router.message(CommandStart())
async def cmd_start(message: Message):
    log_action(message.from_user.id, message.from_user.username or "", "start")
    await message.answer("👋 <b>Привет!</b>\n\nЯ помогу подобрать мастер-класс в Москве.\n\n<b>Выберите категорию:</b>", reply_markup=get_main_keyboard(), parse_mode="HTML")

@router.callback_query(F.data.startswith("cat_"))
async def show_category(callback: CallbackQuery):
    category = callback.data.split("_", 1)[1]
    log_action(callback.from_user.id, callback.from_user.username or "", "category", category)
    results = find_mk(category, limit=3)
    
    if not results:
        await callback.message.answer(f"😔 В категории «{category}» пока нет МК.\n\nПопробуйте другую или нажмите /random", parse_mode="HTML")
        return
    
    parts = [f"<b>🎯 Категория «{category}»:</b>\n"]
    shown_links = []
    for i, mk in enumerate(results, 1):
        parts.append(format_card(mk, i))
        parts.append("─" * 30)
        shown_links.append(mk['link'])
        log_action(callback.from_user.id, callback.from_user.username or "", "view", category)
    
    links_str = "|".join(shown_links)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Ещё варианты", callback_data=f"more_{category}_{links_str}")],
        [InlineKeyboardButton(text="🎲 Случайный", callback_data="random")],
        [InlineKeyboardButton(text="🔁 В меню", callback_data="start")],
    ])
    await callback.message.answer("\n".join(parts), reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)

@router.callback_query(F.data.startswith("more_"))
async def show_more(callback: CallbackQuery):
    data = callback.data[5:]
    parts = data.split("_", 1)
    category = parts[0]
    shown_links = parts[1].split("|") if len(parts) > 1 else []
    
    results = find_mk(category, limit=3, exclude_ids=shown_links)
    if not results:
        await callback.answer("Больше МК в этой категории нет 😔", show_alert=True)
        return
    
    new_parts = [f"<b>🔄 Ещё из «{category}»:</b>\n"]
    new_links = []
    for i, mk in enumerate(results, 1):
        new_parts.append(format_card(mk, i))
        new_parts.append("─" * 30)
        new_links.append(mk['link'])
        log_action(callback.from_user.id, callback.from_user.username or "", "view", category)
    
    all_links = shown_links + new_links
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Ещё", callback_data=f"more_{category}_{'|'.join(all_links)}")],
        [InlineKeyboardButton(text="🔁 В меню", callback_data="start")],
    ])
    await callback.message.answer("\n".join(new_parts), reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)

@router.callback_query(F.data == "random")
@router.message(Command("random"))
async def random_mk(target):
    data = load_mk_data()
    if not data:
        text = "😔 Пока нет МК в базе."
    else:
        mk = random.choice(data)
        text = "<b>🎲 Случайный МК:</b>\n\n" + format_card(mk, 1)
        log_action(target.from_user.id, target.from_user.username or "", "random")
    
    if isinstance(target, CallbackQuery):
        await target.message.answer(text, parse_mode="HTML", disable_web_page_preview=True)
    else:
        await target.answer(text, parse_mode="HTML", disable_web_page_preview=True)

@router.callback_query(F.data == "start")
async def go_start(callback: CallbackQuery):
    await callback.message.delete()
    await cmd_start(callback.message)

# ================= ЗАПУСК =================
async def main():
    print("✅ Бот успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
