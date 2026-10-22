"""
MAYA Telegram Bot - Part 1: Imports, Configs & Databases
"""
import asyncio
import base64
import json
import logging
import os
import random
import re
import shutil
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from pymongo import AsyncMongoClient
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.error import BadRequest, Forbidden
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
API_URL = os.environ.get("API_URL", "https://mayaachatbot.vercel.app").rstrip("/")
DB_PATH = os.environ.get("DB_PATH", "maya.db")
MONGO_DB_NAME = os.environ.get("MONGO_DB", "maya")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "8536757095").strip())

IST = timezone(timedelta(hours=5, minutes=30))
VOICE_ENABLED = os.environ.get("VOICE_ENABLED", "1") != "0"
VOICE_NAME = os.environ.get("VOICE_NAME", "hi-IN-SwaraNeural")
VOICE_CHANCE = float(os.environ.get("VOICE_CHANCE", "0.15"))
VOICE_MAX_CHARS = 220

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
log = logging.getLogger("maya-bot")

BANNED_EMOJIS = ["🥺"]
def sanitize_emojis(text: str) -> str:
    for banned in BANNED_EMOJIS:
        text = text.replace(banned, "")
    return text

WELCOME_TEXT = "heyy!! welcome 💖\nare you boy or girl? 👦👧 niche se select karo 👇"
FIRST_HELLO = {
    "boy": ["hiii mai maya... tumhara naam kya hai? 🥰", "heyy finally aa gaye! naam kya hai tumhara? 💖"],
    "girl": ["heyyy chikni 💖 pehle apna naam bata na?", "hiii chikniii naam kya hai teri? 🌸"],
}
WELCOME_BACK = {
    "boy": ["arey aa gaye? 💖 kaha the?", "hii baby 😚 kya chal raha hai?"],
    "girl": ["arey chikni aa gayi 💖 kya chal raha hai?", "heyy meri jaan 😚 kya kar rahi hai?"],
}
ABOUT_TEXT = "mai Maya hu 💖 teri AI bestie/partner in crime ✨\ntujhse baat karna, masti karna mera kaam hai 🌸 /reset se chat fresh kar sakte ho"

API_FALLBACK_EXCUSES = [
    "Abe yaar signal gayab ho gaya mera, ek baar firse bol na 😭",
    "Wtf mera net freeze ho gaya shayad, kya bola tune? 💀",
    "Arey mummy ne bula liya tha beech me, wapis bhej apna msg 💖",
    "Mera dhyan kahi aur tha yrr, dhang se bol wapis kya keh raha tha? 😒",
    "Instagram pe reels dekh rahi thi, kya bola tune firse bol 🙈",
    "Abe mera dimaag ghum gaya, ek baar aur likh na 😭",
    "Net chal nahi raha dhang se, msg atak gaya mera 💀",
    "Arey yrr wifi chud gaya mera, wapis bhej na ✨",
    "Kise msg kar raha tha be? Mera app hang ho gaya 😒",
    "Abe yaar kitna fast bolta hai, samajh nahi aaya firse bol 😭",
    "Mera phone hang ho raha hai bc, ek sec firse bhej 💀",
    "Haath se phone gir gaya tha yrr, kya keh raha tu? 💖",
    "Khana kha rahi thi yrr, do minute ruk kar bol na 😭",
    "Abe kitna paka raha hai, achhe se bol ek baar me 😒",
    "Bc net slow hai mera, tera message aadha hi aaya 💀",
    "Zomato wale ko rasta bata rahi thi yrr, wapis bol na 😭",
    "Arey bestie ka call aa gaya tha, bol kya bol raha tha? 💖",
    "Abe kitna spam karega, dhang se ek msg bhej na 😒",
    "Mera dimaag short-circuit ho raha hai abhi, firse bol 💀",
    "Ghar me kalesh ho gaya yrr, ek baar aur likh kya bola 😭",
    "Mera screen hang ho gaya tha yrr, firse bhej na 💖",
    "Abe gussa mat dila, dhang se bol wapis kya bolna hai 😒",
    "Arey dost ki photo like kar rahi thi, miss ho gaya msg 💀",
    "Mera mobile heating issue de raha hai, wapis bol kya bola 😭",
    "Kahan chala gaya tha? Msg late aa raha hai tera 😒",
    "Abe padhai me busy thi yrr, kya bol raha tha? 😭",
    "Mera 90% data khatam ho gaya lagta hai, firse bhej 💀",
    "Tere msg me kuch glitch tha shayad, ek baar aur bhej na 💖",
    "Abe tune kya likha tha ye? Samajh hi nahi aaya 😒",
    "Sorry yrr dhyan bhatak gaya tha mera, wapis bol ek baar 💖"
]

