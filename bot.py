# -*- coding: utf-8 -*-
import os, json, random, csv, urllib.request, time
from datetime import datetime
import gspread
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# ================= НАСТРОЙКИ =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
SHEET_CSV_URL = os.getenv("SHEET_CSV_URL")
ANALYTICS_SPREADSHEET_ID = os.getenv("ANALYTICS_SPREADSHEET_ID")
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS")
FAVORITES_FILE = "favorites.json"

session = AiohttpSession()
bot = Bot(token=BOT_TOKEN, session=session)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# Google Sheets для аналитики
gc = None
sheet = None
if GOOGLE_CREDENTIALS and ANALYTICS_SPREADSHEET_ID:
    try:
        credentials_dict = json.loads(GOOGLE_CREDENTIALS)
        gc = gspread.service_account_from_dict(credentials_dict)
        sheet = gc.open_by_key(ANALYTICS_SPREADSHEET_ID).sheet1
        print("✅ Google Sheets подключен для аналитики!")
    except Exception as e:
        print(f"⚠️ Ошибка подключения к Google Sheets: {e}")

# Сессии пользователей (в памяти)
user_sessions = {}

# ================= АНАЛИТИКА =================
def get_session_info(user_id):
    now = time.time()
    if user_id in user_sessions:
        sess = user_sessions[user_id]
        if now - sess['last_activity'] > 1800:
            sess['session_id'] = f"sess_{user_id}_{int(now)}"
            sess['start_time'] = now
        sess['last_activity'] = now
    else:
        sess = {
            'session_id': f"sess_{user_id}_{int(now)}",
            'start_time': now,
            'last_activity': now
        }
        user_sessions[user_id] = sess
    return sess

def log_to_sheet(user_id, username, action, category="", mk_id=""):
    if not sheet:
        return
    sess = get_session_info(user_id)
    duration = int(time.time() - sess['start_time'])
    funnel_map = {
        'start': '1_start',
        'category': '2_category',
        'view': '3_view',
        'link_click': '4_click',
        'random': 'random',
        'favorite_add': 'favorite',
        'favorite_remove': 'favorite',
        'favorites_view': 'favorite'
    }
    funnel_step = funnel_map.get(action, action)
    row = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        str(user_id),
        username or "",
        action,
        category,
        mk_id,
        sess['session_id'],
        duration,
        funnel_step
    ]
    try:
        sheet.append_row(row, value_input_option="USER_ENTERED")
    except Exception as e:
        print(f"⚠️ Ошибка записи в Google Sheets: {e}")

