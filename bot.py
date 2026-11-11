# -*- coding: utf-8 -*-
import os, json, random, csv, urllib.request, time
from datetime import datetime
import gspread
from aiogram import Bot, Dispatcher, F, Router, Update
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.exceptions import TelegramForbiddenError

# ================= НАСТРОЙКИ =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
SHEET_CSV_URL = os.getenv("SHEET_CSV_URL")
ANALYTICS_SPREADSHEET_ID = os.getenv("ANALYTICS_SPREADSHEET_ID")
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS")
FAVORITES_FILE = "favorites.json"
USER_STATS_FILE = "user_stats.json"

session = AiohttpSession()
bot = Bot(token=BOT_TOKEN, session=session)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# ================= GOOGLE SHEETS ИНИЦИАЛИЗАЦИЯ =================
gc = None
sheet = None
if GOOGLE_CREDENTIALS and ANALYTICS_SPREADSHEET_ID:
    try:
        creds_dict = json.loads(GOOGLE_CREDENTIALS)
        gc = gspread.service_account_from_dict(creds_dict)
        sheet = gc.open_by_key(ANALYTICS_SPREADSHEET_ID).sheet1
        print("✅ Google Sheets подключен для аналитики!")
    except Exception as e:
        print(f"⚠️ Ошибка подключения к Google Sheets: {e}")

# ================= СОСТОЯНИЯ И СТАТИСТИКА =================
user_state = {}
user_sessions = {}

def get_user_stats(user_id, action):
    """Отслеживает is_new_user и visit_count (увеличивается только при /start)"""
    stats = {}
    if os.path.exists(USER_STATS_FILE):
        try:
            with open(USER_STATS_FILE, 'r', encoding='utf-8') as f:
                stats = json.load(f)
        except:
            stats = {}
    
    user_str = str(user_id)
    is_new = user_str not in stats
    
    if action == 'start':
        if is_new:
            stats[user_str] = {"visit_count": 1, "first_seen": datetime.now().strftime("%Y-%m-%d")}
        else:
            stats[user_str]["visit_count"] += 1
        
        with open(USER_STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
            
    current_visits = stats.get(user_str, {}).get("visit_count", 1)
    return is_new, current_visits

def get_session_info(user_id):
    """Управляет сессиями (30 минут неактивности = новая сессия)"""
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
    """Записывает строку в Google Таблицу (ровно 11 столбцов)"""
    if not sheet:
        return
    
    sess = get_session_info(user_id)
    duration = int(time.time() - sess['start_time'])
    is_new, visit_count = get_user_stats(user_id, action)
    
    funnel_map = {
        'start': '1_start', 'category': '2_category', 'view': '3_view',
        'link_click': '4_click', 'random': 'random', 'favorite_add': 'favorite',
        'favorite_remove': 'favorite', 'favorites_view': 'favorite', 'favorites_clear': 'favorite', 'blocked': 'blocked'
    }
    funnel_step = funnel_map.get(action, action)
    
    row = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"), # timestamp
        str(user_id),                                  # user_id
        username or "",                                # username
        action,                                        # action
        category if category else "",                  # category
        mk_id if mk_id else "",                        # mk_id
        sess['session_id'],                            # session_id
        duration,                                      # session_duration
        "TRUE" if is_new else "FALSE",                 # is_new_user
        funnel_step,                                   # funnel_step
        visit_count                                    # visit_count
    ]
    
    try:
        sheet.append_row(row, value_input_option="USER_ENTERED")
    except Exception as e:
        print(f"⚠️ Ошибка записи в Google Sheets: {e}")

# ================= ИЗБРАННОЕ =================
def load_favorites():
    if os.path.exists(FAVORITES_FILE):
        try:
            with open(FAVORITES_FILE, 'r', encoding='utf-8') as f: return json.load(f)
        except: return {}
    return {}

def save_favorites(favorites):
    with open(FAVORITES_FILE, 'w', encoding='utf-8') as f:
        json.dump(favorites, f, ensure_ascii=False, indent=2)

