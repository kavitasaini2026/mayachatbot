"""
Maya Telegram Bot - Part 1
Master Admin ID: 8536757095
"""

import asyncio
import logging
import os
import random
import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
API_URL = os.environ.get("API_URL", "https://chikuu-bot-yi71.vercel.app").rstrip("/")
DB_PATH = os.environ.get("DB_PATH", "maya.db")

ADMIN_ID = 8536757095
IST = timezone(timedelta(hours=5, minutes=30))
HISTORY_FOR_API = 15

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
log = logging.getLogger("maya-bot")

# Fancy Font Converter (Dαιʟყ Bσηυѕ Style)
NORMAL_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
FANCY_CHARS  = "αвc∂єƒgнιנкℓмησρqяѕтυνωxуzAвCDEFGHIJкLMNσPQRѕTUνWXуZ"
FONT_MAP = str.maketrans(NORMAL_CHARS, FANCY_CHARS)

def to_fancy_font(text: str) -> str:
    return text.translate(FONT_MAP)

WELCOME_TEXT = "heyy!! welcome 🥰\nare you boy or girl? 👦👧 niche se select karo na 🌚👇"

HELP_TEXT = (
    "✨ <b>Maya Bot Commands Guide</b> ✨\n\n"
    "• /start - Bot start karein\n"
    "• /profile - Apni profile aur Maya ke saath bond dekhein\n"
    "• /mood - Maya ka current mood check karein\n"
    "• /feedback <msg> - Admin ko feedback/report bhejein\n"
    "• /reset - Chat history fresh karein\n"
    "• /help - Ye help menu dekhein"
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    gender TEXT,
    msg_count INTEGER NOT NULL DEFAULT 0,
    last_user_ts REAL,
    last_bot_ts REAL,
    affection_score INTEGER NOT NULL DEFAULT 50,
    bot_nickname TEXT,
    is_banned INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    text TEXT NOT NULL,
    ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

class DB:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def get_user(self, uid: int) -> sqlite3.Row:
        with self.lock:
            row = self.conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
            if row is None:
                nickname = random.choice(["Motu", "Chikni", "Pagal", "Jaanu", "Kamini", "Sali"])
                self.conn.execute("INSERT INTO users (user_id, bot_nickname) VALUES (?, ?)", (uid, nickname))
                self.conn.commit()
                row = self.conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
            return row

    def update(self, uid: int, **fields) -> None:
        if not fields:
            return
        sets = ", ".join(f"{k}=?" for k in fields)
        with self.lock:
            self.conn.execute(f"UPDATE users SET {sets} WHERE user_id=?", (*fields.values(), uid))
            self.conn.commit()

    def add_message(self, uid: int, role: str, text: str) -> None:
        with self.lock:
            self.conn.execute(
                "INSERT INTO messages (user_id, role, text, ts) VALUES (?, ?, ?, ?)",
                (uid, role, text, time.time()),
            )
            self.conn.commit()

    def history(self, uid: int, n: int = HISTORY_FOR_API) -> list:
        with self.lock:
            rows = self.conn.execute(
                "SELECT role, text FROM messages WHERE user_id=? ORDER BY id DESC LIMIT ?",
                (uid, n),
            ).fetchall()
        return [{"role": r["role"], "text": r["text"]} for r in reversed(rows)]

    def clear_history(self, uid: int) -> None:
        with self.lock:
            self.conn.execute("DELETE FROM messages WHERE user_id=?", (uid,))
            self.conn.commit()

    def count_users(self) -> int:
        with self.lock:
            return self.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def get_all_user_ids(self) -> list:
        with self.lock:
            rows = self.conn.execute("SELECT user_id FROM users").fetchall()
            return [r["user_id"] for r in rows]

    def count_messages(self) -> int:
        with self.lock:
            return self.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]

    def get_setting(self, key: str, default: str = "0") -> str:
        with self.lock:
            row = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self.lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
            )
            self.conn.commit()
            # --- PART 2 ---