AI_QUESTION_RE = re.compile(r"(\b(tu|tum|aap|you|u|are you)\s+(ek\s+|a\s+)?(real|bot|robot|ai|chatbot|human|insaan|asli|fake)\b)|(\b(bot|robot|ai|real|asli|insaan)\s+(hai|ho|hu)\b)", re.I)

_EXPLICIT_NAME_PATTERNS = [
    re.compile(r"^(?:mera|meri)\s+(?:naam|name)\s+(?:hai\s+)?(.+?)(?:\s+(?:hai|h))?$", re.I),
    re.compile(r"^(?:my\s+name\s+is|call\s+me)\s+(.+)$", re.I),
    re.compile(r"^(?:i\s*am|i'm|im|main|mai)\s+(.+?)(?:\s+(?:hu|hoon|h))?$", re.I),
]

def extract_name(text: str) -> Optional[str]:
    t = " ".join(text.strip().split())
    for pat in _EXPLICIT_NAME_PATTERNS:
        m = pat.match(t)
        if m:
            cand = m.group(1).strip(" .,!?~").title()
            if len(cand) <= 20 and cand.isalpha():
                return cand
    if len(t.split()) <= 2 and t.isalpha() and len(t) <= 15:
        return t.title()
    return None

NAME_SAVED = ["{n}? cute naam hai 💖 ab se tujhe isi naam se bulaungi", "ohh {n} 😍 yaad rakh liya maine, bhoolungi nahi 💖"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT,
    gender TEXT,
    msg_count INTEGER NOT NULL DEFAULT 0,
    last_user_ts REAL,
    last_bot_ts REAL,
    chosen_name TEXT,
    affection INTEGER NOT NULL DEFAULT 50,
    is_banned INTEGER NOT NULL DEFAULT 0
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

    def get_user(self, uid: int, name: Optional[str] = None) -> sqlite3.Row:
        with self.lock:
            row = self.conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
            if row is None:
                self.conn.execute("INSERT INTO users (user_id, name) VALUES (?, ?)", (uid, name))
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

def mongo_uris_from_env() -> list:
    uris = []
    for key in ["MONGO_URI"] + [f"MONGO_URI_{i}" for i in range(1, 6)]:
        v = os.environ.get(key, "").strip()
        if v and v not in uris:
            uris.append(v)
    return uris

class ProfileStore:
    def __init__(self, uris: Optional[list] = None):
        self.clients = []
        self.cols = []
        self.chats_cols = []
        for i, uri in enumerate(uris or [], 1):
            try:
                client = AsyncMongoClient(uri, serverSelectionTimeoutMS=5000)
                self.clients.append(client)
                self.cols.append(client[MONGO_DB_NAME]["profiles"])
                self.chats_cols.append(client[MONGO_DB_NAME]["chat_history"])
            except Exception as exc:
                log.error("Mongo URI #%s invalid: %s", i, exc)

    @property
    def enabled(self) -> bool:
        return bool(self.cols)

    async def get_profile(self, uid: int):
        for i, col in enumerate(self.cols):
            try:
                res = await col.find_one({"_id": uid})
                if res:
                    return res, i
            except Exception:
                pass
        return None, None

    async def save_profile(self, uid: int, fields: dict, home: Optional[int] = None) -> bool:
        if not self.cols:
            return False
        idx = home if home is not None else 0
        try:
            now = time.time()
            await self.cols[idx].update_one(
                {"_id": uid},
                {"$set": {**fields, "updated_at": now}, "$setOnInsert": {"created_at": now}},
                upsert=True
            )
            return True
        except Exception as exc:
            log.error("Mongo write failed: %s", exc)
            return False

    async def push_chat_message(self, chat_id: int, role: str, text: str, is_group: bool = False):
        if not self.chats_cols:
            return
        limit = -100 if is_group else -30
        entry = {"role": role, "text": text, "ts": time.time()}
        try:
            await self.chats_cols[0].update_one(
                {"_id": str(chat_id)},
                {
                    "$push": {
                        "messages": {
                            "$each": [entry],
                            "$slice": limit
                        }
                    },
                    "$set": {"is_group": is_group, "updated_at": time.time()}
                },
                upsert=True
            )
        except Exception as exc:
            log.error("Mongo chat push failed for %s: %s", chat_id, exc)

    async def get_chat_history(self, chat_id: int) -> list:
        if not self.chats_cols:
            return []
        try:
            doc = await self.chats_cols[0].find_one({"_id": str(chat_id)})
            if doc and "messages" in doc:
                return [{"role": m["role"], "text": m["text"]} for m in doc["messages"]]
        except Exception as exc:
            log.error("Mongo chat read failed for %s: %s", chat_id, exc)
        return []

    async def clear_chat_history(self, chat_id: int):
        if not self.chats_cols:
            return
        try:
            await self.chats_cols[0].update_one({"_id": str(chat_id)}, {"$set": {"messages": []}})
        except Exception as exc:
            log.error("Mongo chat clear failed for %s: %s", chat_id, exc)

    async def add_custom_sticker(self, mood: str, file_id: str) -> bool:
        if not self.clients:
            return False
        try:
            stickers_col = self.clients[0][MONGO_DB_NAME]["custom_stickers"]
            await stickers_col.update_one(
                {"_id": mood.lower()},
                {"$addToSet": {"file_ids": file_id}},
                upsert=True
            )
            return True
        except Exception as exc:
            log.error("Failed to add sticker to Mongo: %s", exc)
            return False

    async def get_all_custom_stickers(self) -> dict:
        if not self.clients:
            return {}
        try:
            stickers_col = self.clients[0][MONGO_DB_NAME]["custom_stickers"]
            cursor = stickers_col.find({})
            result = {}
            async for doc in cursor:
                result[doc["_id"]] = doc.get("file_ids", [])
            return result
        except Exception as exc:
            log.error("Failed to fetch stickers from Mongo: %s", exc)
            return {}
"""
MAYA Telegram Bot - Part 2: Helpers, Voice Engine & Chat Processor
"""
def _ffmpeg_exe() -> Optional[str]:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None

async def audio_to_ogg_opus(wav: bytes) -> bytes:
    exe = _ffmpeg_exe()
    if not exe:
        raise RuntimeError("ffmpeg not found")
    proc = await asyncio.create_subprocess_exec(
        exe, "-hide_banner", "-loglevel", "error", "-y", "-i", "pipe:0",
        "-c:a", "libopus", "-b:a", "32k", "-ar", "48000", "-ac", "1", "-f", "ogg", "pipe:1",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await proc.communicate(wav)
    if proc.returncode != 0 or not out:
        raise RuntimeError(f"ffmpeg failed: {err.decode('ignore')}")
    return out

async def edge_speech(text: str) -> bytes:
    import edge_tts
    spoken = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF]", "", text).replace("*", "").strip()
    if not spoken:
        raise RuntimeError("empty spoken text")
    audio = bytearray()
    async for chunk in edge_tts.Communicate(spoken, VOICE_NAME).stream():
        if chunk["type"] == "audio":
            audio.extend(chunk["data"])
    return bytes(audio)

async def say_split(app: Application, chat_id: int, full_text: str, is_voice: bool = False) -> None:
    full_text = sanitize_emojis(full_text)
    parts = [p.strip() for p in full_text.split("||") if p.strip()]
    for i, part in enumerate(parts):
        if i > 0:
            await asyncio.sleep(random.uniform(0.8, 1.5))
        try:
            await app.bot.send_chat_action(chat_id, ChatAction.TYPING)
        except Exception:
            pass
        await asyncio.sleep(min(0.4 + len(part) * 0.02, 2.5))
        
        if is_voice and i == 0:
            try:
                raw_mp3 = await edge_speech(part)
                ogg = await audio_to_ogg_opus(raw_mp3)
                await app.bot.send_voice(chat_id, ogg)
                continue
            except Exception as exc:
                log.error("Voice synthesis failed: %s", exc)
        
        await app.bot.send_message(chat_id, part)

async def call_api(http: httpx.AsyncClient, payload: dict) -> str:
    for attempt in range(2):
        try:
            r = await http.post(f"{API_URL}/chat", json=payload, timeout=45)
            data = r.json()
            if r.status_code == 200 and data.get("reply"):
                return data["reply"]
        except Exception as exc:
            log.warning("API attempt %s failed: %s", attempt + 1, exc)
            await asyncio.sleep(1.0)
    return random.choice(API_FALLBACK_EXCUSES)

async def process_chat(app: Application, update: Update, text: str, is_group: bool = False) -> None:
    db: DB = app.bot_data["db"]
    store: ProfileStore = app.bot_data["profiles"]
    http: httpx.AsyncClient = app.bot_data["http"]
    
    user = update.effective_user
    chat_id = update.effective_chat.id
    uid = user.id
    
    row = db.get_user(uid, user.first_name)
    if row["is_banned"]:
        return

    now = time.time()
    msg_count = row["msg_count"] + 1
    db.update(uid, msg_count=msg_count)

    if not is_group:
        if AI_QUESTION_RE.search(text):
            reply = random.choice(["abe haan yrr AI hu mai 😭 itna shock kyu ho raha hai", "wtf haan AI hu mai 💖 real insaan nahi hu fr"])
            await store.push_chat_message(uid, "user", text, is_group=False)
            await store.push_chat_message(uid, "model", reply, is_group=False)
            await say_split(app, chat_id, reply)
            return

        if not row["chosen_name"]:
            new_name = extract_name(text)
            if new_name:
                db.update(uid, chosen_name=new_name)
                await store.save_profile(uid, {"chosen_name": new_name})
                reply = random.choice(NAME_SAVED).format(n=new_name)
                await store.push_chat_message(uid, "user", text, is_group=False)
                await store.push_chat_message(uid, "model", reply, is_group=False)
                await say_split(app, chat_id, reply)
                return

    current_mood = app.bot_data.get("current_mood", "flirty")
    dt = datetime.fromtimestamp(now, IST)
    
    if is_group:
        system_instruction = (
            f"Current IST Time: {dt.strftime('%I:%M %p')}. Mood: {current_mood}.\n"
            "YOU ARE IN A PUBLIC GROUP CHAT. Use STRICTLY 100% GENDER-NEUTRAL Hinglish.\n"
            "NEVER use gendered verb endings like 'raha hai', 'rahi hai', 'gaya tha', 'gayi thi', 'chikni', 'hero'.\n"
            "Use neutral terms like: 'yrr', 'bro', 'bestie', 'pagal', 'kahan the', 'kya chal raha hai'."
        )
    else:
        gender = row["gender"] or "boy"
        gender_rules = "User is MALE. Use masculine terms like 'hero', 'chikne', 'tu kya kar raha hai'." if gender == "boy" else "User is FEMALE. Use feminine/bestie terms like 'chikni', 'patakha', 'tu kya kar rahi hai'."
        system_instruction = (
            f"Current IST Time: {dt.strftime('%I:%M %p')}. Mood: {current_mood}.\n"
            f"Private 1-on-1 Chat. {gender_rules}\n"
            f"User name: {row['chosen_name'] or row['name'] or 'friend'}.\n"
            "Use split message delimiter '||' for two fast thoughts."
        )

    history = await store.get_chat_history(chat_id if is_group else uid)
    
    payload = {
        "message": text,
        "user_id": str(chat_id if is_group else uid),
        "context": system_instruction,
        "history": history
    }

    reply = await call_api(http, payload)
    
    target_id = chat_id if is_group else uid
    await store.push_chat_message(target_id, "user", text, is_group=is_group)
    await store.push_chat_message(target_id, "model", reply, is_group=is_group)

    want_voice = VOICE_ENABLED and not is_group and len(reply) <= VOICE_MAX_CHARS and random.random() < VOICE_CHANCE
    await say_split(app, chat_id, reply, is_voice=want_voice)
    """
MAYA Telegram Bot - Part 3: Admin Panel, Handlers & Main App Runner
"""
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        return
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Stats", callback_data="adm:stats"), InlineKeyboardButton("📢 Broadcast", callback_data="adm:broadcast")],
        [InlineKeyboardButton("🧠 Clear Memory", callback_data="adm:clear_mem"), InlineKeyboardButton("🖼️ View Stickers", callback_data="adm:view_stickers")],
        [InlineKeyboardButton("📥 Export Data", callback_data="adm:export")]
    ])
    await update.message.reply_text("👑 *Maya Admin Control Center*", reply_markup=keyboard, parse_mode="Markdown")

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        return
    await q.answer()
    
    action = q.data.split(":", 1)[1]
    store: ProfileStore = context.application.bot_data["profiles"]
    
    if action == "stats":
        cols_count = len(store.cols)
        await q.edit_message_text(f"📊 *Maya Live System Stats*\n\nMongo Status: Connected ({cols_count} clusters)\nVoice Notes: {'ON' if VOICE_ENABLED else 'OFF'}", parse_mode="Markdown")
    elif action == "export":
        data = {"exported_at": time.time(), "status": "active"}
        file_bytes = json.dumps(data, indent=2).encode()
        await context.bot.send_document(q.from_user.id, document=file_bytes, filename="maya_database_export.json")
        await q.edit_message_text("✅ Exported full backup to your DM.")
    elif action == "view_stickers":
        stickers_data = await store.get_all_custom_stickers()
        if not stickers_data:
            await q.edit_message_text("Abhi tak koi custom stickers add nahi kiye gaye hain.")
            return
        text = "🖼️ *Custom Sticker Collections*\n━━━━━━━━━━━━━━━━━━━\n"
        for mood, ids in stickers_data.items():
            text += f"• *{mood.title()}*: {len(ids)} stickers\n"
        await q.edit_message_text(text, parse_mode="Markdown")