def add_favorite(user_id, mk_link):
    favorites = load_favorites()
    if str(user_id) not in favorites: favorites[str(user_id)] = []
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

def clear_favorites(user_id):
    favorites = load_favorites()
    if str(user_id) in favorites:
        del favorites[str(user_id)]
        save_favorites(favorites)
        return True
    return False

def get_user_favorites(user_id):
    return load_favorites().get(str(user_id), [])

def is_favorite(user_id, mk_link):
    return mk_link in get_user_favorites(user_id)

# ================= ДАННЫЕ МК =================
def load_mk_data():
    try:
        req = urllib.request.Request(SHEET_CSV_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as response:
            csv_data = response.read().decode('utf-8')
        first_line = csv_data.split('\n')[0]
        delimiter = ';' if ';' in first_line else ','
        reader = csv.DictReader(csv_data.splitlines(), delimiter=delimiter)
        data = []
        for row in reader:
            try:
                clean_row = {k.strip().lower(): (v.strip() if v else "") for k, v in row.items() if k}
                name = clean_row.get('name', '')
                category = clean_row.get('category', '')
                if not name or not category: continue
                
                priority = clean_row.get('priority', '1')
                try: priority = int(priority)
                except: priority = 1
                
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
                    "public_page": clean_row.get('public_page', '') or clean_row.get('сайт', ''),
                    "preposition": clean_row.get('preposition', ''),
                    "priority": priority
                })
            except: continue
        return data
    except Exception as e:
        print(f"❌ Ошибка загрузки таблицы: {e}")
        return []

def get_mk_by_category(category):
    return [item for item in load_mk_data() if item["category"].lower() == category.lower()]

def get_mk_by_link(link):
    for mk in load_mk_data():
        if mk['link'] == link: return mk
    return None

def weighted_random_choice(items, k=3, exclude_links=None):
    if not items: return []
    exclude_links = exclude_links or []
    available = [item for item in items if item['link'] not in exclude_links]
    if not available: return []
    
    pool = []
    for item in available:
        pool.extend([item] * item.get('priority', 1))
    
    selected, used_links = [], set()
    for _ in range(min(k, len(available))):
        available_pool = [item for item in pool if item['link'] not in used_links]
        if not available_pool: break
        chosen = random.choice(available_pool)
        selected.append(chosen)
        used_links.add(chosen['link'])
    return selected

def format_card(mk, number=1, total=1):
    card = [f"<b>{number} из {total}</b>", f"<b>{mk['name']}</b>", f"Категория: {mk['category']}", ""]
    if mk.get('preposition'):
        card.extend([f"💬 <i>{mk['preposition']}</i>", ""])
    if mk.get('metro'): card.append(f"🚇 <b>Метро:</b> {mk['metro']}")
    if mk.get('price'): card.append(f"💰 <b>Цена:</b> {mk['price']}")
    if mk.get('participants'): card.append(f"👥 <b>Участников:</b> до {mk['participants']} чел.")
    if mk.get('periodicity'): card.append(f"📅 <b>Периодичность:</b> {mk['periodicity']}")
    card.append("")
    if mk.get('feature'): card.append(f"✨ <b>Фишка:</b> {mk['feature']}")
    if mk.get('advantages'): card.append(f"✅ <b>Плюсы:</b> {mk['advantages']}")
    if mk.get('disadvantages'): card.append(f"⚠️ <b>Минусы:</b> {mk['disadvantages']}")
    if mk.get('best_reason'): card.append(f"💡 <b>Идеально для:</b> {mk['best_reason']}")
    card.extend(["", "⚠️ <i>Проверьте актуальность перед записью!</i>"])
    
    links = []
    if mk.get('link'): links.append(f"🔗 <a href='{mk['link']}'>Пост в канале</a>")
    if mk.get('public_page') and mk['public_page'] not in ['#', '', 'нет ссылки']:
        links.append(f"🌐 <a href='{mk['public_page']}'>Сайт</a>")
    if links: card.append(" | ".join(links))
    return "\n".join(card)

