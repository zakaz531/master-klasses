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
FAVORITES_FILE = "favorites.json"

session = AiohttpSession()
bot = Bot(token=BOT_TOKEN, session=session)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# Хранилище состояния пользователей
user_state = {}

# ================= АНАЛИТИКА =================
def log_action(user_id, username, action, category="", mk_id=""):
    record = {
        "time": datetime.now().isoformat(),
        "user_id": user_id,
        "username": username,
        "action": action,
        "category": category,
        "mk_id": mk_id
    }
    records = []
    if os.path.exists(ANALYTICS_FILE):
        try:
            with open(ANALYTICS_FILE, 'r', encoding='utf-8') as f:
                records = json.load(f)
        except:
            records = []
    records.append(record)
    with open(ANALYTICS_FILE, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

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
                if not name or not category:
                    continue
                
                # Приоритет: если поле priority есть в таблице, используем его, иначе 1
                priority = clean_row.get('priority', '1')
                try:
                    priority = int(priority)
                except:
                    priority = 1
                
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
                    "priority": priority
                })
            except:
                continue
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

def weighted_random_choice(items, k=3):
    """Взвешенный случайный выбор с учётом приоритета"""
    if not items:
        return []
    
    # Создаём пул с учётом приоритета (МК с priority=3 попадает в пул 3 раза)
    pool = []
    for item in items:
        priority = item.get('priority', 1)
        pool.extend([item] * priority)
    
    # Выбираем k уникальных элементов
    selected = []
    used_links = set()
    
    for _ in range(k):
        if not pool:
            break
        
        # Фильтруем пул, исключая уже выбранные
        available_pool = [item for item in pool if item['link'] not in used_links]
        if not available_pool:
            break
        
        chosen = random.choice(available_pool)
        selected.append(chosen)
        used_links.add(chosen['link'])
    
    return selected

def format_card(mk, number=1, total=1):
    card = []
    card.append(f"<b>{number} из {total}</b>")
    card.append(f"<b>{mk['name']}</b>")
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

