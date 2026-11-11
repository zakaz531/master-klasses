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
        'favorite_remove': 'favorite', 'favorites_view': 'favorite