# ================= ИЗБРАННОЕ =================
def load_favorites():
    if os.path.exists(FAVORITES_FILE):
        try:
            with open(FAVORITES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_favorites(favorites):
    with open(FAVORITES_FILE, 'w', encoding='utf-8') as f:
        json.dump(favorites, f, ensure_ascii=False, indent=2)

def add_favorite(user_id, mk_link):
    favorites = load_favorites()
    if str(user_id) not in favorites:
        favorites[str(user_id)] = []
    if mk_link not in favorites[str(user_id)]:
        favorites[str(user_id)].append(mk_link)
        save_favorites(favorites)
        return True
    return False

def remove_favorite(user_id, mk_link):
    favorites = load_favorites()
    if str(user_id) in favorites and mk_link in favorites[str(user_id)]:
        favorites[str(user_id)].remove(mk_link)
        save_favorites(favorites)
        return True
    return False

def get_user_favorites(user_id):
    favorites = load_favorites()
    return favorites.get(str(user_id), [])

# ================= ДАННЫЕ МК =================
def load_mk_data():
    try:
        req = urllib.request.Request(SHEET_CSV_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as response:
            csv_data = response.read().decode('utf-8')
        first_line = csv_data.split('\n')[0]
        delimiter = ';' if ';' in first_line else ','
        reader = csv.DictReader(csv_data.splitlines(), delimiter=delimiter)
        print(f"🔍 DEBUG: Заголовки таблицы: {reader.fieldnames}")
        data = []
        for row in reader:
            try:
                clean_row = {k.strip().lower(): (v.strip() if v else "") for k, v in row.items() if k}
                name = clean_row.get('name', '')
                category = clean_row.get('category', '')
                if not name or not category:
                    continue
                data.append({
                    "link": clean_row.get('link', '') or clean_row.get('tglink', ''),
                    "name": name,
                    "category": category,
                    "metro": clean_row.get('metro', ''),
                    "price": clean_row.get('price', ''),
                    "feature": clean_row.get('feature', '') or clean_row.get('фишка', ''),
                    "advantages": clean_row.get('advantages', '') or clean_row.get('плюсы', ''),
                    "disadvantages": clean_row.get('disadvantages', '') or clean_row.get('минусы', ''),
                    "best_reason": clean_row.get('best_reason', '') or clean_row.get('идеально для', ''),
                    "participants": clean_row.get('participants', ''),
                    "periodicity": clean_row.get('periodicity', ''),
                    "public_page": clean_row.get('public_page', '') or clean_row.get('сайт', '')
                })
            except:
                continue
        print(f"✅ DEBUG: Загружено {len(data)} мастер-классов")
        return data
    except Exception as e:
        print(f"❌ Ошибка загрузки таблицы: {e}")
        return []

def get_mk_by_category(category):
    data = load_mk_data()
    return [item for item in data if item["category"].lower() == category.lower()]

def get_mk_by_link(link):
    data = load_mk_data()
    for mk in data:
        if mk['link'] == link:
            return mk
    return None

def format_card(mk, number=1):
    card = []
    card.append(f"<b>{number}. {mk['name']}</b>")
    card.append(f"Категория: {mk['category']}")
    card.append("")
    if mk.get('metro'):
        card.append(f"🚇 <b>Метро:</b> {mk['metro']}")
    if mk.get('price'):
        card.append(f"💰 <b>Цена:</b> {mk['price']}")
    if mk.get('participants'):
        card.append(f"👥 <b>Участников:</b> до {mk['participants']} чел.")
    if mk.get('periodicity'):
        card.append(f"📅 <b>Периодичность:</b> {mk['periodicity']}")
    card.append("")
    if mk.get('feature'):
        card.append(f"✨ <b>Фишка:</b> {mk['feature']}")
    if mk.get('advantages'):
        card.append(f"✅ <b>Плюсы:</b> {mk['advantages']}")
    if mk.get('disadvantages'):
        card.append(f"⚠️ <b>Минусы:</b> {mk['disadvantages']}")
    if mk.get('best_reason'):
        card.append(f"💡 <b>Идеально для:</b> {mk['best_reason']}")
    card.append("")
    card.append("⚠️ <i>Проверьте актуальность перед записью!</i>")
    links = []
    if mk.get('link'):
        links.append(f"🔗 <a href='{mk['link']}'>Пост в канале</a>")
    if mk.get('public_page') and mk['public_page'] not in ['#', '', 'нет ссылки']:
        links.append(f"🌐 <a href='{mk['public_page']}'>Сайт</a>")
    if links:
        card.append(" | ".join(links))
    return "\n".join(card)

# ================= МЕНЮ =================
def get_main_keyboard():
    categories = [
        ("🍳 Кулинария", "Кулинария"),
        ("🎨 Арт", "Арт"),
        ("🧶 Рукоделие", "Рукоделие"),
        ("🏺 Керамика", "Керамика"),
        ("💎 Ювелирка", "Ювелирка"),
        ("🌸 Флористика", "Флористика"),
        ("🎭 Необычное", "Необычное"),
        ("💃 Танцы", "Танцы"),
        ("🎵 Музыка", "Музыка"),
        ("📸 Фото", "Фото"),
        ("👶 Детский", "Детский"),
        ("📋 Разное", "Разное"),
    ]
    buttons = []
    for i in range(0, len(categories), 2):
        row = [InlineKeyboardButton(text=categories[i][0], callback_data=f"cat_{categories[i][1]}")]
        if i + 1 < len(categories):
            row.append(InlineKeyboardButton(text=categories[i+1][0], callback_data=f"cat_{categories[i+1][1]}"))
        buttons.append(row)
    buttons.append([
        InlineKeyboardButton(text="🎲 Случайный", callback_data="random"),
        InlineKeyboardButton(text="❤️ Избранное", callback_data="show_fav")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_card_keyboard(mk, user_id):
    favorites = get_user_favorites(user_id)
    is_fav = mk['link'] in favorites
    fav_text = "💔 Убрать из избранного" if is_fav else "❤️ В избранное"
    fav_action = f"fav_remove_{mk['link']}" if is_fav else f"fav_add_{mk['link']}"
    
    buttons = [
        [InlineKeyboardButton(text=fav_text, callback_data=fav_action)],
        [InlineKeyboardButton(text="📋 В меню", callback_data="start")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# Прогресс пользователя: какие МК уже показаны в каждой категории
user_progress = {}

def get_user_progress(user_id, category):
    key = f"{user_id}_{category}"
    if key not in user_progress:
        user_progress[key] = []
    return user_progress[key]

def add_to_progress(user_id, category, links):
    key = f"{user_id}_{category}"
    if key not in user_progress:
        user_progress[key] = []
    user_progress[key].extend(links)

# ================= ОБРАБОТЧИКИ =================

@router.message(CommandStart())
async def cmd_start(message: Message):
    log_to_sheet(message.from_user.id, message.from_user.username, "start")
    await message.answer(
        "👋 <b>Привет!</b>\n\n"
        "Я помогу подобрать мастер-класс в Москве.\n\n"
        "<b>Выберите категорию:</b>",
        reply_markup=get_main_keyboard(),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("cat_"))
async def show_category(callback: CallbackQuery):
    category = callback.data.split("_", 1)[1]
    log_to_sheet(callback.from_user.id, callback.from_user.username, "category", category)
    
    shown_links = get_user_progress(callback.from_user.id, category)
    all_mks = get_mk_by_category(category)
    available = [mk for mk in all_mks if mk['link'] not in shown_links]
    
    if not available:
        user_progress[f"{callback.from_user.id}_{category}"] = []
        available = all_mks
    
    if not available:
        await callback.message.answer(
            f"😔 В категории «{category}» пока нет МК.\n\n"
            f"Попробуйте другую категорию или нажмите /random",
            parse_mode="HTML"
        )
        return
    
    to_show = available[:3]
    shown_links_new = [mk['link'] for mk in to_show]
    add_to_progress(callback.from_user.id, category, shown_links_new)
    
    parts = [f"<b>🎯 Категория «{category}»:</b>\n"]
    for i, mk in enumerate(to_show, 1):
        parts.append(format_card(mk, i))
        parts.append("─" * 40)
        log_to_sheet(callback.from_user.id, callback.from_user.username, "view", category, mk['link'])
    
    last_mk = to_show[-1]
    kb = get_card_keyboard(last_mk, callback.from_user.id)
    
    nav_buttons = []
    if len(available) > 3:
        nav_buttons.append([InlineKeyboardButton(text="🔄 Ещё варианты", callback_data=f"more_{category}")])
    nav_buttons.append([
        InlineKeyboardButton(text="🎲 Случайный", callback_data="random"),
        InlineKeyboardButton(text="📋 В меню", callback_data="start")
    ])
    
    all_buttons = kb.inline_keyboard[:-1] + nav_buttons
    final_kb = InlineKeyboardMarkup(inline_keyboard=all_buttons)
    
    await callback.message.answer("\n".join(parts), reply_markup=final_kb, parse_mode="HTML", disable_web_page_preview=True)

@router.callback_query(F.data.startswith("more_"))
async def show_more(callback: CallbackQuery):
    category = callback.data.split("_", 1)[1]
    shown_links = get_user_progress(callback.from_user.id, category)
    all_mks = get_mk_by_category(category)
    available = [mk for mk in all_mks if mk['link'] not in shown_links]
    
    if not available:
        await callback.answer("Больше МК в этой категории нет 😔", show_alert=True)
        return
    
    to_show = available[:3]
    shown_links_new = [mk['link'] for mk in to_show]
    add_to_progress(callback.from_user.id, category, shown_links_new)
    
    parts = [f"<b>🔄 Ещё из «{category}»:</b>\n"]
    for i, mk in enumerate(to_show, 1):
        parts.append(format_card(mk, i))
        parts.append("─" * 40)
        log_to_sheet(callback.from_user.id, callback.from_user.username, "view", category, mk['link'])
    
    last_mk = to_show[-1]
    kb = get_card_keyboard(last_mk, callback.from_user.id)
    
    nav_buttons = []
    remaining = [mk for mk in all_mks if mk['link'] not in shown_links + shown_links_new]
    if remaining:
        nav_buttons.append([InlineKeyboardButton(text="🔄 Ещё", callback_data=f"more_{category}")])
    nav_buttons.append([
        InlineKeyboardButton(text="🎲 Случайный", callback_data="random"),
        InlineKeyboardButton(text="📋 В меню", callback_data="start")
    ])
    
    all_buttons = kb.inline_keyboard[:-1] + nav_buttons
    final_kb = InlineKeyboardMarkup(inline_keyboard=all_buttons)
    
    await callback.message.answer("\n".join(parts), reply_markup=final_kb, parse_mode="HTML", disable_web_page_preview=True)

@router.callback_query(F.data.startswith("fav_add_"))
async def add_to_favorites(callback: CallbackQuery):
    link = callback.data.split("fav_add_", 1)[1]
    mk = get_mk_by_link(link)
    if add_favorite(callback.from_user.id, link):
        log_to_sheet(callback.from_user.id, callback.from_user.username, "favorite_add", mk['category'] if mk else "", link)
        await callback.answer("❤️ Добавлено в избранное!", show_alert=False)
        if mk:
            new_kb = get_card_keyboard(mk, callback.from_user.id)
            await callback.message.edit_reply_markup(reply_markup=new_kb)
    else:
        await callback.answer("Уже в избранном", show_alert=True)

@router.callback_query(F.data.startswith("fav_remove_"))
async def remove_from_favorites(callback: CallbackQuery):
    link = callback.data.split("fav_remove_", 1)[1]
    mk = get_mk_by_link(link)
    if remove_favorite(callback.from_user.id, link):
        log_to_sheet(callback.from_user.id, callback.from_user.username, "favorite_remove", mk['category'] if mk else "", link)
        await callback.answer("💔 Удалено из избранного", show_alert=False)
        if mk:
            new_kb = get_card_keyboard(mk, callback.from_user.id)
            await callback.message.edit_reply_markup(reply_markup=new_kb)
    else:
        await callback.answer("Не найдено в избранном", show_alert=True)

@router.callback_query(F.data == "show_fav")
async def show_favorites(callback: CallbackQuery):
    log_to_sheet(callback.from_user.id, callback.from_user.username, "favorites_view")
    favorites_links = get_user_favorites(callback.from_user.id)
    
    if not favorites_links:
        await callback.message.answer(
            "❤️ <b>Ваше избранное пусто</b>\n\n"
            "Нажимайте «❤️ В избранное» под карточками МК, чтобы сохранять понравившиеся.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 В меню", callback_data="start")]
            ])
        )
        return
    
    all_data = load_mk_data()
    favorites_mks = [mk for mk in all_data if mk['link'] in favorites_links]
    
    if not favorites_mks:
        await callback.message.answer(
            "❤️ <b>Ваше избранное</b>\n\n"
            "Сохранённые МК больше не доступны в базе.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 В меню", callback_data="start")]
            ])
        )
        return
    
    parts = ["<b>❤️ Ваше избранное:</b>\n"]
    for i, mk in enumerate(favorites_mks, 1):
        parts.append(format_card(mk, i))
        parts.append("─" * 40)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 В меню", callback_data="start")]
    ])
    
    await callback.message.answer("\n".join(parts), reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)

