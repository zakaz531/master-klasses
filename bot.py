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
    """Читает ВСЕ данные из Google Таблицы"""
    try:
        req = urllib.request.Request(SHEET_CSV_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as response:
            csv_data = response.read().decode('utf-8')
        
        # Умное определение разделителя
        first_line = csv_data.split('\n')[0]
        delimiter = ';' if ';' in first_line else ','
        
        reader = csv.DictReader(csv_data.splitlines(), delimiter=delimiter)
        
        # ОТЛАДКА: показываем заголовки в логах
        print(f" DEBUG: Заголовки таблицы: {reader.fieldnames}")
        
        data = []
        for row in reader:
            try:
                # Приводим все ключи к нижнему регистру и убираем пробелы
                clean_row = {k.strip().lower(): (v.strip() if v else "") for k, v in row.items() if k}
                
                name = clean_row.get('name', '')
                category = clean_row.get('category', '')
                
                if not name or not category:
                    continue
                
                # Читаем ВСЕ поля из таблицы
                data.append({
                    "link": clean_row.get('link', ''),
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
                    "tglink": clean_row.get('tglink', '') or clean_row.get('link', '')
                })
            except Exception as e:
                print(f"⚠️ Ошибка строки: {e}")
                continue
        
        print(f"✅ DEBUG: Загружено {len(data)} мастер-классов")
        return data
    except Exception as e:
        print(f" Ошибка загрузки таблицы: {e}")
        return []

def find_mk(category, limit=3, exclude_ids=None):
    """Находит МК по категории"""
    data = load_mk_data()
    exclude_ids = exclude_ids or []
    filtered = [
        item for item in data 
        if item["category"].lower() == category.lower() 
        and item["link"] not in exclude_ids
    ]
    if len(filtered) > limit:
        return random.sample(filtered, limit)
    return filtered

def format_card(mk, number=1):
    """Форматирует ПОЛНУЮ карточку МК (как в старом боте)"""
    card = []
    
    # Заголовок
    card.append(f"<b>{number}. {mk['name']}</b>")
    card.append(f"Категория: {mk['category']}")
    card.append("")
    
    # Метро
    if mk.get('metro'):
        card.append(f"🚇 {mk['metro']}")
    
    # Цена
    if mk.get('price'):
        card.append(f"💰 {mk['price']}")
    
    # Участники и периодичность
    if mk.get('participants'):
        card.append(f"👥 до {mk['participants']} чел.")
    if mk.get('periodicity'):
        card.append(f"📅 {mk['periodicity']}")
    
    card.append("")
    
    # Фишка
    if mk.get('feature'):
        card.append(f"⚡ <b>Фишка:</b> {mk['feature']}")
    
    # Плюсы
    if mk.get('advantages'):
        card.append(f"✅ <b>Плюсы:</b> {mk['advantages']}")
    
    # Минусы
    if mk.get('disadvantages'):
        card.append(f"⚠️ <b>Минусы:</b> {mk['disadvantages']}")
    
    # Идеально для
    if mk.get('best_reason'):
        card.append(f"🎯 <b>Идеально для:</b> {mk['best_reason']}")
    
    card.append("")
    card.append("<i>️ Проверьте актуальность перед записью!</i>")
    
    return "\n".join(card)

def get_card_keyboard(mk):
    """Создаёт кнопки под карточкой (как в старом боте)"""
    buttons = []
    
    # Первая строка: В избранное | Поделиться
    row1 = [
        InlineKeyboardButton(text="❤️ В избранное", callback_data=f"fav_{mk['link']}"),
        InlineKeyboardButton(text="📤 Поделиться", callback_data=f"share_{mk['link']}")
    ]
    buttons.append(row1)
    
    # Вторая строка: Вперёд (следующий МК)
    row2 = [InlineKeyboardButton(text="▶️ Вперёд", callback_data=f"next_{mk['category']}")]
    buttons.append(row2)
    
    # Третья строка: В меню
    row3 = [InlineKeyboardButton(text="📋 В меню", callback_data="start")]
    buttons.append(row3)
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def log_action(user_id, username, action, category="", mk_link=""):
    """Записывает аналитику"""
    record = {
        "time": datetime.now().isoformat(),
        "user_id": user_id,
        "username": username,
        "action": action,
        "category": category,
        "mk_link": mk_link
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

# ================= МЕНЮ =================

def get_main_keyboard():
    categories = [
        ("🍳 Кулинария", "Кулинария"),
        (" Арт", "Арт"),
        (" Рукоделие", "Рукоделие"),
        ("🏺 Керамика", "Керамика"),
        ("💎 Ювелирка", "Ювелирка"),
        ("🌸 Флористика", "Флористика"),
        ("🎭 Необычное", "Необычное"),
        (" Танцы", "Танцы"),
        ("🎵 Музыка", "Музыка"),
        ("📸 Фото", "Фото"),
        (" Детский", "Детский"),
        ("📋 Разное", "Разное"),
    ]
    # По 2 кнопки в ряд
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
    await message.answer(
        " <b>Привет!</b>\n\n"
        "Я помогу подобрать мастер-класс в Москве.\n\n"
        "<b>Выберите категорию:</b>",
        reply_markup=get_main_keyboard(),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("cat_"))
async def show_category(callback: CallbackQuery):
    category = callback.data.split("_", 1)[1]
    log_action(callback.from_user.id, callback.from_user.username or "", "category", category)
    
    results = find_mk(category, limit=3)
    
    if not results:
        await callback.message.answer(
            f"😔 В категории «{category}» пока нет МК.\n\n"
            f"Попробуйте другую категорию или нажмите /random",
            parse_mode="HTML"
        )
        return
    
    # Показываем первую карточку
    mk = results[0]
    text = format_card(mk, 1)
    log_action(callback.from_user.id, callback.from_user.username or "", "view", category, mk['link'])
    
    # Сохраняем оставшиеся для кнопки "Вперёд"
    remaining_links = [m['link'] for m in results[1:]]
    remaining_str = "|".join(remaining_links)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❤️ В избранное", callback_data=f"fav_{mk['link']}"),
         InlineKeyboardButton(text="📤 Поделиться", callback_data=f"share_{mk['link']}")],
        [InlineKeyboardButton(text="▶️ Вперёд", callback_data=f"next_{category}_{remaining_str}")],
        [InlineKeyboardButton(text="🔄 Ещё из категории", callback_data=f"more_{category}_{mk['link']}")],
        [InlineKeyboardButton(text=" Случайный", callback_data="random")],
        [InlineKeyboardButton(text="📋 В меню", callback_data="start")],
    ])
    
    await callback.message.answer(text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)