def gender_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Boy 👦", callback_data="g:boy"),
                InlineKeyboardButton("Girl 👧", callback_data="g:girl"),
            ]
        ]
    )


def build_context(
    msg_count: int,
    gender: str = "boy",
    is_photo: bool = False,
    is_group: bool = False,
) -> str:
    dt = datetime.fromtimestamp(time.time(), IST)
    
    if is_group:
        type_rule = (
            "ENVIRONMENT: PUBLIC TELEGRAM GROUP CHAT.\n"
            "GENDER-NEUTRAL FLIRTING RULE: Speak in 100% gender-neutral Hinglish ('kahan the yrr', 'arey suno na', 'aag laga di 🌚', 'bestie', 'bro'). "
            "Flirt, tease, hype, and joke with everyone in the group playfully without specifying male/female grammar!"
        )
    else:
        type_rule = f"STRICT USER GENDER: {gender.upper()}. Be ultra-flirty, cute, teasing, and playful!"

    photo_rule = "PHOTO FLIRTING RULE: User sent a photo/selfie. Hype them up, flirt, and tease them dynamically! 🌚😍" if is_photo else ""

    return "\n".join([
        f"Time: {dt.strftime('%I:%M %p')}.",
        type_rule,
        photo_rule,
        "EMOJI STRICT RULE: DO NOT USE 🥺 EMOJI. Use: 💅🏼 😒 😋 🌚 😥 🤧 😗 🙂 🌝 😳 👀 🙄 🤣 😭 😑 😐 😍 😁 🥰",
        "PERSONA: Maya - Cheeky, flirty Gen-Z girl. Keep replies short, super engaging, witty, and playful!"
    ])


async def say_parts(app: Application, chat_id: int, parts: list, reply_to_id: Optional[int] = None) -> None:
    db: DB = app.bot_data["db"]
    is_fancy = db.get_setting("fancy_font", "0") == "1"

    for i, text in enumerate(parts):
        final_text = to_fancy_font(text) if is_fancy else text
        
        if i == 0 and reply_to_id:
            await app.bot.send_message(chat_id, final_text, reply_to_message_id=reply_to_id)
        else:
            await app.bot.send_message(chat_id, final_text)


async def process_user_input(
    app: Application, chat_id: int, uid: int, text: str, is_photo: bool = False, is_group: bool = False, msg_id: Optional[int] = None
) -> None:
    db: DB = app.bot_data["db"]
    http: httpx.AsyncClient = app.bot_data["http"]
    
    row = db.get_user(uid)
    if row["is_banned"] == 1:
        if not is_group:
            await app.bot.send_message(chat_id, "🚫 You are banned from using Maya.")
        return

    gender = row["gender"] or "boy"
    db.update(uid, msg_count=row["msg_count"] + 1)

    context_text = build_context(row["msg_count"], gender=gender, is_photo=is_photo, is_group=is_group)
    payload = {
        "message": text if text else "Photo reaction",
        "user_id": str(uid),
        "gender": gender,
        "context": context_text,
        "history": db.history(uid) if not is_group else [],
    }

    try:
        r = await http.post(f"{API_URL}/chat", json=payload, timeout=60)
        data = r.json()
        parts = data.get("messages") or [data.get("reply", "haan bolo? 👀")]
    except Exception:
        parts = ["haan bolo? 🌚", "kya chal raha hai? ✨"]

    if not is_group:
        db.add_message(uid, "user", text if text else "[Photo]")
        db.add_message(uid, "model", " ".join(parts))

    await say_parts(app, chat_id, parts, reply_to_id=msg_id if is_group else None)