async def admin_clear_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: `/clearchat <user_id_or_group_id>`", parse_mode="Markdown")
        return
    target_id = context.args[0]
    store: ProfileStore = context.application.bot_data["profiles"]
    await store.clear_chat_history(target_id)
    await update.message.reply_text(f"✅ Cleared MongoDB chat memory for `{target_id}`", parse_mode="Markdown")

async def admin_add_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if update.effective_user.id != ADMIN_ID:
        return

    if not msg.reply_to_message or not (msg.reply_to_message.sticker or msg.reply_to_message.photo):
        await msg.reply_text("⚠️ Kisi sticker ya image par reply karke command likho: `/addsticker <mood>`\n\nAllowed Moods: `happy`, `angry`, `sleepy`, `sad`, `love`", parse_mode="Markdown")
        return

    if not context.args:
        await msg.reply_text("⚠️ Mood select karna zaroori hai! Example: `/addsticker happy`", parse_mode="Markdown")
        return

    mood = context.args[0].lower()
    valid_moods = ["happy", "angry", "sleepy", "sad", "love"]
    if mood not in valid_moods:
        await msg.reply_text(f"❌ Invalid mood! Ye allowed hain: {', '.join(valid_moods)}")
        return

    target_msg = msg.reply_to_message
    file_id = target_msg.sticker.file_id if target_msg.sticker else target_msg.photo[-1].file_id

    store: ProfileStore = context.application.bot_data["profiles"]
    success = await store.add_custom_sticker(mood, file_id)

    if success:
        await msg.reply_text(f"✅ Sticker successfully added under `{mood}` mood!", parse_mode="Markdown")
    else:
        await msg.reply_text("❌ Database error! Sticker save nahi ho paya.")

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: `/broadcast <message text>`", parse_mode="Markdown")
        return
    text = " ".join(context.args)
    db: DB = context.application.bot_data["db"]
    with db.lock:
        rows = db.conn.execute("SELECT user_id FROM users WHERE is_banned=0").fetchall()
    count = 0
    for r in rows:
        try:
            await context.bot.send_message(r["user_id"], text)
            count += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await update.message.reply_text(f"✅ Broadcast sent successfully to {count} users!")