# ================= МЕНЮ =================
def get_main_keyboard():
    categories = [
        ("🍳 Кулинария", "Кулинария"), ("🎨 Арт", "Арт"), ("🧶 Рукоделие", "Рукоделие"),
        ("🏺 Керамика", "Керамика"), ("💎 Ювелирка", "Ювелирка"), ("🌸 Флористика", "Флористика"),
        ("🎭 Необычное", "Необычное"), ("💃 Танцы", "Танцы"), ("🎵 Музыка", "Музыка"),
        ("📸 Фото", "Фото"), ("👶 Детский", "Детский"), ("📋 Разное", "Разное"),
    ]
    buttons = []
    for i in range(0, len(categories), 2):
        row = [InlineKeyboardButton(text=categories[i][0], callback_data=f"cat_{categories[i][1]}")]
        if i + 1 < len(categories):
            row.append(InlineKeyboardButton(text=categories[i+1][0], callback_data=f"cat_{categories[i+1][1]}"))
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🎲 Случайный", callback_data="random"), InlineKeyboardButton(text="❤️ Избранное", callback_data="show_fav")])
    buttons.append([InlineKeyboardButton(text="❓ Помощь", callback_data="help")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_card_keyboard(user_id, mk, current_index, total_in_batch, has_next, has_more, category, from_fav=False):
    fav_status = is_favorite(user_id, mk['link'])
    fav_text = "💔 Убрать из избранного" if fav_status else "❤️ В избранное"
    fav_action = f"fav_remove_{mk['link']}" if fav_status else f"fav_add_{mk['link']}"
    
    buttons = []
    nav_row = []
    if current_index > 0: nav_row.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"nav_{category}_{current_index - 1}"))
    if has_next: nav_row.append(InlineKeyboardButton(text="▶️ Вперёд", callback_data=f"nav_{category}_{current_index + 1}"))
    elif has_more: nav_row.append(InlineKeyboardButton(text="🔄 Ещё подборку", callback_data=f"new_batch_{category}"))
    if nav_row: buttons.append(nav_row)
    
    buttons.append([InlineKeyboardButton(text=fav_text, callback_data=fav_action)])
    buttons.append([InlineKeyboardButton(text="📋 К списку избранного" if from_fav else "📋 В главное меню", callback_data="show_fav" if from_fav else "start")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ================= ОБРАБОТЧИКИ =================
@router.message(CommandStart())
async def cmd_start(message: Message):
    log_to_sheet(message.from_user.id, message.from_user.username, "start")
    await message.answer("👋 <b>Привет!</b>\n\nЯ помогу подобрать мастер-класс в Москве.\n\n<b>Выберите категорию:</b>", reply_markup=get_main_keyboard(), parse_mode="HTML")

@router.message(Command("help"))
@router.callback_query(F.data == "help")
async def cmd_help(target):
    help_text = ("📖 <b>Как пользоваться ботом:</b>\n\n"
        "🍳 <b>Выбор категории</b> — нажмите на кнопку с нужной категорией\n"
        "🎯 <b>Просмотр МК</b> — бот покажет 1 карточку. Используйте ◀️ Назад и ▶️ Вперёд\n"
        "🔄 <b>Ещё подборку</b> — на последней карточке нажмите для новой тройки МК\n"
        "❤️ <b>Избранное</b> — сохраняйте понравившиеся МК и управляйте ими в главном меню\n"
        "🎲 <b>Случайный МК</b> — покажет случайный мастер-класс (с учётом приоритетов)\n"
        "⚠️ <i>Проверяйте актуальность МК перед записью!</i>")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 В главное меню", callback_data="start")]])
    if isinstance(target, CallbackQuery):
        await target.message.answer(help_text, reply_markup=kb, parse_mode="HTML")
        await target.answer()
    else:
        await target.answer(help_text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("cat_"))
async def show_category(callback: CallbackQuery):
    category = callback.data.split("_", 1)[1]
    log_to_sheet(callback.from_user.id, callback.from_user.username, "category", category)
    all_mks = get_mk_by_category(category)
    if not all_mks:
        await callback.message.answer(f"😔 В категории «{category}» пока нет МК.\n\nПопробуйте другую или нажмите /random", parse_mode="HTML")
        return
    
    selected = weighted_random_choice(all_mks, k=3)
    user_state[callback.from_user.id] = {'category': category, 'index': 0, 'mks': selected, 'all_mks': all_mks, 'shown_links': [mk['link'] for mk in selected], 'from_favorites': False}
    
    mk = selected[0]
    log_to_sheet(callback.from_user.id, callback.from_user.username, "view", category, mk['link'])
    has_next = len(selected) > 1
    has_more = len(all_mks) > len(selected)
    
    await callback.message.answer(format_card(mk, 1, len(selected)), reply_markup=get_card_keyboard(callback.from_user.id, mk, 0, len(selected), has_next, has_more, category, False), parse_mode="HTML", disable_web_page_preview=True)

@router.callback_query(F.data.startswith("nav_"))
async def navigate_card(callback: CallbackQuery):
    data = callback.data[4:]
    parts = data.rsplit("_", 1)
    category, new_index = parts[0], int(parts[1])
    
    if callback.from_user.id not in user_state or user_state[callback.from_user.id]['category'] != category:
        return await callback.answer("Сессия истекла, выберите категорию заново", show_alert=True)
    
    state = user_state[callback.from_user.id]
    if new_index < 0 or new_index >= len(state['mks']):
        return await callback.answer("Больше нет карточек", show_alert=True)
    
    state['index'] = new_index
    mk = state['mks'][new_index]
    log_to_sheet(callback.from_user.id, callback.from_user.username, "view", category, mk['link'])
    
    has_next = new_index < len(state['mks']) - 1
    has_more = len(state['all_mks']) > len(state['shown_links'])
    
    await callback.message.edit_text(format_card(mk, new_index + 1, len(state['mks'])), reply_markup=get_card_keyboard(callback.from_user.id, mk, new_index, len(state['mks']), has_next, has_more, category, state['from_favorites']), parse_mode="HTML", disable_web_page_preview=True)
    await callback.answer()

@router.callback_query(F.data.startswith("new_batch_"))
async def new_batch(callback: CallbackQuery):
    category = callback.data.split("new_batch_", 1)[1]
    if callback.from_user.id not in user_state: return await callback.answer("Сессия истекла", show_alert=True)
    
    state = user_state[callback.from_user.id]
    available = [mk for mk in state['all_mks'] if mk['link'] not in state['shown_links']]
    if not available:
        available, state['shown_links'] = state['all_mks'], []
    
    selected = weighted_random_choice(available, k=3)
    if not selected: return await callback.answer("Больше МК нет 😔", show_alert=True)
    
    state['mks'], state['index'] = selected, 0
    state['shown_links'].extend([mk['link'] for mk in selected])
    mk = selected[0]
    log_to_sheet(callback.from_user.id, callback.from_user.username, "view", category, mk['link'])
    
    has_next = len(selected) > 1
    has_more = len(state['all_mks']) > len(state['shown_links'])
    
    await callback.message.edit_text(format_card(mk, 1, len(selected)), reply_markup=get_card_keyboard(callback.from_user.id, mk, 0, len(selected), has_next, has_more, category, False), parse_mode="HTML", disable_web_page_preview=True)
    await callback.answer()

@router.callback_query(F.data.startswith("fav_add_"))
async def add_to_favorites(callback: CallbackQuery):
    link = callback.data.split("fav_add_", 1)[1]
    mk = get_mk_by_link(link)
    if add_favorite(callback.from_user.id, link):
        log_to_sheet(callback.from_user.id, callback.from_user.username, "favorite_add", mk['category'] if mk else "", link)
        await callback.answer("❤️ Добавлено в избранное!", show_alert=False)
        if callback.from_user.id in user_state:
            state = user_state[callback.from_user.id]
            await callback.message.edit_reply_markup(reply_markup=get_card_keyboard(callback.from_user.id, mk, state['index'], len(state['mks']), state['index'] < len(state['mks']) - 1, len(state['all_mks']) > len(state['shown_links']), state['category'], state['from_favorites']))
    else:
        await callback.answer("Уже в избранном", show_alert=True)

@router.callback_query(F.data.startswith("fav_remove_"))
async def remove_from_favorites(callback: CallbackQuery):
    link = callback.data.split("fav_remove_", 1)[1]
    mk = get_mk_by_link(link)
    if remove_favorite(callback.from_user.id, link):
        log_to_sheet(callback.from_user.id, callback.from_user.username, "favorite_remove", mk['category'] if mk else "", link)
        await callback.answer("💔 Удалено из избранного", show_alert=False)
        if callback.from_user.id in user_state and user_state[callback.from_user.id].get('from_favorites'):
            await show_favorites_list(callback)
        elif callback.from_user.id in user_state:
            state = user_state[callback.from_user.id]
            await callback.message.edit_reply_markup(reply_markup=get_card_keyboard(callback.from_user.id, mk, state['index'], len(state['mks']), state['index'] < len(state['mks']) - 1, len(state['all_mks']) > len(state['shown_links']), state['category'], state['from_favorites']))
    else:
        await callback.answer("Не найдено в избранном", show_alert=True)

@router.callback_query(F.data == "show_fav")
async def show_favorites(callback: CallbackQuery):
    log_to_sheet(callback.from_user.id, callback.from_user.username, "favorites_view")
    await show_favorites_list(callback)

async def show_favorites_list(callback: CallbackQuery):
    fav_links = get_user_favorites(callback.from_user.id)
    if not fav_links:
        return await callback.message.answer("❤️ <b>Ваше избранное пусто</b>\n\nНажимайте «❤️ В избранное» под карточками.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 В главное меню", callback_data="start")]]))
    
    fav_mks = [mk for mk in load_mk_data() if mk['link'] in fav_links]
    if not fav_mks:
        return await callback.message.answer("❤️ <b>Ваше избранное</b>\n\nСохранённые МК больше не доступны в базе.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 В главное меню", callback_data="start")]]))
    
    parts, buttons = ["<b>❤️ Ваше избранное:</b>\n"], []
    for i, mk in enumerate(fav_mks, 1):
        parts.extend([f"<b>{i}. {mk['name']}</b>", f"   Категория: {mk['category']}", f"   🔗 <a href='{mk['link']}'>Ссылка</a>", ""])
        buttons.append([InlineKeyboardButton(text=f"🗑 Удалить #{i}", callback_data=f"fav_remove_{mk['link']}")])
    
    buttons.extend([[InlineKeyboardButton(text="🗑 Очистить всё избранное", callback_data="clear_fav")], [InlineKeyboardButton(text="📋 В главное меню", callback_data="start")]])
    
    user_state[callback.from_user.id] = {'category': 'favorites', 'index': 0, 'mks': fav_mks, 'all_mks': fav_mks, 'shown_links': [fav_mks[0]['link']], 'from_favorites': True}
    await callback.message.answer("\n".join(parts), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML", disable_web_page_preview=True)

@router.callback_query(F.data == "clear_fav")
async def clear_favorites_handler(callback: CallbackQuery):
    if clear_favorites(callback.from_user.id):
        log_to_sheet(callback.from_user.id, callback.from_user.username, "favorites_clear")
        await callback.answer("🗑 Избранное очищено!", show_alert=True)
        await show_favorites_list(callback)
    else:
        await callback.answer("Избранное уже пусто", show_alert=True)

@router.callback_query(F.data == "random")
@router.message(Command("random"))
async def random_mk(target):
    data = load_mk_data()
    if not data:
        text = "😔 Пока нет МК в базе."
        return await (target.message.answer if isinstance(target, CallbackQuery) else target.answer)(text, parse_mode="HTML")
    
    mk = weighted_random_choice(data, k=1)[0]
    log_to_sheet(target.from_user.id, target.from_user.username, "random", mk['category'], mk['link'])
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Ещё случайный", callback_data="random")],
        [InlineKeyboardButton(text="📋 В главное меню", callback_data="start")]
    ])
    text = "<b>🎲 Случайный МК:</b>\n\n" + format_card(mk, 1, 1)
    
    if isinstance(target, CallbackQuery):
        await target.message.answer(text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
    else:
        await target.answer(text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)

@router.callback_query(F.data == "start")
async def go_start(callback: CallbackQuery):
    await callback.message.delete()
    await cmd_start(callback.message)

@router.message(Command("stats"))
async def admin_stats(message: Message):
    if message.from_user.id != ADMIN_ID or not sheet:
        return
    
    try:
        records = sheet.get_all_records()
        if not records:
            await message.answer("📊 Таблица аналитики пуста.")
            return
            
        today = datetime.now().date()
        today_recs = []
        
        for r in records:
            ts = r.get('timestamp', '')
            try:
                rec_date = datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S").date()
            except:
                try:
                    rec_date = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + int(float(ts)) - 2).date()
                except:
                    continue
            
            if rec_date == today:
                today_recs.append(r)
        
        unique_users = len(set(r.get('user_id') for r in today_recs if r.get('user_id')))
        new_users = sum(1 for r in today_recs if str(r.get('is_new_user')).upper() == 'TRUE')
        returning_users = unique_users - new_users
        
        starts = sum(1 for r in today_recs if r.get('action') == 'start')
        views = sum(1 for r in today_recs if r.get('action') == 'view')
        random_clicks = sum(1 for r in today_recs if r.get('action') == 'random')
        favorites = sum(1 for r in today_recs if 'favorite' in str(r.get('action', '')))
        blocked = sum(1 for r in today_recs if r.get('action') == 'blocked')
        
        cat_counts = {}
        for r in records:
            cat = str(r.get('category', '')).strip()
            if r.get('action') == 'category' and cat and cat.lower() != 'none':
                cat_counts[cat] = cat_counts.get(cat, 0) + 1
                
        top_cats = sorted(cat_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        stats_text = (
            f"📊 <b>Статистика за сегодня:</b>\n\n"
            f"👥 Всего уникальных: {unique_users}\n"
            f"🆕 Новых пользователей: {new_users}\n"
            f"🔄 Вернувшихся: {returning_users}\n"
            f"🚫 Заблокировали бота: {blocked}\n\n"
            f"🚀 Команд /start: {starts}\n"
            f"👁 Просмотров карточек: {views}\n"
            f"🎲 Запросов 'Случайный': {random_clicks}\n"
            f"❤️ Действий с избранным: {favorites}\n\n"
            f"🔥 <b>Топ категорий (всего):</b>\n"
        )
        for cat, count in top_cats:
            stats_text += f"  • {cat}: {count}\n"
            
        await message.answer(stats_text, parse_mode="HTML")
        
    except Exception as e:
        await message.answer(f"❌ Ошибка чтения статистики: {e}")

# ================= ГЛОБАЛЬНЫЙ ОБРАБОТЧИК ОШИБОК =================
@dp.errors()
async def errors_handler(event: Update, exception: Exception):
    """Перехватывает ошибку блокировки бота пользователем"""
    if isinstance(exception, TelegramForbiddenError):
        try:
            user_id = event.event.from_user.id
            username = event.event.from_user.username or ""
            
            row = [
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                str(user_id), username, "blocked", "", "", "", 0, "FALSE", "blocked", 0
            ]
            if sheet:
                sheet.append_row(row, value_input_option="USER_ENTERED")
            print(f"⚠️ Пользователь {user_id} заблокировал бота. Записано в аналитику.")
        except Exception as e:
            print(f"Ошибка при записи blocked: {e}")
        return True
    
    print(f"❌ Неизвестная ошибка бота: {exception}")
    return True

# ================= ЗАПУСК =================
async def main():
    print("✅ Бот успешно запущен с Google Sheets аналитикой!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
