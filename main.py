

# main.py - To'liq Telegram bot (aiogram 3.x)

import asyncio
import logging
import sqlite3
import random
import string
import re
import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from contextlib import contextmanager
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Load environment variables
load_dotenv()

# Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(id_) for id_ in os.getenv("ADMIN_IDS", "").split(",") if id_]
DATABASE_PATH = os.getenv("DATABASE_PATH", "bot_database.db")

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== DATABASE MODELS ====================

@dataclass
class User:
    id: int
    telegram_id: int
    username: Optional[str]
    first_name: str
    last_name: Optional[str]
    is_admin: bool
    created_at: str
    last_active: str

@dataclass
class File:
    id: int
    code: str
    admin_id: int
    created_at: str
    description: Optional[str]

@dataclass
class FileItem:
    id: int
    file_id: int
    file_type: str
    telegram_file_id: str
    file_name: Optional[str]
    file_size: Optional[int]

@dataclass
class Channel:
    id: int
    channel_id: int
    channel_username: Optional[str]
    channel_title: str
    added_by: int
    added_at: str
    is_active: bool

@dataclass
class Whitelist:
    id: int
    user_id: int
    added_by: int
    added_at: str

# ==================== DATABASE CLASS ====================

class Database:
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
        self.init_database()
    
    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def init_database(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE NOT NULL,
                    username TEXT,
                    first_name TEXT NOT NULL,
                    last_name TEXT,
                    is_admin BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Files table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL,
                    admin_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    description TEXT,
                    FOREIGN KEY (admin_id) REFERENCES users (telegram_id)
                )
            ''')
            
            # File items table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS file_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER NOT NULL,
                    file_type TEXT NOT NULL,
                    telegram_file_id TEXT NOT NULL,
                    file_name TEXT,
                    file_size INTEGER,
                    FOREIGN KEY (file_id) REFERENCES files (id) ON DELETE CASCADE
                )
            ''')
            
            # Channels table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id INTEGER UNIQUE NOT NULL,
                    channel_username TEXT,
                    channel_title TEXT NOT NULL,
                    added_by INTEGER NOT NULL,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE,
                    FOREIGN KEY (added_by) REFERENCES users (telegram_id)
                )
            ''')
            
            # Whitelist table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS whitelist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE NOT NULL,
                    added_by INTEGER NOT NULL,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (telegram_id),
                    FOREIGN KEY (added_by) REFERENCES users (telegram_id)
                )
            ''')
            
            conn.commit()
            logger.info("Database initialized successfully")
    
    # User methods
    def add_user(self, telegram_id: int, first_name: str, username: Optional[str] = None, 
                 last_name: Optional[str] = None) -> None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO users (telegram_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
            ''', (telegram_id, username, first_name, last_name))
            conn.commit()
    
    def update_user_activity(self, telegram_id: int) -> None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users SET last_active = CURRENT_TIMESTAMP 
                WHERE telegram_id = ?
            ''', (telegram_id,))
            conn.commit()
    
    def get_user(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE username = ?', (username.replace('@', ''),))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def is_admin(self, telegram_id: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT is_admin FROM users WHERE telegram_id = ?', (telegram_id,))
            row = cursor.fetchone()
            return row['is_admin'] if row else False
    
    def get_all_users_count(self) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) as count FROM users')
            row = cursor.fetchone()
            return row['count']
    
    # File methods
    def create_file(self, code: str, admin_id: int, description: Optional[str] = None) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO files (code, admin_id, description)
                VALUES (?, ?, ?)
            ''', (code, admin_id, description))
            conn.commit()
            return cursor.lastrowid
    
    def add_file_item(self, file_id: int, file_type: str, telegram_file_id: str, 
                      file_name: Optional[str] = None, file_size: Optional[int] = None) -> None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO file_items (file_id, file_type, telegram_file_id, file_name, file_size)
                VALUES (?, ?, ?, ?, ?)
            ''', (file_id, file_type, telegram_file_id, file_name, file_size))
            conn.commit()
    
    def get_file_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM files WHERE code = ?', (code,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_file_items(self, file_id: int) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM file_items WHERE file_id = ?', (file_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_all_files(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT f.*, COUNT(fi.id) as items_count 
                FROM files f
                LEFT JOIN file_items fi ON f.id = fi.file_id
                GROUP BY f.id
                ORDER BY f.created_at DESC
            ''')
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def delete_file(self, file_id: int) -> None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM files WHERE id = ?', (file_id,))
            conn.commit()
    
    def get_files_count(self) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) as count FROM files')
            row = cursor.fetchone()
            return row['count']
    
    def get_file_items_count(self) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) as count FROM file_items')
            row = cursor.fetchone()
            return row['count']
    
    # Channel methods
    def add_channel(self, channel_id: int, channel_title: str, added_by: int, 
                    channel_username: Optional[str] = None) -> None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO channels (channel_id, channel_username, channel_title, added_by)
                VALUES (?, ?, ?, ?)
            ''', (channel_id, channel_username, channel_title, added_by))
            conn.commit()
    
    def remove_channel(self, channel_id: int) -> None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM channels WHERE channel_id = ?', (channel_id,))
            conn.commit()
    
    def get_all_channels(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM channels WHERE is_active = 1 ORDER BY added_at DESC')
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_channel(self, channel_id: int) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM channels WHERE channel_id = ?', (channel_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    # Whitelist methods
    def add_to_whitelist(self, user_id: int, added_by: int) -> bool:
        with self.get_connection() as conn:
            try:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR IGNORE INTO whitelist (user_id, added_by)
                    VALUES (?, ?)
                ''', (user_id, added_by))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Error adding to whitelist: {e}")
                return False
    
    def remove_from_whitelist(self, user_id: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM whitelist WHERE user_id = ?', (user_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    def is_whitelisted(self, user_id: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM whitelist WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()
            return row is not None
    
    def get_whitelist(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT w.*, u.username, u.first_name, u.telegram_id
                FROM whitelist w
                JOIN users u ON w.user_id = u.telegram_id
                ORDER BY w.added_at DESC
            ''')
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

# ==================== STATES ====================

class AdminStates(StatesGroup):
    waiting_for_files = State()
    waiting_for_code_description = State()
    waiting_for_channel = State()
    waiting_for_channel_remove = State()
    waiting_for_whitelist_user = State()
    waiting_for_whitelist_remove = State()
    waiting_for_code = State()

# ==================== UTILITIES ====================

class CodeGenerator:
    @staticmethod
    def generate_code(length: int = 8) -> str:
        characters = string.ascii_uppercase + string.digits
        return ''.join(random.choices(characters, k=length))
    
    @staticmethod
    def validate_code(code: str) -> bool:
        return bool(re.match(r'^[A-Z0-9]{8}$', code))

class ChannelChecker:
    def __init__(self, bot: Bot):
        self.bot = bot
    
    async def check_subscription(self, user_id: int, channels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        not_subscribed = []
        
        for channel in channels:
            try:
                chat_member = await self.bot.get_chat_member(
                    chat_id=channel['channel_id'], 
                    user_id=user_id
                )
                
                if chat_member.status in ['left', 'kicked']:
                    not_subscribed.append(channel)
                    
            except Exception as e:
                logger.error(f"Error checking subscription for channel {channel['channel_id']}: {e}")
                not_subscribed.append(channel)
        
        return not_subscribed
    
    async def get_channel_info(self, channel_identifier: str) -> Optional[Dict[str, Any]]:
        try:
            if channel_identifier.startswith('@'):
                channel_identifier = channel_identifier[1:]
            
            chat = await self.bot.get_chat(f"@{channel_identifier}")
            
            bot_member = await self.bot.get_chat_member(chat.id, self.bot.id)
            if bot_member.status not in ['administrator', 'creator']:
                return None
            
            return {
                'id': chat.id,
                'username': chat.username,
                'title': chat.title,
                'type': chat.type
            }
            
        except Exception as e:
            logger.error(f"Error getting channel info: {e}")
            return None

class StatisticsService:
    def __init__(self, db: Database):
        self.db = db
    
    def get_statistics(self) -> dict:
        users_count = self.db.get_all_users_count()
        files_count = self.db.get_files_count()
        file_items_count = self.db.get_file_items_count()
        channels_count = len(self.db.get_all_channels())
        whitelist_count = len(self.db.get_whitelist())
        
        return {
            'users_count': users_count,
            'files_count': files_count,
            'file_items_count': file_items_count,
            'channels_count': channels_count,
            'whitelist_count': whitelist_count
        }

def extract_channel_username(text: str) -> Optional[str]:
    text = text.strip().replace('@', '')
    
    telegram_pattern = r'(?:https?://)?(?:t\.me|telegram\.me)/([a-zA-Z0-9_]+)'
    match = re.search(telegram_pattern, text)
    if match:
        return match.group(1)
    
    if re.match(r'^[a-zA-Z0-9_]{5,}$', text):
        return text
    
    return None

def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

# ==================== KEYBOARDS ====================

def get_main_menu_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Asosiy menyu keyboard"""
    if is_admin:
        return get_admin_main_keyboard()
    else:
        return get_user_main_keyboard()

def get_admin_main_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📤 Fayl yuklash", callback_data="upload_file"),
         InlineKeyboardButton(text="📂 Fayllarim", callback_data="my_files")],
        [InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="add_channel"),
         InlineKeyboardButton(text="➖ Kanal o'chirish", callback_data="remove_channel")],
        [InlineKeyboardButton(text="📋 Kanallar ro'yxati", callback_data="list_channels"),
         InlineKeyboardButton(text="👤 Whitelist qo'shish", callback_data="add_whitelist")],
        [InlineKeyboardButton(text="❌ Whitelist o'chirish", callback_data="remove_whitelist"),
         InlineKeyboardButton(text="📊 Statistika", callback_data="statistics")],
        [InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="back_to_main"),
         InlineKeyboardButton(text="ℹ️ Bot haqida", callback_data="about_bot")],
        [InlineKeyboardButton(text="👨‍💻 Yaratuvchi", callback_data="about_creator")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_user_main_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🔑 Kod yuborish", callback_data="send_code")],
        [InlineKeyboardButton(text="ℹ️ Bot haqida", callback_data="about_bot")],
        [InlineKeyboardButton(text="👨‍💻 Yaratuvchi", callback_data="about_creator")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_back_keyboard(target: str = "main") -> InlineKeyboardMarkup:
    """Ortga qaytish keyboard"""
    if target == "main":
        text = "🏠 Bosh menyu"
        data = "back_to_main"
    elif target == "admin":
        text = "👑 Admin panel"
        data = "back_to_admin"
    else:
        text = "🔙 Ortga"
        data = "back"
    
    buttons = [[InlineKeyboardButton(text=text, callback_data=data)]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_subscription_keyboard(channels: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    buttons = []
    for channel in channels:
        if channel['channel_username']:
            url = f"https://t.me/{channel['channel_username']}"
        else:
            url = f"https://t.me/c/{str(channel['channel_id'])[4:]}"
        
        display_name = channel['channel_title']
        if len(display_name) > 30:
            display_name = display_name[:27] + "..."
        
        buttons.append([InlineKeyboardButton(text=f"📢 {display_name}", url=url)])
    
    buttons.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_subscription")])
    buttons.append([InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_files_keyboard(files: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    buttons = []
    for file in files:
        buttons.append([InlineKeyboardButton(
            text=f"📁 {file['code']} ({file['items_count']} ta fayl)",
            callback_data=f"view_file_{file['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="👑 Admin panel", callback_data="back_to_admin")])
    buttons.append([InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_file_actions_keyboard(file_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📥 Yuklab olish", callback_data=f"download_file_{file_id}")],
        [InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"delete_file_{file_id}")],
        [InlineKeyboardButton(text="👑 Admin panel", callback_data="back_to_admin")],
        [InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_channels_keyboard(channels: List[Dict[str, Any]], action: str = "remove") -> InlineKeyboardMarkup:
    buttons = []
    for channel in channels:
        display_name = channel['channel_title']
        if len(display_name) > 30:
            display_name = display_name[:27] + "..."
        
        buttons.append([InlineKeyboardButton(
            text=f"📢 {display_name}",
            callback_data=f"{action}_channel_{channel['channel_id']}"
        )])
    buttons.append([InlineKeyboardButton(text="👑 Admin panel", callback_data="back_to_admin")])
    buttons.append([InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_whitelist_keyboard(whitelist: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    buttons = []
    for item in whitelist:
        username = item['username'] or item['first_name']
        if len(username) > 20:
            username = username[:17] + "..."
        
        buttons.append([InlineKeyboardButton(
            text=f"👤 {username}",
            callback_data=f"remove_wl_{item['user_id']}"
        )])
    buttons.append([InlineKeyboardButton(text="👑 Admin panel", callback_data="back_to_admin")])
    buttons.append([InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_cancel_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel")],
        [InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ==================== MIDDLEWARES ====================

class SubscriptionMiddleware(BaseMiddleware):
    def __init__(self, db: Database, channel_checker: ChannelChecker):
        self.db = db
        self.channel_checker = channel_checker
        super().__init__()
    
    async def __call__(self, handler, event: Message | CallbackQuery, data: Dict[str, Any]):
        user_id = event.from_user.id
        
        # Skip check for admins
        if self.db.is_admin(user_id) or self.db.is_whitelisted(user_id):
            return await handler(event, data)
        
        # Check if it's a code message
        if isinstance(event, Message) and event.text and len(event.text) == 8:
            channels = self.db.get_all_channels()
            
            if channels:
                not_subscribed = await self.channel_checker.check_subscription(user_id, channels)
                
                if not_subscribed:
                    keyboard = get_subscription_keyboard(not_subscribed)
                    await event.answer(
                        "❗️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:",
                        reply_markup=keyboard
                    )
                    return
        
        return await handler(event, data)

# ==================== HANDLERS ====================

class BotHandlers:
    def __init__(self, bot: Bot, dp: Dispatcher, db: Database, channel_checker: ChannelChecker):
        self.bot = bot
        self.dp = dp
        self.db = db
        self.channel_checker = channel_checker
        self.statistics = StatisticsService(db)
        self.setup_handlers()
    
    def setup_handlers(self):
        # ========== BOSH MENYU HANDLERS ==========
        
        @self.dp.message(CommandStart())
        async def cmd_start(message: Message):
            user = message.from_user
            self.db.add_user(
                telegram_id=user.id,
                first_name=user.first_name,
                username=user.username,
                last_name=user.last_name
            )
            self.db.update_user_activity(user.id)
            
            # Chiroyli start xabari
            welcome_text = (
                "✨ *Assalomu alaykum! Botimizga xush kelibsiz!* ✨\n\n"
                "📁 Bu bot orqali siz maxsus kodlar yordamida fayllarni yuklab olishingiz mumkin.\n\n"
                "🔍 *Bot imkoniyatlari:*\n"
                "• Maxsus kod orqali fayllarni yuklab olish\n"
                "• Majburiy kanallarga obuna bo'lish tizimi\n"
                "• Tez va qulay interfeys\n\n"
                "👇 Quyidagi tugmalardan birini tanlang:"
            )
            
            if self.db.is_admin(user.id) or user.id in ADMIN_IDS:
                await message.answer(
                    welcome_text + "\n\n👑 *Siz admin sifatida kirdingiz*",
                    parse_mode="Markdown",
                    reply_markup=get_admin_main_keyboard()
                )
            else:
                await message.answer(
                    welcome_text,
                    parse_mode="Markdown",
                    reply_markup=get_user_main_keyboard()
                )
            
            logger.info(f"User {user.id} started the bot")
        
        @self.dp.callback_query(F.data == "back_to_main")
        async def back_to_main(callback: CallbackQuery):
            user_id = callback.from_user.id
            welcome_text = (
                "✨ *Bosh menyu* ✨\n\n"
                "Quyidagi tugmalardan birini tanlang:"
            )
            
            if self.db.is_admin(user_id) or user_id in ADMIN_IDS:
                await callback.message.edit_text(
                    welcome_text + "\n\n👑 *Admin panel*",
                    parse_mode="Markdown",
                    reply_markup=get_admin_main_keyboard()
                )
            else:
                await callback.message.edit_text(
                    welcome_text,
                    parse_mode="Markdown",
                    reply_markup=get_user_main_keyboard()
                )
            await callback.answer()
        
        @self.dp.callback_query(F.data == "back_to_admin")
        async def back_to_admin(callback: CallbackQuery):
            await callback.message.edit_text(
                "👑 *Admin panel*",
                parse_mode="Markdown",
                reply_markup=get_admin_main_keyboard()
            )
            await callback.answer()
        
        @self.dp.callback_query(F.data == "about_bot")
        async def about_bot(callback: CallbackQuery):
            about_text = (
                "🤖 *Bot haqida*\n\n"
                "Bu bot fayllarni maxsus kodlar orqali tarqatish uchun yaratilgan.\n\n"
                "📌 *Asosiy xususiyatlar:*\n"
                "• Fayllarni bir kodga birlashtirish\n"
                "• Majburiy kanallarga obuna tizimi\n"
                "• Admin panel orqali to'liq boshqaruv\n"
                "• Whitelist tizimi (kanalsiz foydalanish)\n\n"
                "🛡 *Xavfsizlik:*\n"
                "Barcha ma'lumotlar maxfiy saqlanadi va faqat admin tomonidan boshqariladi."
            )
            await callback.message.edit_text(
                about_text,
                parse_mode="Markdown",
                reply_markup=get_back_keyboard("main")
            )
            await callback.answer()
        
        @self.dp.callback_query(F.data == "about_creator")
        async def about_creator(callback: CallbackQuery):
            creator_text = (
                "👨‍💻 *Yaratuvchi haqida*\n\n"
                "• *Ism:* Farrux\n"
                "• *Username:* @devc0derweb\n"
                "• *Kasb:* Python Developer & Telegram Bot Developer\n\n"
                "📊 *Tajriba:*\n"
                "• 3+ yil Python dasturlash\n"
                "• 2+ yil Telegram botlar yaratish\n"
                "• 50+ loyiha\n\n"
                "🔧 *Texnologiyalar:*\n"
                "• Python, Aiogram, Django\n"
                "• SQLite, PostgreSQL\n"
                "• HTML, CSS, JavaScript\n\n"
                "📞 *Bog'lanish:*\n"
                "Telegram: @devc0derweb\n"
                "GitHub: github.com/devc0derweb\n\n"
                "💡 *Taklif va murojaatlar uchun bemalol yozing!*"
            )
            await callback.message.edit_text(
                creator_text,
                parse_mode="Markdown",
                reply_markup=get_back_keyboard("main")
            )
            await callback.answer()
        
        # ========== USER HANDLERS ==========
        
        @self.dp.callback_query(F.data == "send_code")
        async def send_code_prompt(callback: CallbackQuery, state: FSMContext):
            await callback.message.edit_text(
                "🔑 *Iltimos, fayl kodini yuboring*\n\n"
                "Kod 8 ta belgidan iborat (A-Z, 0-9)",
                parse_mode="Markdown",
                reply_markup=get_cancel_keyboard()
            )
            await state.set_state(AdminStates.waiting_for_code)
            await callback.answer()
        
        @self.dp.message(AdminStates.waiting_for_code)
        async def process_code(message: Message, state: FSMContext):
            code = message.text.strip().upper()
            
            if not CodeGenerator.validate_code(code):
                await message.answer(
                    "❌ *Noto'g'ri kod formati!*\n\n"
                    "Kod 8 ta belgidan iborat bo'lishi kerak (A-Z, 0-9).\n"
                    "Masalan: `ABC123XY`",
                    parse_mode="Markdown"
                )
                return
            
            file_data = self.db.get_file_by_code(code)
            
            if not file_data:
                await message.answer(
                    "❌ *Bunday kod mavjud emas!*\n\n"
                    "Iltimos, kodni tekshirib qaytadan yuboring.",
                    parse_mode="Markdown"
                )
                await state.clear()
                return
            
            file_items = self.db.get_file_items(file_data['id'])
            
            if not file_items:
                await message.answer(
                    "❌ *Bu kodda fayllar mavjud emas!*",
                    parse_mode="Markdown"
                )
                await state.clear()
                return
            
            await message.answer(
                f"📥 *{len(file_items)} ta fayl yuklanmoqda...*",
                parse_mode="Markdown"
            )
            
            for item in file_items:
                try:
                    caption = f"📁 {item['file_name'] or 'Fayl'}"
                    if item['file_size']:
                        caption += f" | {format_size(item['file_size'])}"
                    
                    if item['file_type'] == 'photo':
                        await message.answer_photo(
                            item['telegram_file_id'],
                            caption=caption
                        )
                    elif item['file_type'] == 'video':
                        await message.answer_video(
                            item['telegram_file_id'],
                            caption=caption
                        )
                    else:
                        await message.answer_document(
                            item['telegram_file_id'],
                            caption=caption
                        )
                except Exception as e:
                    logger.error(f"Error sending file: {e}")
                    await message.answer_document(
                        item['telegram_file_id'],
                        caption="📁 Fayl"
                    )
            
            await message.answer(
                "✅ *Barcha fayllar yuborildi!*",
                parse_mode="Markdown"
            )
            await state.clear()
        
        @self.dp.callback_query(F.data == "check_subscription")
        async def check_subscription(callback: CallbackQuery):
            user_id = callback.from_user.id
            channels = self.db.get_all_channels()
            
            if not channels:
                await callback.message.edit_text(
                    "✅ *Siz barcha kanallarga obuna bo'lgansiz!*\n\n"
                    "Endi kod yuborishingiz mumkin.",
                    parse_mode="Markdown",
                    reply_markup=get_back_keyboard("main")
                )
                await callback.answer()
                return
            
            not_subscribed = await self.channel_checker.check_subscription(user_id, channels)
            
            if not_subscribed:
                await callback.message.edit_text(
                    "❗️ *Hali ham quyidagi kanallarga obuna bo'lmagansiz:*",
                    parse_mode="Markdown",
                    reply_markup=get_subscription_keyboard(not_subscribed)
                )
            else:
                await callback.message.edit_text(
                    "✅ *Obuna tekshirildi!*\n\n"
                    "Barcha kanallarga obuna bo'lgansiz.\n"
                    "Endi kod yuborishingiz mumkin.",
                    parse_mode="Markdown",
                    reply_markup=get_back_keyboard("main")
                )
            
            await callback.answer()
        
        @self.dp.callback_query(F.data == "cancel")
        async def cancel_action(callback: CallbackQuery, state: FSMContext):
            await state.clear()
            await callback.message.edit_text(
                "❌ *Amal bekor qilindi*",
                parse_mode="Markdown"
            )
            await back_to_main(callback)
        
        # ========== ADMIN HANDLERS ==========
        
        @self.dp.callback_query(F.data == "upload_file")
        async def upload_file_start(callback: CallbackQuery, state: FSMContext):
            if callback.from_user.id not in ADMIN_IDS:
                await callback.answer("❌ Ruxsat yo'q!", show_alert=True)
                return
            
            await callback.message.edit_text(
                "📤 *Fayl yuklash*\n\n"
                "Fayllarni yuboring. Bir nechta fayl yuborishingiz mumkin.\n"
                "Yuklash tugagach /done buyrug'ini yuboring.\n\n"
                "Qabul qilinadigan formatlar:\n"
                "• Rasm (photo)\n"
                "• Video\n"
                "• Hujjat (document)",
                parse_mode="Markdown",
                reply_markup=get_cancel_keyboard()
            )
            await state.set_state(AdminStates.waiting_for_files)
            await state.update_data(files=[])
            await callback.answer()
        
        @self.dp.message(AdminStates.waiting_for_files)
        async def process_files(message: Message, state: FSMContext):
            if message.text == '/done':
                data = await state.get_data()
                files = data.get('files', [])
                
                if not files:
                    await message.answer(
                        "❌ *Hech qanday fayl yuklanmadi*",
                        parse_mode="Markdown"
                    )
                    await state.clear()
                    return
                
                code = CodeGenerator.generate_code()
                file_id = self.db.create_file(code, message.from_user.id)
                
                for file_data in files:
                    self.db.add_file_item(
                        file_id=file_id,
                        file_type=file_data['type'],
                        telegram_file_id=file_data['file_id'],
                        file_name=file_data.get('name'),
                        file_size=file_data.get('size')
                    )
                
                await message.answer(
                    f"✅ *Fayllar muvaffaqiyatli yuklandi!*\n\n"
                    f"📌 *Kod:* `{code}`\n"
                    f"📊 *Fayllar soni:* {len(files)}\n\n"
                    f"🔍 Bu kod orqali foydalanuvchilar fayllarni yuklab olishlari mumkin.",
                    parse_mode="Markdown"
                )
                await state.clear()
                return
            
            # Process file
            file_data = None
            if message.photo:
                file_data = {
                    'type': 'photo',
                    'file_id': message.photo[-1].file_id,
                    'name': f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg",
                    'size': None
                }
            elif message.video:
                file_data = {
                    'type': 'video',
                    'file_id': message.video.file_id,
                    'name': message.video.file_name or f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4",
                    'size': message.video.file_size
                }
            elif message.document:
                file_data = {
                    'type': 'document',
                    'file_id': message.document.file_id,
                    'name': message.document.file_name,
                    'size': message.document.file_size
                }
            
            if file_data:
                data = await state.get_data()
                files = data.get('files', [])
                files.append(file_data)
                await state.update_data(files=files)
                
                size_info = f" | {format_size(file_data['size'])}" if file_data['size'] else ""
                await message.answer(
                    f"✅ *Fayl qabul qilindi*\n\n"
                    f"📁 {file_data['name']}{size_info}\n"
                    f"📊 Jami: {len(files)} ta fayl\n\n"
                    f"Yana fayl yuborishingiz yoki /done yozishingiz mumkin.",
                    parse_mode="Markdown"
                )
            else:
                await message.answer(
                    "❌ *Iltimos, fayl yuboring*\n\n"
                    "Rasm, video yoki hujjat yuborishingiz mumkin.",
                    parse_mode="Markdown"
                )
        
        @self.dp.callback_query(F.data == "my_files")
        async def my_files(callback: CallbackQuery):
            if callback.from_user.id not in ADMIN_IDS:
                await callback.answer("❌ Ruxsat yo'q!", show_alert=True)
                return
            
            files = self.db.get_all_files()
            
            if not files:
                await callback.message.edit_text(
                    "📂 *Sizda hali fayllar mavjud emas*",
                    parse_mode="Markdown",
                    reply_markup=get_back_keyboard("admin")
                )
                await callback.answer()
                return
            
            await callback.message.edit_text(
                "📂 *Sizning fayllaringiz*\n\n"
                f"Jami: {len(files)} ta fayl to'plami",
                parse_mode="Markdown",
                reply_markup=get_files_keyboard(files)
            )
            await callback.answer()
        
        @self.dp.callback_query(F.data.startswith("view_file_"))
        async def view_file(callback: CallbackQuery):
            file_id = int(callback.data.split("_")[2])
            await callback.message.edit_text(
                "📁 *Fayl amallari*",
                parse_mode="Markdown",
                reply_markup=get_file_actions_keyboard(file_id)
            )
            await callback.answer()
        
        @self.dp.callback_query(F.data.startswith("download_file_"))
        async def download_file(callback: CallbackQuery):
            file_id = int(callback.data.split("_")[2])
            file_items = self.db.get_file_items(file_id)
            
            await callback.message.answer(
                f"📥 *{len(file_items)} ta fayl yuborilmoqda...*",
                parse_mode="Markdown"
            )
            
            for item in file_items:
                try:
                    caption = f"📁 {item['file_name'] or 'Fayl'}"
                    if item['file_size']:
                        caption += f" | {format_size(item['file_size'])}"
                    
                    if item['file_type'] == 'photo':
                        await callback.message.answer_photo(
                            item['telegram_file_id'],
                            caption=caption
                        )
                    elif item['file_type'] == 'video':
                        await callback.message.answer_video(
                            item['telegram_file_id'],
                            caption=caption
                        )
                    else:
                        await callback.message.answer_document(
                            item['telegram_file_id'],
                            caption=caption
                        )
                except Exception as e:
                    logger.error(f"Error sending file: {e}")
                    await callback.message.answer_document(item['telegram_file_id'])
            
            await callback.answer()
        
        @self.dp.callback_query(F.data.startswith("delete_file_"))
        async def delete_file(callback: CallbackQuery):
            file_id = int(callback.data.split("_")[2])
            self.db.delete_file(file_id)
            
            await callback.message.edit_text(
                "✅ *Fayl muvaffaqiyatli o'chirildi!*",
                parse_mode="Markdown",
                reply_markup=get_admin_main_keyboard()
            )
            await callback.answer()
        
        @self.dp.callback_query(F.data == "add_channel")
        async def add_channel_start(callback: CallbackQuery, state: FSMContext):
            if callback.from_user.id not in ADMIN_IDS:
                await callback.answer("❌ Ruxsat yo'q!", show_alert=True)
                return
            
            await callback.message.edit_text(
                "➕ *Kanal qo'shish*\n\n"
                "Kanal username yoki linkini yuboring:\n"
                "Masalan: `@kanal_nomi` yoki `https://t.me/kanal_nomi`\n\n"
                "⚠️ *Muhim:* Bot kanalda admin bo'lishi kerak!",
                parse_mode="Markdown",
                reply_markup=get_cancel_keyboard()
            )
            await state.set_state(AdminStates.waiting_for_channel)
            await callback.answer()
        
        @self.dp.message(AdminStates.waiting_for_channel)
        async def process_channel(message: Message, state: FSMContext):
            channel_username = extract_channel_username(message.text)
            
            if not channel_username:
                await message.answer(
                    "❌ *Noto'g'ri kanal formati*\n\n"
                    "Iltimos, qaytadan urinib ko'ring.\n"
                    "Masalan: @kanal_nomi yoki https://t.me/kanal_nomi",
                    parse_mode="Markdown"
                )
                return
            
            channel_info = await self.channel_checker.get_channel_info(channel_username)
            
            if not channel_info:
                await message.answer(
                    "❌ *Kanal topilmadi yoki bot kanalda admin emas*\n\n"
                    "Botni kanalga admin qilib qo'shing va qaytadan urinib ko'ring.",
                    parse_mode="Markdown"
                )
                return
            
            self.db.add_channel(
                channel_id=channel_info['id'],
                channel_title=channel_info['title'],
                added_by=message.from_user.id,
                channel_username=channel_info['username']
            )
            
            await message.answer(
                f"✅ *Kanal muvaffaqiyatli qo'shildi!*\n\n"
                f"📢 *Nomi:* {channel_info['title']}\n"
                f"🔗 *Username:* @{channel_info['username'] if channel_info['username'] else 'Noma\\lum'}\n\n"
                f"Endi foydalanuvchilar bu kanalga obuna bo'lishlari kerak.",
                parse_mode="Markdown"
            )
            await state.clear()
        
        @self.dp.callback_query(F.data == "remove_channel")
        async def remove_channel_list(callback: CallbackQuery):
            if callback.from_user.id not in ADMIN_IDS:
                await callback.answer("❌ Ruxsat yo'q!", show_alert=True)
                return
            
            channels = self.db.get_all_channels()
            
            if not channels:
                await callback.message.edit_text(
                    "❌ *Hech qanday kanal qo'shilmagan*",
                    parse_mode="Markdown",
                    reply_markup=get_back_keyboard("admin")
                )
                await callback.answer()
                return
            
            await callback.message.edit_text(
                "➖ *O'chiriladigan kanalni tanlang*",
                parse_mode="Markdown",
                reply_markup=get_channels_keyboard(channels, "remove")
            )
            await callback.answer()
        
        @self.dp.callback_query(F.data.startswith("remove_channel_"))
        async def remove_channel(callback: CallbackQuery):
            channel_id = int(callback.data.split("_")[2])
            channel = self.db.get_channel(channel_id)
            self.db.remove_channel(channel_id)
            
            await callback.message.edit_text(
                f"✅ *Kanal muvaffaqiyatli o'chirildi!*\n\n"
                f"📢 {channel['channel_title'] if channel else 'Kanal'}",
                parse_mode="Markdown",
                reply_markup=get_admin_main_keyboard()
            )
            await callback.answer()
        
        @self.dp.callback_query(F.data == "list_channels")
        async def list_channels(callback: CallbackQuery):
            if callback.from_user.id not in ADMIN_IDS:
                await callback.answer("❌ Ruxsat yo'q!", show_alert=True)
                return
            
            channels = self.db.get_all_channels()
            
            if not channels:
                await callback.message.edit_text(
                    "📋 *Hech qanday kanal qo'shilmagan*",
                    parse_mode="Markdown",
                    reply_markup=get_back_keyboard("admin")
                )
                await callback.answer()
                return
            
            text = "📋 *Majburiy kanallar ro'yxati:*\n\n"
            for i, channel in enumerate(channels, 1):
                username = f"@{channel['channel_username']}" if channel['channel_username'] else "🔒 Maxfiy kanal"
                text += f"{i}. *{channel['channel_title']}*\n   {username}\n"
            
            await callback.message.edit_text(
                text,
                parse_mode="Markdown",
                reply_markup=get_back_keyboard("admin")
            )
            await callback.answer()
        
        @self.dp.callback_query(F.data == "add_whitelist")
        async def add_whitelist_start(callback: CallbackQuery, state: FSMContext):
            if callback.from_user.id not in ADMIN_IDS:
                await callback.answer("❌ Ruxsat yo'q!", show_alert=True)
                return
            
            await callback.message.edit_text(
                "👤 *Whitelistga qo'shish*\n\n"
                "Foydalanuvchi username yoki ID sini yuboring:\n"
                "Masalan: `@username` yoki `123456789`\n\n"
                "Whitelistdagi foydalanuvchilar kanallarga obuna bo'lmasdan fayl olishlari mumkin.",
                parse_mode="Markdown",
                reply_markup=get_cancel_keyboard()
            )
            await state.set_state(AdminStates.waiting_for_whitelist_user)
            await callback.answer()
        
        @self.dp.message(AdminStates.waiting_for_whitelist_user)
        async def process_whitelist_add(message: Message, state: FSMContext):
            text = message.text.strip()
            user_id = None
            username = None
            user = None
            
            if text.startswith('@'):
                username = text[1:]
                user = self.db.get_user_by_username(username)
                if user:
                    user_id = user['telegram_id']
            elif text.isdigit():
                user_id = int(text)
                user = self.db.get_user(user_id)
            
            if not user_id or not user:
                await message.answer(
                    "❌ *Foydalanuvchi topilmadi!*\n\n"
                    "Foydalanuvchi avval botni ishga tushirgan bo'lishi kerak.",
                    parse_mode="Markdown"
                )
                return
            
            if self.db.add_to_whitelist(user_id, message.from_user.id):
                await message.answer(
                    f"✅ *Foydalanuvchi whitelistga qo'shildi!*\n\n"
                    f"👤 *Foydalanuvchi:* @{user['username'] or user_id}\n"
                    f"⚠️ Bu foydalanuvchi endi kanal majburiyatidan ozod qilindi.",
                    parse_mode="Markdown"
                )
            else:
                await message.answer(
                    "❌ *Xatolik yuz berdi*\n\n"
                    "Foydalanuvchi allaqachon whitelistda bo'lishi mumkin.",
                    parse_mode="Markdown"
                )
            
            await state.clear()
        
        @self.dp.callback_query(F.data == "remove_whitelist")
        async def remove_whitelist_list(callback: CallbackQuery):
            if callback.from_user.id not in ADMIN_IDS:
                await callback.answer("❌ Ruxsat yo'q!", show_alert=True)
                return
            
            whitelist = self.db.get_whitelist()
            
            if not whitelist:
                await callback.message.edit_text(
                    "❌ *Whitelist bo'sh*",
                    parse_mode="Markdown",
                    reply_markup=get_back_keyboard("admin")
                )
                await callback.answer()
                return
            
            await callback.message.edit_text(
                "➖ *Whitelistdan o'chiriladigan foydalanuvchini tanlang*",
                parse_mode="Markdown",
                reply_markup=get_whitelist_keyboard(whitelist)
            )
            await callback.answer()
        
        @self.dp.callback_query(F.data.startswith("remove_wl_"))
        async def remove_whitelist(callback: CallbackQuery):
            user_id = int(callback.data.split("_")[2])
            
            if self.db.remove_from_whitelist(user_id):
                user = self.db.get_user(user_id)
                username = user['username'] if user else str(user_id)
                
                await callback.message.edit_text(
                    f"✅ *Foydalanuvchi whitelistdan o'chirildi!*\n\n"
                    f"👤 @{username} endi kanallarga obuna bo'lishi kerak.",
                    parse_mode="Markdown",
                    reply_markup=get_admin_main_keyboard()
                )
            else:
                await callback.message.edit_text(
                    "❌ *Xatolik yuz berdi*",
                    parse_mode="Markdown",
                    reply_markup=get_admin_main_keyboard()
                )
            
            await callback.answer()
        
        @self.dp.callback_query(F.data == "statistics")
        async def show_statistics(callback: CallbackQuery):
            if callback.from_user.id not in ADMIN_IDS:
                await callback.answer("❌ Ruxsat yo'q!", show_alert=True)
                return
            
            stats = self.statistics.get_statistics()
            
            text = (
                "📊 *Bot statistikasi*\n\n"
                f"👥 *Jami foydalanuvchilar:* {stats['users_count']}\n"
                f"📁 *Jami fayl to'plamlari:* {stats['files_count']}\n"
                f"📄 *Jami fayllar:* {stats['file_items_count']}\n"
                f"📢 *Kanallar soni:* {stats['channels_count']}\n"
                f"👤 *Whitelist soni:* {stats['whitelist_count']}\n\n"
                f"📊 *Bot holati:* ✅ Ishlamoqda"
            )
            
            await callback.message.edit_text(
                text,
                parse_mode="Markdown",
                reply_markup=get_back_keyboard("admin")
            )
            await callback.answer()

# ==================== MAIN BOT CLASS ====================

class TelegramBot:
    def __init__(self):
        self.bot = Bot(token=BOT_TOKEN)
        self.storage = MemoryStorage()
        self.dp = Dispatcher(storage=self.storage)
        self.db = Database()
        self.channel_checker = ChannelChecker(self.bot)
        
        # Setup middleware
        self.dp.message.middleware(SubscriptionMiddleware(self.db, self.channel_checker))
        self.dp.callback_query.middleware(SubscriptionMiddleware(self.db, self.channel_checker))
        
        # Setup handlers
        self.handlers = BotHandlers(self.bot, self.dp, self.db, self.channel_checker)
    
    async def start(self):
        try:
            logger.info("Bot started successfully")
            print("🤖 Bot ishga tushdi! @devc0derweb")
            await self.dp.start_polling(self.bot)
        except Exception as e:
            logger.error(f"Bot crashed: {e}")
            print(f"❌ Bot ishdan chiqdi: {e}")
        finally:
            await self.bot.session.close()
    
    def run(self):
        asyncio.run(self.start())

# ==================== MAIN ENTRY POINT ====================

if __name__ == "__main__":
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not found in environment variables!")
        print("❌ BOT_TOKEN topilmadi! .env faylini tekshiring.")
        exit(1)
    
    print("""
    ╔════════════════════════════════════╗
    ║     🤖 Telegram Bot ishga tushmoqda    ║
    ║     👨‍💻 Yaratuvchi: @devc0derweb      ║
    ╚════════════════════════════════════╝
    """)
    
    bot = TelegramBot()
    bot.run()