@router.callback_query(F.data == "random")
@router.message(Command("random"))
async def random_mk(target):
    data = load_mk_data()
    if not data:
        text = "😔 Пока нет МК в базе."
        if isinstance(target, CallbackQuery):
            await target.message.answer(text, parse_mode="HTML")
        else:
            await target.answer(text, parse_mode="HTML")
        return
    
    mk = random.choice(data)
    log_to_sheet(target.from_user.id, target.from_user.username, "random", mk['category'], mk['link'])
    
    text = "<b>🎲 Случайный МК:</b>\n\n" + format_card(mk, 1)
    kb = get_card_keyboard(mk, target.from_user.id)
    
    nav_buttons = [
        [InlineKeyboardButton(text="🎲 Ещё случайный", callback_data="random")],
        [InlineKeyboardButton(text="📋 В меню", callback_data="start")]
    ]
    all_buttons = kb.inline_keyboard[:-1] + nav_buttons
    final_kb = InlineKeyboardMarkup(inline_keyboard=all_buttons)
    
    if isinstance(target, CallbackQuery):
        await target.message.answer(text, reply_markup=final_kb, parse_mode="HTML", disable_web_page_preview=True)
    else:
        await target.answer(text, reply_markup=final_kb, parse_mode="HTML", disable_web_page_preview=True)