def get_card_navigation_keyboard(user_id, mk, current_index, total_count, category, is_from_favorites=False, has_more=False):
    """Клавиатура для навигации по карточкам"""
    fav_status = is_favorite(user_id, mk['link'])
    fav_text = "💔 Убрать" if fav_status else "❤️ В избранное"
    fav_action = f"fav_remove_{mk['link']}" if fav_status else f"fav_add_{mk['link']}"
    
    buttons = []
    
    # Кнопки навигации
    nav_row = []
    if current_index > 0:
        nav_row.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"nav_{category}_{current_index - 1}"))
    if current_index < total_count - 1:
        nav_row.append(InlineKeyboardButton(text="▶️ Вперёд", callback_data=f"nav_{category}_{current_index + 1}"))
    if nav_row:
        buttons.append(nav_row)
    
    # Кнопка "Ещё подборку" (если дошли до конца и есть ещё МК в категории)
    if current_index == total_count - 1 and has_more:
        buttons.append([InlineKeyboardButton(text="🔄 Ещё подборку", callback_data=f"new_batch_{category}")])
    
    # Кнопка избранного
    buttons.append([InlineKeyboardButton(text=fav_text, callback_data=fav_action)])
    
    # Кнопка "В меню"
    if is_from_favorites:
        buttons.append([InlineKeyboardButton(text="📋 К избранному", callback_data="show_fav")])
    else:
        buttons.append([InlineKeyboardButton(text="📋 В меню", callback_data="start")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ================= ОБРАБОТЧИКИ =================

@router.message(CommandStart())
async def cmd_start(message: Message):
    log_action(message.from_user.id, message.from_user.username, "start")
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
    log_action(callback.from_user.id, callback.from_user.username, "category", category)
    
    all_mks = get_mk_by_category(category)
    if not all_mks:
        await callback.message.answer(
            f"😔 В категории «{category}» пока нет МК.\n\n"
            f"Попробуйте другую категорию или нажмите /random",
            parse_mode="HTML"
        )
        return
    
    # Взвешенный случайный выбор 3 МК
    selected_mks = weighted_random_choice(all_mks, k=3)
    
    # Сохраняем состояние
    user_state[callback.from_user.id] = {
        'category': category,
        'index': 0,
        'mks': selected_mks,
        'all_mks': all_mks,  # Все МК категории для проверки "Ещё подборку"
        'from_favorites': False,
        'shown_links': [mk['link'] for mk in selected_mks]
    }
    
    mk = selected_mks[0]
    log_action(callback.from_user.id, callback.from_user.username, "view", category, mk['link'])
    
    # Проверяем, есть ли ещё МК для "Ещё подборку"
    has_more = len(all_mks) > len(selected_mks)
    
    text = format_card(mk, 1, len(selected_mks))
    kb = get_card_navigation_keyboard(callback.from_user.id, mk, 0, len(selected_mks), category, False, has_more)
    
    await callback.message.answer(text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)

@router.callback_query(F.data.startswith("nav_"))
async def navigate_card(callback: CallbackQuery):
    """Навигация между карточками"""
    data = callback.data[4:]  # убираем "nav_"
    parts = data.rsplit("_", 1)
    category = parts[0]
    new_index = int(parts[1])
    
    user_id = callback.from_user.id
    if user_id not in user_state or user_state[user_id]['category'] != category:
        await callback.answer("Сессия истекла, выберите категорию заново", show_alert=True)
        return
    
    state = user_state[user_id]
    mks = state['mks']
    
    if new_index < 0 or new_index >= len(mks):
        await callback.answer("Больше нет карточек", show_alert=True)
        return
    
    # ВАЖНО: Обновляем индекс в состоянии
    state['index'] = new_index
    
    mk = mks[new_index]
    log_action(user_id, callback.from_user.username, "view", category, mk['link'])
    
    # Проверяем, есть ли ещё МК для "Ещё подборку"
    all_mks = state.get('all_mks', mks)
    shown_links = state.get('shown_links', [])
    has_more = len(all_mks) > len(shown_links) and new_index == len(mks) - 1
    
    text = format_card(mk, new_index + 1, len(mks))
    kb = get_card_navigation_keyboard(user_id, mk, new_index, len(mks), category, state.get('from_favorites', False), has_more)
    
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
    await callback.answer()

@router.callback_query(F.data.startswith("new_batch_"))
async def new_batch(callback: CallbackQuery):
    """Новая подборка из той же категории"""
    category = callback.data.split("new_batch_", 1)[1]
    user_id = callback.from_user.id
    
    if user_id not in user_state:
        await callback.answer("Сессия истекла", show_alert=True)
        return
    
    state = user_state[user_id]
    all_mks = state.get('all_mks', [])
    shown_links = state.get('shown_links', [])
    
    # Фильтруем уже показанные
    available = [mk for mk in all_mks if mk['link'] not in shown_links]
    
    if not available:
        # Если все показаны, сбрасываем и начинаем заново
        available = all_mks
        shown_links = []
    
    # Взвешенный выбор
    selected_mks = weighted_random_choice(available, k=3)
    
    if not selected_mks:
        await callback.answer("Больше МК нет 😔", show_alert=True)
        return
    
    # Обновляем состояние
    state['mks'] = selected_mks
    state['index'] = 0
    state['shown_links'] = shown_links + [mk['link'] for mk in selected_mks]
    
    mk = selected_mks[0]
    log_action(user_id, callback.from_user.username, "view", category, mk['link'])
    
    # Проверяем, есть ли ещё
    has_more = len(all_mks) > len(state['shown_links'])
    
    text = format_card(mk, 1, len(selected_mks))
    kb = get_card_navigation_keyboard(user_id, mk, 0, len(selected_mks), category, False, has_more)
    
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
    await callback.answer()

@router.callback_query(F.data.startswith("fav_add_"))
async def add_to_favorites(callback: CallbackQuery):
    link = callback.data.split("fav_add_", 1)[1]
    mk = get_mk_by_link(link)
    if add_favorite(callback.from_user.id, link):
        log_action(callback.from_user.id, callback.from_user.username, "favorite_add", mk['category'] if mk else "", link)
        await callback.answer("❤️ Добавлено в избранное!", show_alert=False)
        # Обновляем клавиатуру
        if callback.from_user.id in user_state:
            state = user_state[callback.from_user.id]
            has_more = len(state.get('all_mks', [])) > len(state.get('shown_links', []))
            kb = get_card_navigation_keyboard(
                callback.from_user.id, mk, state['index'], len(state['mks']), 
                state['category'], state.get('from_favorites', False), has_more
            )
            await callback.message.edit_reply_markup(reply_markup=kb)
    else:
        await callback.answer("Уже в избранном", show_alert=True)

@router.callback_query(F.data.startswith("fav_remove_"))
async def remove_from_favorites(callback: CallbackQuery):
    link = callback.data.split("fav_remove_", 1)[1]
    mk = get_mk_by_link(link)
    if remove_favorite(callback.from_user.id, link):
        log_action(callback.from_user.id, callback.from_user.username, "favorite_remove", mk['category'] if mk else "", link)
        await callback.answer("💔 Удалено из избранного", show_alert=False)
        # Если мы в списке избранного — обновляем весь список
        if callback.from_user.id in user_state and user_state[callback.from_user.id].get('from_favorites'):
            await show_favorites_list(callback)
        else:
            # Иначе просто обновляем кнопку на карточке
            if callback.from_user.id in user_state:
                state = user_state[callback.from_user.id]
                has_more = len(state.get('all_mks', [])) > len(state.get('shown_links', []))
                kb = get_card_navigation_keyboard(
                    callback.from_user.id, mk, state['index'], len(state['mks']), 
                    state['category'], state.get('from_favorites', False), has_more
                )
                await callback.message.edit_reply_markup(reply_markup=kb)
    else:
        await callback.answer("Не найдено в избранном", show_alert=True)

@router.callback_query(F.data == "show_fav")
async def show_favorites(callback: CallbackQuery):
    log_action(callback.from_user.id, callback.from_user.username, "favorites_view")
    await show_favorites_list(callback)

async def show_favorites_list(callback: CallbackQuery):
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
    
    # Показываем первую карточку из избранного
    user_state[callback.from_user.id] = {
        'category': 'favorites',
        'index': 0,
        'mks': favorites_mks,
        'all_mks': favorites_mks,
        'from_favorites': True,
        'shown_links': [favorites_mks[0]['link']]
    }
    
    mk = favorites_mks[0]
    text = format_card(mk, 1, len(favorites_mks))
    kb = get_card_navigation_keyboard(callback.from_user.id, mk, 0, len(favorites_mks), 'favorites', True, False)
    
    await callback.message.answer(text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)

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
    
    # Взвешенный случайный выбор
    mk = weighted_random_choice(data, k=1)[0]
    log_action(target.from_user.id, target.from_user.username, "random", mk['category'], mk['link'])
    
    user_state[target.from_user.id] = {
        'category': 'random',
        'index': 0,
        'mks': [mk],
        'all_mks': [mk],
        'from_favorites': False,
        'shown_links': [mk['link']]
    }
    
    text = "<b>🎲 Случайный МК:</b>\n\n" + format_card(mk, 1, 1)
    kb = get_card_navigation_keyboard(target.from_user.id, mk, 0, 1, 'random', False, False)
    
    # Добавляем кнопку "Ещё случайный"
    kb.inline_keyboard.insert(-1, [InlineKeyboardButton(text="🎲 Ещё случайный", callback_data="random")])
    
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
    if message.from_user.id != ADMIN_ID:
        return
    
    if not os.path.exists(ANALYTICS_FILE):
        await message.answer("📊 Статистика пока пуста.")
        return
    
    with open(ANALYTICS_FILE, 'r', encoding='utf-8') as f:
        try:
            records = json.load(f)
        except:
            await message.answer("❌ Ошибка чтения статистики.")
            return
    
    now = datetime.now()
    today = now.date()
    
    today_records = [r for r in records if datetime.fromisoformat(r['time']).date() == today]
    total_users = len(set(r['user_id'] for r in today_records))
    starts = len([r for r in today_records if r['action'] == 'start'])
    categories = len([r for r in today_records if r['action'] == 'category'])
    views = len([r for r in today_records if r['action'] == 'view'])
    
    cat_counts = {}
    for r in records:
        if r['action'] == 'category' and r.get('category'):
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
    print("✅ Бот успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