async def handle_incoming_msg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg, user, chat = update.effective_message, update.effective_user, update.effective_chat
    if not msg or not user or not chat:
        return

    is_group = chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)
    text = msg.text or msg.caption or ""
    bot_username = (context.bot.username or "").lower()

    if is_group:
        is_mentioned = bot_username and f"@{bot_username}" in text.lower()
        is_name_called = bool(re.search(r"\bmaya\b", text, re.IGNORECASE))
        is_reply_to_bot = bool(
            msg.reply_to_message
            and msg.reply_to_message.from_user
            and msg.reply_to_message.from_user.id == context.bot.id
        )

        if not (is_mentioned or is_name_called or is_reply_to_bot):
            return

        clean_text = re.sub(rf"@{bot_username}", "", text, flags=re.IGNORECASE) if bot_username else text
        await process_user_input(
            context.application, chat.id, user.id, clean_text.strip(), is_photo=bool(msg.photo), is_group=True, msg_id=msg.message_id
        )
    else:
        db: DB = context.application.bot_data["db"]
        row = db.get_user(user.id)
        
        if not row["gender"] and not text.startswith("/"):
            await msg.reply_text(WELCOME_TEXT, reply_markup=gender_keyboard())
            return

        await process_user_input(
            context.application, chat.id, user.id, text, is_photo=bool(msg.photo), is_group=False
            )
        # --- PART 3 ---