@router.callback_query(F.data == "start")
async def go_start(callback: CallbackQuery):
    await callback.message.delete()
    await cmd_start(callback.message)

@router.message(Command("stats"))
async def admin_stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    if not sheet:
        await message.answer("📊 Google Sheets не подключен.")
        return
    
    try:
        records = sheet.get_all_records()
    except Exception as e:
        await message.answer(f"❌ Ошибка чтения: {e}")
        return
    
    now = datetime.now()
    today = now.date()
    
    today_records = [r for r in records if r.get('timestamp') and datetime.strptime(str(r['timestamp'])[:19], "%Y-%m-%d %H:%M:%S").date() == today]
    total_users = len(set(r.get('user_id') for r in today_records if r.get('user_id')))
    starts = len([r for r in today_records if r.get('action') == 'start'])
    categories = len([r for r in today_records if r.get('action') == 'category'])
    views = len([r for r in today_records if r.get('action') == 'view'])
    
    cat_counts = {}
    for r in records:
        if r.get('action') == 'category' and r.get('category'):
            cat = r['category']
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
    top_cats = sorted(cat_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    
    stats_text = (
        f"📊 <b>Статистика за сегодня:</b>\n\n"
        f"👥 Уникальных пользователей: {total_users}\n"
        f"🚀 /start: {starts}\n"
        f"📂 Выбор категории: {categories}\n"
        f"👁 Просмотров карточек: {views}\n\n"
        f"🔥 <b>Топ категорий (всего):</b>\n"
    )
    for cat, count in top_cats:
        stats_text += f"  • {cat}: {count}\n"
    
    await message.answer(stats_text, parse_mode="HTML")

# ================= ЗАПУСК =================
async def main():
    print("✅ Бот успешно запущен с аналитикой в Google Sheets!")
    print(f"📊 Таблица аналитики: {ANALYTICS_SPREADSHEET_ID}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