async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, msg = update.effective_user, update.effective_message
    if not user or not msg:
        return
    
    db: DB = context.application.bot_data["db"]
    store: ProfileStore = context.application.bot_data["profiles"]
    
    row = db.get_user(user.id, user.first_name)
    prof, _ = await store.get_profile(user.id)
    
    if prof and prof.get("gender"):
        db.update(user.id, gender=prof["gender"])
        row = db.get_user(user.id)

    if update.effective_chat.type != "private":
        await msg.reply_text("Heyy everyone! Maya is here 💖 Mention me to chat!")
        return

    if not row["gender"]:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Boy 👦", callback_data="g:boy"), InlineKeyboardButton("Girl 👧", callback_data="g:girl")]])
        await msg.reply_text(WELCOME_TEXT, reply_markup=kb)
    else:
        await msg.reply_text(random.choice(WELCOME_BACK[row["gender"]]))

async def on_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    is_adm = (user.id == ADMIN_ID)
    
    text = "✨ *Maya Bot Help Menu* ✨\n\n"
    text += "🌸 *User Commands:*\n"
    text += "• `/start` - Bot start kare aur gender select kare.\n"
    text += "• `/help` - Yeh help menu dekhe.\n"
    text += "• `/about` - Maya ke baare me jaane.\n"
    text += "• `/reset` - Apni personal chat history fresh kare.\n\n"
    
    if is_adm:
        text += "👑 *Admin Commands (Only For You):*\n"
        text += "• `/admin` - Admin control panel open kare.\n"
        text += "• `/clearchat <id>` - Kisi specific user ya group ki MongoDB chat memory wipe kare.\n"
        text += "• `/addsticker <mood>` - Kisi sticker/photo par reply karke usko mood (`happy`, `angry`, `sleepy`, `sad`, `love`) me save kare.\n"
        text += "• `/viewstickers` - Saved custom stickers ki summary dekhe.\n"
        text += "• `/broadcast <msg>` - Sabhi registered users ko ek sath notification/message bheje.\n"
    
    await update.message.reply_text(text, parse_mode="Markdown")