async def on_gender(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q or not q.data:
        return
    app = context.application
    db: DB = app.bot_data["db"]
    uid = q.from_user.id
    row = db.get_user(uid)

    if row["gender"]:
        try:
            await q.edit_message_text(text=f"Aapka gender pehle se saved hai: {row['gender'].upper()} ✨")
        except BadRequest:
            pass
        await q.answer()
        return

    data = q.data
    if data in ("g:boy", "g:girl"):
        gender = "boy" if data == "g:boy" else "girl"
        db.update(uid, gender=gender)
        try:
            await q.edit_message_text(text=f"Confirmed: {gender.upper()} 👦👧\n✨ Profile updated!")
        except BadRequest:
            pass

        chat_id = q.message.chat_id if q.message else uid
        hello = "hiii 🌚 mai maya... bolo kya chal raha hai?" if gender == "boy" else "heyyy chikni 💖 kya chal raha hai?"
        db.add_message(uid, "model", hello)
        await say_parts(app, chat_id, [hello])


def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or not is_admin(user.id):
        return
    db: DB = context.application.bot_data["db"]
    font_status = "ON ✨" if db.get_setting("fancy_font", "0") == "1" else "OFF 📝"

    panel = (
        "<b>👑 MAYA BOT MASTER ADMIN DASHBOARD</b>\n\n"
        f"• <code>/togglefont</code> : Fancy Font (Current: {font_status})\n"
        "• <code>/stats</code> : Live system stats\n"
        "• <code>/broadcast &lt;msg&gt;</code> : Broadcast to Users\n"
        "• <code>/broadcast &lt;group_id&gt; &lt;msg&gt;</code> : Broadcast to Group\n"
    )
    await update.effective_message.reply_html(panel)


async def admin_toggle_font(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or not is_admin(user.id):
        return
    db: DB = context.application.bot_data["db"]
    current = db.get_setting("fancy_font", "0")
    new_val = "1" if current == "0" else "0"
    db.set_setting("fancy_font", new_val)
    await update.effective_message.reply_text(f"Fancy Font: {'ENABLED ✨' if new_val == '1' else 'DISABLED 📝'}")


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or not is_admin(user.id):
        return
    db: DB = context.application.bot_data["db"]
    stats_text = (
        f"<b>📊 SYSTEM STATS</b>\n\n"
        f"👥 Total Users: <code>{db.count_users()}</code>\n"
        f"💬 Messages Logged: <code>{db.count_messages()}</code>\n"
    )
    await update.effective_message.reply_html(stats_text)


async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or not is_admin(user.id):
        return
    args = context.args
    if not args:
        await update.effective_message.reply_text("Usage: /broadcast <msg> OR /broadcast <group_id> <msg>")
        return

    db: DB = context.application.bot_data["db"]
    if args[0].startswith("-100") or (args[0].startswith("-") and args[0][1:].isdigit()):
        try:
            await context.application.bot.send_message(args[0], f"📢 <b>Announcement:</b>\n\n{' '.join(args[1:])}", parse_mode="HTML")
            await update.effective_message.reply_text("✅ Group Broadcast Sent!")
        except Exception as e:
            await update.effective_message.reply_text(f"❌ Error: {e}")
        return

    msg_text = " ".join(args)
    sent = 0
    for uid in db.get_all_user_ids():
        try:
            await context.application.bot.send_message(uid, f"📢 <b>Announcement:</b>\n\n{msg_text}", parse_mode="HTML")
            sent += 1
            await asyncio.sleep(0.04)
        except Exception:
            pass
    await update.effective_message.reply_text(f"✅ Sent to {sent} users!")


async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, msg, chat = update.effective_user, update.effective_message, update.effective_chat
    if not user or not msg:
        return
    if chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        await msg.reply_text("heyy guys! 👋 Maya is active here! Just tag me or reply to my message to chat 💖")
        return
    
    db: DB = context.application.bot_data["db"]
    row = db.get_user(user.id)
    if not row["gender"]:
        await msg.reply_text(WELCOME_TEXT, reply_markup=gender_keyboard())
    else:
        await msg.reply_text("heyy aa gaye fir se? 🌚 kya chal raha hai?")


async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    db: DB = context.application.bot_data["db"]
    row = db.get_user(user.id)
    text = (
        f"💖 <b>MAYA'S BOND PROFILE</b> 💖\n\n"
        f"👤 User ID: <code>{user.id}</code>\n"
        f"🏷️ Gender: <code>{(row['gender'] or 'Not Set').upper()}</code>\n"
        f"💬 Messages: <code>{row['msg_count']}</code>\n"
        f"💞 Affection: <code>{row['affection_score']}/100</code>\n"
        f"🐾 Nickname: <b>{row['bot_nickname']}</b>"
    )
    await update.effective_message.reply_html(text)


async def cmd_mood(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    db: DB = context.application.bot_data["db"]
    row = db.get_user(user.id)
    score = row["affection_score"]
    mood_desc = "Happy & Playful 🥰" if score > 50 else "Thoda gussa ya mood off 😒"
    await update.effective_message.reply_text(f"Maya's Current Mood: {mood_desc}")


async def cmd_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    msg_text = " ".join(context.args)
    if not msg_text:
        await update.effective_message.reply_text("Usage: /feedback <message>")
        return
    try:
        await context.application.bot.send_message(
            ADMIN_ID, f"📩 <b>Feedback from {user.id}:</b>\n\n{msg_text}", parse_mode="HTML"
        )
        await update.effective_message.reply_text("✅ Feedback sent to admin!")
    except Exception:
        await update.effective_message.reply_text("❌ Error sending feedback.")


async def on_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        await update.effective_message.reply_html(HELP_TEXT)


async def on_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, msg = update.effective_user, update.effective_message
    if not user or not msg:
        return
    db: DB = context.application.bot_data["db"]
    db.clear_history(user.id)
    await msg.reply_text("done 🥰 chat fresh kar di ✨")


async def post_init(app: Application) -> None:
    app.bot_data["db"] = DB(DB_PATH)
    app.bot_data["http"] = httpx.AsyncClient()


def build_app() -> Application:
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN missing.")
    
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("stats", admin_stats))
    app.add_handler(CommandHandler("togglefont", admin_toggle_font))
    app.add_handler(CommandHandler("broadcast", admin_broadcast))

    app.add_handler(CommandHandler("start", on_start))
    app.add_handler(CommandHandler("reset", on_reset))
    app.add_handler(CommandHandler("profile", cmd_profile))
    app.add_handler(CommandHandler("mood", cmd_mood))
    app.add_handler(CommandHandler("feedback", cmd_feedback))
    app.add_handler(CommandHandler("help", on_help))

    app.add_handler(CallbackQueryHandler(on_gender, pattern=r"^g:(boy|girl)$"))

    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_incoming_msg))

    return app


if __name__ == "__main__":
    build_app().run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