@router.callback_query(F.data.startswith("next_"))
async def show_next(callback: CallbackQuery):
    data = callback.data[6:]  # убираем "next_"
    parts = data.split("_", 1)
    category = parts[0]
    remaining_links = parts[1].split("|") if len(parts) > 1 else []
    
    if not remaining_links:
        await callback.answer("Больше нет в этой подборке", show_alert=True)
        return
    
    # Находим следующий МК
    all_data = load_mk_data()
    next_mk = None
    for mk in all_data:
        if mk['category'].lower() == category.lower() and mk['link'] == remaining_links[0]:
            next_mk = mk
            break
    
    if not next_mk:
        await callback.answer("МК не найден", show_alert=True)
        return
    
    text = format_card(next_mk, 1)
    log_action(callback.from_user.id, callback.from_user.username or "", "view", category, next_mk['link'])
    
    new_remaining = remaining_links[1:]
    new_remaining_str = "|".join(new_remaining)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❤️ В избранное", callback_data=f"fav_{next_mk['link']}"),
         InlineKeyboardButton(text="📤 Поделиться", callback_data=f"share_{next_mk['link']}")],
        [InlineKeyboardButton(text="▶️ Вперёд", callback_data=f"next_{category}_{new_remaining_str}")] if new_remaining else [],
        [InlineKeyboardButton(text="🔄 Ещё из категории", callback_data=f"more_{category}_{next_mk['link']}")],
        [InlineKeyboardButton(text="📋 В меню", callback_data="start")],
    ])
    
    await callback.message.answer(text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)