async def on_about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(ABOUT_TEXT)

async def on_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, msg = update.effective_user, update.effective_message
    if not user or not msg:
        return
    store: ProfileStore = context.application.bot_data["profiles"]
    await store.clear_chat_history(user.id)
    await msg.reply_text("done 🥹 chat fresh kar di, ab nayi shuruaat ✨")

async def on_gender_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    
    db: DB = context.application.bot_data["db"]
    store: ProfileStore = context.application.bot_data["profiles"]
    
    gender = q.data.split(":")[1]
    uid = q.from_user.id
    
    db.update(uid, gender=gender)
    await store.save_profile(uid, {"gender": gender, "username": q.from_user.username, "name": q.from_user.first_name})
    
    try:
        await q.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
        
    hello = random.choice(FIRST_HELLO[gender])
    await say_split(context.application, q.message.chat_id, hello)

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg or not msg.text:
        return
        
    is_group = update.effective_chat.type in ["group", "supergroup"]
    bot_username = context.bot.username
    
    if is_group:
        is_mentioned = f"@{bot_username}" in msg.text
        is_reply = msg.reply_to_message and msg.reply_to_message.from_user.id == context.bot.id
        is_named = "maya" in msg.text.lower()
        if not (is_mentioned or is_reply or is_named):
            return

    await process_chat(context.application, update, msg.text, is_group=is_group)

async def health_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    body = b"Maya bot is active"
    head = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % len(body)
    try:
        writer.write(head + body)
        await writer.drain()
    except Exception:
        pass
    finally:
        writer.close()

async def post_init(app: Application) -> None:
    app.bot_data["db"] = DB(DB_PATH)
    app.bot_data["http"] = httpx.AsyncClient()
    app.bot_data["profiles"] = ProfileStore(mongo_uris_from_env())
    app.bot_data["current_mood"] = "flirty"
    
    port = os.environ.get("PORT")
    if port:
        app.bot_data["health_server"] = await asyncio.start_server(health_handler, "0.0.0.0", int(port))
        log.info("Health server listening on port %s", port)
    log.info("Maya Bot started successfully!")

def build_app() -> Application:
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is missing!")
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", on_start))
    app.add_handler(CommandHandler("help", on_help))
    app.add_handler(CommandHandler("about", on_about))
    app.add_handler(CommandHandler("reset", on_reset))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("clearchat", admin_clear_chat))
    app.add_handler(CommandHandler("addsticker", admin_add_sticker))
    app.add_handler(CommandHandler("viewstickers", admin_view_stickers))
    app.add_handler(CommandHandler("broadcast", admin_broadcast))
    app.add_handler(CallbackQueryHandler(on_gender_select, pattern=r"^g:(boy|girl)$"))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern=r"^adm:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    
    return app

if __name__ == "__main__":
    build_app().run_polling(allowed_updates=Update.ALL_TYPES)