@router.callback_query(F.data.startswith("more_"))
async def show_more(callback: CallbackQuery):
    data = callback.data[5:]  # убираем "more_"
    parts = data.split("_", 1)
    category = parts[0]
    shown_links = parts[1].split("|") if len(parts) > 1 else []
    
    results = find_mk(category, limit=3, exclude_ids=shown_links)
    
    if not results:
        await callback.answer("Больше МК в этой категории нет 😔", show_alert=True)
        return
    
    mk = results[0]
    text = format_card(mk, 1)
    log_action(callback.from_user.id, callback.from_user.username or "", "view", category, mk['link'])
    
    remaining_links = [m['link'] for m in results[1:]]
    all_shown = shown_links + [mk['link']]
    all_shown_str = "|".join(all_shown)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❤️ В избранное", callback_data=f"fav_{mk['link']}"),
         InlineKeyboardButton(text="📤 Поделиться", callback_data=f"share_{mk['link']}")],
        [InlineKeyboardButton(text="▶️ Вперёд", callback_data=f"next_{category}_{'|'.join(remaining_links)}")] if remaining_links else [],
        [InlineKeyboardButton(text="🔄 Ещё", callback_data=f"more_{category}_{all_shown_str}")],
        [InlineKeyboardButton(text="📋 В меню", callback_data="start")],
    ])
    
    await callback.message.answer(text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)

@router.callback_query(F.data.startswith("fav_"))
async def add_to_favorites(callback: CallbackQuery):
    mk_link = callback.data.split("_", 1)[1]
    # Здесь можно добавить сохранение в избранное пользователя
    await callback.answer("Добавлено в избранное ❤️", show_alert=False)
    log_action(callback.from_user.id, callback.from_user.username or "", "favorite", "", mk_link)

@router.callback_query(F.data.startswith("share_"))
async def share_mk(callback: CallbackQuery):
    mk_link = callback.data.split("_", 1)[1]
    # Telegram не позволяет отправить сообщение от имени бота другому пользователю напрямую
    # Поэтому просто показываем уведомление
    await callback.answer("Чтобы поделиться: скопируйте ссылку из карточки и отправьте другу", show_alert=True)
    log_action(callback.from_user.id, callback.from_user.username or "", "share", "", mk_link)

@router.callback_query(F.data == "random")
@router.message(Command("random"))
async def random_mk(target):
    data = load_mk_data()
    if not data:
        text = "😔 Пока нет МК в базе."
    else:
        mk = random.choice(data)
        text = "<b>🎲 Случайный МК:</b>\n\n" + format_card(mk, 1)
        log_action(target.from_user.id, target.from_user.username or "", "random", "", mk['link'])
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❤️ В избранное", callback_data=f"fav_{mk['link']}"),
             InlineKeyboardButton(text="📤 Поделиться", callback_data=f"share_{mk['link']}")],
            [InlineKeyboardButton(text="🔄 Ещё случайный", callback_data="random")],
            [InlineKeyboardButton(text="📋 В меню", callback_data="start")],
        ])
        
        if isinstance(target, CallbackQuery):
            await target.message.answer(text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
        else:
            await target.answer(text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
        return
    
    if isinstance(target, CallbackQuery):
        await target.message.answer(text, parse_mode="HTML")
    else:
        await target.answer(text, parse_mode="HTML")

@router.callback_query(F.data == "start")
async def go_start(callback: CallbackQuery):
    await callback.message.delete()
    await cmd_start(callback.message)

@router.message(Command("stats"))
async def admin_stats(message: Message):
    """Показывает статистику (только для админа)"""
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
    
    # Считаем за сегодня
    today_records = [r for r in records if datetime.fromisoformat(r['time']).date() == today]
    total_users = len(set(r['user_id'] for r in today_records))
    starts = len([r for r in today_records if r['action'] == 'start'])
    categories = len([r for r in today_records if r['action'] == 'category'])
    views = len([r for r in today_records if r['action'] == 'view'])
    
    # Топ категорий
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
        f" Выбор категории: {categories}\n"
        f"👁 Просмотров карточек: {views}\n\n"
        f"🔥 <b>Топ категорий (всего):</b>\n"
    )
    
    for cat, count in top_cats:
        stats_text += f"  • {cat}: {count}\n"
    
    await message.answer(stats_text, parse_mode="HTML")

# ================= ЗАПУСК =================

async def main():
    print("✅ Бот успешно запущен!")
    print(f"📊 Аналитика пишется в: {os.path.abspath(ANALYTICS_FILE)}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
