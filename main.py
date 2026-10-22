"""
Maya Telegram bot (Render Web Service ready, MongoDB profile storage). - Part 1
"""
import asyncio
import base64
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

# ---------------------------------------------------------------------------
# Config & Timezone
# ---------------------------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
API_URL = os.environ.get("API_URL", "https://chikuu-bot-yi71.vercel.app").rstrip("/")
DB_PATH = os.environ.get("DB_PATH", "maya.db")
MONGO_DB_NAME = os.environ.get("MONGO_DB", "maya")

IST = timezone(timedelta(hours=5, minutes=30))
QUIET_START_HOUR = 0
QUIET_END_HOUR = 8
HISTORY_FOR_API = 12
MONGO_RETRY_SECONDS = 120

STICKER_PACK = os.environ.get("STICKER_PACK", "")
STICKER_MOODS = ["happy", "angry", "sleepy", "sad", "love"]
STICKER_EVERY = (3, 5)
STICKER_CHANCE = float(os.environ.get("STICKER_CHANCE", "0.6"))

VOICE_ENABLED = os.environ.get("VOICE_ENABLED", "1") != "0"
VOICE_ENGINE = os.environ.get("VOICE_ENGINE", "edge").strip().lower()
VOICE_NAME = os.environ.get("VOICE_NAME", "hi-IN-SwaraNeural")
VOICE_CHANCE = float(os.environ.get("VOICE_CHANCE", "0.15"))
VOICE_GAP = int(os.environ.get("VOICE_GAP", "10"))
VOICE_MAX_CHARS = 220

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("maya-bot")

# ---------------------------------------------------------------------------
# Texts (Full Baddie / Girlfriend Vibe)
# ---------------------------------------------------------------------------
WELCOME_TEXT = "heyy!! welcome 💖\nare you boy or girl? 👦👧 niche se select karo nh 👇"
PICK_GENDER_TEXT = "Select your gender frist....🫣👇"

FIRST_HELLO = {
    "boy": ["hiii 🥺 mai maya... tumhara naam kya hai?", "heyy 🥹 finally aa gaye! naam kya hai tumhara?"],
    "girl": ["heyyy chikni 💖 pehle apna naam bata na?", "hiii chikniii 🥺 naam kya hai teri?"],
}
WELCOME_BACK = {
    "boy": ["arey aa gaye? 🥺 kaha the?", "hii baby 😚 kya chal raha hai?"],
    "girl": ["arey chikni aa gayi 🥺 kya chal raha hai?", "heyy meri jaan 😚 kya kar rahi hai?"],
}
ABOUT_TEXT = (
    "mai Maya hu 💖 teri bestie/partner in crime 🥺\n"
    "tujhse baat karna, masti karna mera kaam hai ✨ /reset se chat fresh kar sakte ho"
)

DENY_AI_REPLIES = [
    "abe sale gadhe! 😭 mai insaan hu, tere jaise pagal thodi hu bc jo aisi bakwaas kar raha hai 💅",
    "wtf is wrong with you? 💀 khud pagalon jaisi baatein karta hai aur mujhe aisi cheezein bolta hai 😒",
    "mc shakal dekhi hai apni jo mujhe aisi faltu baatein bol raha hai? chup chap dhang se baat kar na 😡",
    "abey oye! 🤬 agar agli baar aisi faltu baatein ki na toh block kar dungi, real hu mai 😤",
]

FALLBACK_ERRORS = [
    "wtf yaar, dimag kharab mat kar mera 😭 kuch bhi bole jaa raha hai sale",
    "kya bakwaas hai ye mc, dimaag mat kha mera chup chap kuch dhang ka bol 💀",
    "mera dhyan kahi aur tha yrr, tu aisi faltu baatein karega toh ignore hi karungi na 😒",
    "mood off kar diya tu ne ekdum, baad me baat karugi jaa 💅",
]
API_FAIL_REPLIES = [
    "mujhe abhi baat nahi karni tere se, dimag mat kha mera bc 😭",
    "tera message dekh ke hi gussa aa jata hai sale, chup ho ja thodi der 💀",
]
EMPTY_REPLIES = [
    "wtf kuch samajh nahi aaya kya bol gaya tu bc 😭",
    "kya bakwaas hai ye, kuch aur bol na sale 💀",
]

TECH_FORCED = [
    "kitni baar bolu bc ki mujhe ye coding-shoding me koi interest nahi hai! 😒 dimag mat kha mera",
    "wtf is wrong with you? har waqt padhai ya code 💀 jaa nikal pehli fursat me sale",
    "abe gadhe, mai koi teacher ya notebook hu kya? 😭 in sab faltu cheezon ke liye mat bol mujhe mc",
]
TECH_FOLLOWUP = "acha sun, dimag mat chala mera aur ye bata khana khaya ya nahi?"

NUDGE_1 = {
    "boy": [
        "arey seen karke bhaag gaya sale? 😒",
        "hello? zinda hai ya mar gaya bc? 💀",
        "accha ignore? samajh gayi tera attitude mc 😏",
    ],
    "girl": [
        "arey chikni seen karke bhaag gayi? 😒",
        "hello? zinda hai kya bc? 💀",
        "accha ignore? samajh gayi tera attitude 😏",
        "chikni aaj chup hai, kahi uska wait toh nahi kar rahi jo seen tak nahi karta sale 💀",
    ],
}
NUDGE_2 = [
    "thik hai mat kar reply, mai bhi baat nahi karungi ab bhad me ja sale 😒💅",
    "ok bye, jaa rahi sone mood mat kharab kar mc 🥺",
]

TRAPS = [
    (
        "t1",
        "ek question puchu? 2+2 kitna hota hai?",
        re.compile(r"\b4\b|char|four", re.I),
        "toh phir usne tujhe kyu chhoda sale? 4 bhi nahi sambhal paya? 💀😭",
    ),
    (
        "t2",
        "din me kitne ghante hote hai?",
        re.compile(r"\b24\b|chaubis|twenty", re.I),
        "toh 24 ghante me ek ghanta bhi usko teri yaad nahi aayi bc? 💀",
    ),
    (
        "t3",
        "paani kaisa hota hai?",
        re.compile(r"thand|cold|cool", re.I),
        "tere jokes ki tarah bekar sale? 😏",
    ),
]

# ---------------------------------------------------------------------------
# Detectors & Name Extractors
# ---------------------------------------------------------------------------
AI_QUESTION_RE = re.compile(
    r"(\b(tu|tum|tm|aap|you|u|r u|are you|are u)\s+(ek\s+|a\s+|an\s+)?"
    r"(real|bot|robot|ai|chatbot|human|insaan|asli|fake)\b)"
    r"|(\b(bot|robot|ai|chatbot|real|asli|insaan|human)\s+(hai|ho|h|hu)\b)"
    r"|(\breal\s+(ladki|girl)\b)",
    re.I,
)

TECH_RE = re.compile(
    r"\b(code|coding|python|java|javascript|html|css|api|script|program|programming|"
    r"bug|error|homework|assignment|essay|maths?|solve|equation|translate|translation|"
    r"gk|pdf|excel|resume|paragraph|summary|summarize|formula|calculate|algorithm|"
    r"github|linux|database|sql|file)\b",
    re.I,
)

VOICE_REQUEST_RE = re.compile(
    r"(voice|awaaz|awaz|aawaz|audio).{0,20}(bhej|send|sun|do\b|de\b|dena|chahiye|note|msg|message|bol)"
    r"|(bhej|send|sun|bol)\w*.{0,12}(voice|awaaz|awaz|audio)"
    r"|\bvoice\s*note\b|\bsunao\b|\bsuna\s*do\b",
    re.I,
)


def is_voice_request(text: str) -> bool:
    return bool(VOICE_REQUEST_RE.search(text))


def is_ai_question(text: str) -> bool:
    return bool(AI_QUESTION_RE.search(text))


def is_tech_request(text: str) -> bool:
    return bool(TECH_RE.search(text))


NAME_SAVED = [
    "{n}? cute naam hai 🥺💖 ab se tujhe isi naam se bulaungi",
    "ohh {n} 😍 yaad rakh liya maine, bhoolungi nahi 🫶🏻",
    "{n} hmm... theek hai pasand aaya sale 😏💖",
]
NAME_STOPWORDS = {
    "hi", "hii", "hiii", "hello", "hey", "heyy", "haan", "han", "ha", "nahi", "nhi", "no", "yes", "ok",
    "okay", "kya", "kuch", "bol", "bata", "batao", "btao", "tum", "tu", "aap", "mai", "main", "me", "mera",
    "meri", "naam", "name", "bhai", "didi", "jaanu", "baby", "pata", "idk", "kaun", "kon", "kyu", "kyun",
    "hmm", "hm", "acha", "accha", "thik", "theek", "fine", "good", "sad", "happy", "bore", "busy", "bas",
    "sona", "babu", "jan", "tera", "teri", "tumhara", "tumhari", "pehle", "abhi", "wapas",
}
_NAME_OK = re.compile(r"^[^\W\d_]+(?:[ '.-][^\W\d_]+)?$", re.UNICODE)
_EXPLICIT_NAME_PATTERNS = [
    re.compile(r"^(?:mera|meri)\s+(?:naam|name|nam)\s+(?:hai\s+)?(.+?)(?:\s+(?:hai|h|he|hain))?$", re.I),
    re.compile(r"^(?:my\s+name\s+is|my\s+name's|call\s+me|name\s+is)\s+(.+)$", re.I),
    re.compile(r"^(?:naam|name)\s+(?:hai\s+)?(.+?)(?:\s+(?:hai|h))?$", re.I),
    re.compile(r"^(.+?)\s+(?:naam\s+hai\s+mera|hai\s+mera\s+naam)$", re.I),
]
_LOOSE_NAME_PATTERNS = [
    re.compile(r"^(?:i\s*am|i'm|im|main|mai|mein)\s+(.+?)(?:\s+(?:hu|hoon|hun|h))?$", re.I),
    re.compile(r"^(?:mera|meri)\s+(.+?)\s+(?:hai|h|he)$", re.I),
    re.compile(r"^(.+?)\s+(?:hu|hoon|hun)$", re.I),
]


def _valid_name(candidate: str) -> Optional[str]:
    c = candidate.strip(" .,!?~")
    if not c or len(c) > 20 or not _NAME_OK.match(c):
        return None
    if any(w in NAME_STOPWORDS for w in c.lower().split()):
        return None
    return c.title()


def extract_name(text: str, awaiting: bool = False) -> Optional[str]:
    t = " ".join(text.strip().split())
    patterns = _EXPLICIT_NAME_PATTERNS + (_LOOSE_NAME_PATTERNS if awaiting else [])
    for pat in patterns:
        m = pat.match(t)
        if m:
            name = _valid_name(m.group(1))
            if name:
                return name
    return _valid_name(t) if awaiting else None


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    gender TEXT,
    msg_count INTEGER NOT NULL DEFAULT 0,
    last_user_ts REAL,
    last_bot_ts REAL,
    nudge_stage INTEGER NOT NULL DEFAULT 2,
    next_nudge_at REAL,
    pending_trap TEXT,
    trap_next_at INTEGER NOT NULL DEFAULT 0,
    tech_count INTEGER NOT NULL DEFAULT 0,
    chosen_name TEXT,
    awaiting_name INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    text TEXT NOT NULL,
    ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_user ON messages(user_id, id);
"""

USER_COLUMNS = {
    "gender", "msg_count", "last_user_ts", "last_bot_ts",
    "nudge_stage", "next_nudge_at", "pending_trap", "trap_next_at",
    "tech_count", "chosen_name", "awaiting_name",
}


class DB:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.conn.executescript(SCHEMA)
            existing = {r[1] for r in self.conn.execute("PRAGMA table_info(users)")}
            if "chosen_name" not in existing:
                self.conn.execute("ALTER TABLE users ADD COLUMN chosen_name TEXT")
            if "awaiting_name" not in existing:
                self.conn.execute("ALTER TABLE users ADD COLUMN awaiting_name INTEGER NOT NULL DEFAULT 0")
            self.conn.commit()

    def get_user(self, uid: int) -> sqlite3.Row:
        with self.lock:
            row = self.conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
            if row is None:
                self.conn.execute("INSERT INTO users (user_id) VALUES (?)", (uid,))
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

    def due_nudges(self, now: float) -> list:
        with self.lock:
            return self.conn.execute(
                "SELECT * FROM users WHERE nudge_stage < 2 AND next_nudge_at IS NOT NULL "
                "AND next_nudge_at <= ?",
                (now,),
            ).fetchall()
            """
Maya Telegram bot - Part 2
"""
def mongo_uris_from_env() -> list:
    uris = []
    for key in ["MONGO_URI"] + [f"MONGO_URI_{i}" for i in range(1, 6)]:
        value = os.environ.get(key, "").strip()
        if value and value not in uris:
            uris.append(value)
    return uris


class ProfileStore:
    """Stores ONLY Gender and User-provided Real Name in MongoDB."""
    def __init__(self, uris: Optional[list] = None, collections: Optional[list] = None):
        self.clients: list = []
        self.cols: list = []
        if collections is not None:
            self.cols = list(collections)
            return
        for i, uri in enumerate(uris or [], 1):
            try:
                client = AsyncMongoClient(uri, serverSelectionTimeoutMS=5000)
                self.clients.append(client)
                self.cols.append(client[MONGO_DB_NAME]["profiles"])
            except Exception:
                log.exception("Mongo URI #%s is invalid, skipped", i)

    @property
    def enabled(self) -> bool:
        return bool(self.cols)

    async def check(self) -> None:
        for i, client in enumerate(self.clients, 1):
            try:
                await client.admin.command("ping")
                log.info("Mongo #%s connected", i)
            except Exception as exc:
                log.error("Mongo #%s NOT reachable: %s", i, exc)

    async def close(self) -> None:
        for client in self.clients:
            try:
                await client.close()
            except Exception:
                pass

    async def _find(self, i: int, uid: int):
        return await self.cols[i].find_one({"_id": uid})

    async def get(self, uid: int):
        results = await asyncio.gather(
            *(self._find(i, uid) for i in range(len(self.cols))), return_exceptions=True
        )
        had_error = False
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                had_error = True
            elif res:
                return res, i, had_error
        return None, None, had_error

    async def save(self, uid: int, fields: dict, home: Optional[int] = None) -> bool:
        n = len(self.cols)
        if n == 0:
            return False
        if home is None:
            _profile, home, _err = await self.get(uid)
        order = [home] if home is not None else [(uid + k) % n for k in range(n)]
        now = time.time()
        for i in order:
            try:
                await self.cols[i].update_one(
                    {"_id": uid},
                    {"$set": {**fields, "updated_at": now}, "$setOnInsert": {"created_at": now}},
                    upsert=True,
                )
                return True
            except Exception:
                pass
        return False


async def load_user(app: Application, tg_user) -> sqlite3.Row:
    db: DB = app.bot_data["db"]
    uid = tg_user.id
    row = db.get_user(uid)
    store: Optional[ProfileStore] = app.bot_data.get("profiles")
    if not store or not store.enabled:
        return row
    synced: set = app.bot_data.setdefault("synced", set())
    retry_at: dict = app.bot_data.setdefault("retry_at", {})
    now = time.time()
    if uid in synced or now < retry_at.get(uid, 0):
        return row

    profile, home, had_error = await store.get(uid)
    if profile is None and had_error:
        retry_at[uid] = now + MONGO_RETRY_SECONDS
        return row

    if profile:
        updates = {}
        if profile.get("gender") and not row["gender"]:
            db.update(uid, gender=profile["gender"])
            row = db.get_user(uid)
        if profile.get("chosen_name") and not row["chosen_name"]:
            db.update(uid, chosen_name=profile["chosen_name"], awaiting_name=0)
            row = db.get_user(uid)
        
        mongo_updates = {}
        if row["gender"] and not profile.get("gender"):
            mongo_updates["gender"] = row["gender"]
        if row["chosen_name"] and profile.get("chosen_name") != row["chosen_name"]:
            mongo_updates["chosen_name"] = row["chosen_name"]
        if mongo_updates:
            if not await store.save(uid, mongo_updates, home):
                retry_at[uid] = now + MONGO_RETRY_SECONDS
                return row
        synced.add(uid)
        return row

    fields = {}
    if row["gender"]:
        fields["gender"] = row["gender"]
    if row["chosen_name"]:
        fields["chosen_name"] = row["chosen_name"]
    if fields:
        ok = await store.save(uid, fields)
        if ok:
            synced.add(uid)
        else:
            retry_at[uid] = now + MONGO_RETRY_SECONDS
    return row


def gender_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Boy 👦", callback_data="g:boy"),
                InlineKeyboardButton("Girl 👧", callback_data="g:girl"),
            ]
        ]
    )


def part_of_day(hour: int) -> str:
    if hour < 5:
        return "late night"
    if hour < 12:
        return "morning"
    if hour < 17:
        return "afternoon"
    if hour < 21:
        return "evening"
    return "night"


def gap_hint(now: float, last_bot_ts: Optional[float]) -> Optional[str]:
    if not last_bot_ts:
        return None
    gap = now - last_bot_ts
    if gap < 0:
        return None
    today = datetime.fromtimestamp(now, IST).date()
    last_day = datetime.fromtimestamp(last_bot_ts, IST).date()
    mins = gap / 60
    if today != last_day and gap > 6 * 3600:
        return 'User replied the next day. You may roast like: "kal ka message aaj bhej raha hai sale? itna bhav kyu kha raha hai bc? 😭".'
    if mins < 5:
        return None
    if mins < 20:
        return 'User replied after about 5-15 minutes. You may tease like: "5 min baad yaad aayi meri? itna kahan busy tha sale? 😒".'
    if mins < 50:
        return 'User replied after about half an hour. You may tease like: "aadhe ghante baad reply? wah bhai wah sale".'
    if mins < 180:
        return 'User replied after 1-2 hours. You may tease like: "1 ghante baad? kisi aur se chat chal rahi thi kya teri mc? 😒💀".'
    return 'User replied after 3+ hours. You may say like: "3 ghante baad? mai toh so gayi thi ya fir ignore maar rahi thi sale 🥺".'


def closeness(msg_count: int) -> str:
    if msg_count < 15:
        return "Closeness: stranger. You are a real human girl who is sarcastic, moody, sassy, and uses words like wtf, bc, sale."
    if msg_count < 60:
        return "Closeness: getting close. Playful, dramatic, using heavy Gen-Z lingo, wtf, bc, mc, and roast banter as a possessive girlfriend/bestie."
    return "Closeness: very close. Full unfiltered masti, heavy gaali-galoch style friendly banter (bc, mc, sale, abey) as a close partner/girlfriend."


def clean_name(name: Optional[str]) -> str:
    return re.sub(r"[^\w .'-]", "", name or "", flags=re.UNICODE).strip()[:30]


def build_context(
    msg_count: int,
    now: float,
    last_bot_ts: Optional[float],
    extra: Optional[str] = None,
    name: Optional[str] = None,
) -> str:
    dt = datetime.fromtimestamp(now, IST)
    lines = [
        f"Current time in India (IST): {dt.strftime('%I:%M %p')} ({part_of_day(dt.hour)}).",
        closeness(msg_count),
        "CRITICAL INSTRUCTION: You are a real human girl / girlfriend. NEVER claim to be an AI, robot, or computer program. "
        "If anyone asks if you are an AI or bot, get deeply offended, use aggressive Gen-Z slang (wtf, bc, sale, mc, abey), "
        "and insist you are a real human girl.",
    ]
    nm = clean_name(name)
    if nm:
        lines.append(f"User's real chosen name: {nm}. Use it naturally during conversation.")
    hint = gap_hint(now, last_bot_ts)
    if hint and random.random() < 0.7:
        lines.append(hint)
    if random.random() < 0.30:
        lines.append('Roast hint: give a savage Gen-Z roast this time using words like bc/sale, then add "mazak kar rahi hu yrr pighal mat itna 💀".')
    if random.random() < 0.20:
        lines.append("Style hint: stretch a word or use heavy Gen-Z slang naturally (like wtf, frrrr, bc, sale, mc).")
    if extra:
        lines.append(extra)
    return "\n".join(lines)


async def say(app: Application, chat_id: int, text: str, typing: bool = True) -> None:
    if typing:
        try:
            await app.bot.send_chat_action(chat_id, ChatAction.TYPING)
        except Exception:
            pass
        await asyncio.sleep(min(0.5 + len(text) * 0.03, 3.0))
    await app.bot.send_message(chat_id, text)


def _pack_name(token: str) -> str:
    t = token.strip()
    if "addstickers/" in t:
        t = t.split("addstickers/", 1)[1]
    return t.split("?")[0].strip("/ ")


def sticker_config_from_env() -> dict:
    default = [x for x in (_pack_name(v) for v in os.environ.get("STICKER_PACK", "").split(",")) if x]
    cfg = {}
    for mood in STICKER_MOODS:
        raw = os.environ.get(f"STICKER_{mood.upper()}", "")
        items = [x for x in (_pack_name(v) for v in raw.split(",")) if x]
        cfg[mood] = items or default
    cfg["any"] = default
    return cfg


async def load_stickers(app: Application) -> dict:
    cfg = sticker_config_from_env()
    cache: dict = {}
    result: dict = {}
    for mood, items in cfg.items():
        ids: list = []
        for item in items:
            if len(item) >= 60:
                ids.append(item)
                continue
            if item not in cache:
                try:
                    pack = await app.bot.get_sticker_set(item)
                    cache[item] = [st.file_id for st in pack.stickers]
                except Exception:
                    cache[item] = []
            ids.extend(cache[item])
        result[mood] = ids
    return result


def sticker_due(app: Application, uid: int) -> bool:
    state = app.bot_data.setdefault("sticker_state", {})
    count, target = state.get(uid, (0, random.randint(*STICKER_EVERY)))
    count += 1
    if count >= target:
        state[uid] = (0, random.randint(*STICKER_EVERY))
        return random.random() <= STICKER_CHANCE
    state[uid] = (count, target)
    return False


async def maybe_sticker(app: Application, chat_id: int, mood: Optional[str], uid: Optional[int] = None) -> None:
    pools = app.bot_data.get("stickers") or {}
    ids = pools.get(mood or "") or pools.get("any")
    if not ids:
        return
    if not sticker_due(app, uid if uid is not None else chat_id):
        return
    try:
        await app.bot.send_sticker(chat_id, random.choice(ids))
    except Exception:
        pass


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
        raise RuntimeError("ffmpeg is not available")
    proc = await asyncio.create_subprocess_exec(
        exe, "-hide_banner", "-loglevel", "error", "-y", "-i", "pipe:0",
        "-c:a", "libopus", "-b:a", "32k", "-ar", "48000", "-ac", "1", "-f", "ogg", "pipe:1",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(wav), timeout=30)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError("ffmpeg timed out")
    if proc.returncode != 0 or not out:
        raise RuntimeError(f"ffmpeg failed")
    return out


wav_to_ogg_opus = audio_to_ogg_opus

_EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200d]")


def speakable(text: str) -> str:
    text = _EMOJI_RE.sub("", text).replace("*", "").replace("_", " ")
    return re.sub(r"\s+", " ", text).strip()


async def edge_speech(text: str) -> bytes:
    import edge_tts
    audio = bytearray()
    async for chunk in edge_tts.Communicate(text, VOICE_NAME).stream():
        if chunk["type"] == "audio":
            audio.extend(chunk["data"])
    if not audio:
        raise RuntimeError("edge-tts returned no audio")
    return bytes(audio)


async def gemini_speech(http: httpx.AsyncClient, text: str) -> bytes:
    r = await http.post(f"{API_URL}/tts", json={"text": text}, timeout=90)
    data = r.json()
    if r.status_code != 200 or not data.get("success"):
        raise RuntimeError("TTS API error")
    return base64.b64decode(data["audio_b64"])


async def synth_voice(app: Application, text: str) -> bytes:
    if VOICE_ENGINE == "gemini":
        audio = await gemini_speech(app.bot_data["http"], text)
    else:
        spoken = speakable(text)
        if not spoken:
            raise RuntimeError("nothing to speak")
        audio = await edge_speech(spoken)
    return await audio_to_ogg_opus(audio)


async def send_voice_reply(app: Application, chat_id: int, text: str) -> bool:
    try:
        await app.bot.send_chat_action(chat_id, ChatAction.RECORD_VOICE)
    except Exception:
        pass
    try:
        ogg = await synth_voice(app, text)
        await app.bot.send_voice(chat_id, ogg)
        return True
    except Exception:
        return False


def voice_due(app: Application, uid: int) -> bool:
    state = app.bot_data.setdefault("voice_state", {})
    since = state.get(uid, VOICE_GAP) + 1
    state[uid] = since
    return since > VOICE_GAP and random.random() < VOICE_CHANCE


def schedule_nudge(db: DB, uid: int, now: float) -> None:
    db.update(
        uid,
        last_bot_ts=now,
        nudge_stage=0,
        next_nudge_at=now + random.uniform(180, 300),
    )


async def call_api(http: httpx.AsyncClient, payload: dict) -> dict:
    last_exc: Optional[Exception] = None
    for attempt in range(2):
        try:
            r = await http.post(f"{API_URL}/chat", json=payload, timeout=60)
            data = r.json()
            if r.status_code == 200 and data.get("success"):
                return data
            last_exc = RuntimeError(f"API error")
        except Exception as exc:
            last_exc = exc
        await asyncio.sleep(1.0)
    raise last_exc


async def remember_name(app: Application, uid: int, name: str) -> None:
    db: DB = app.bot_data["db"]
    db.update(uid, chosen_name=name, awaiting_name=0)
    store: Optional[ProfileStore] = app.bot_data.get("profiles")
    if store and store.enabled:
        if not await store.save(uid, {"chosen_name": name}):
            app.bot_data.setdefault("synced", set()).discard(uid)
            app.bot_data.setdefault("retry_at", {}).pop(uid, None)
"""
Maya Telegram bot - Part 3
"""
async def process_message(app: Application, chat_id: int, uid: int, text: str) -> None:
    db: DB = app.bot_data["db"]
    http: httpx.AsyncClient = app.bot_data["http"]
    row = db.get_user(uid)
    gender = row["gender"]
    now = time.time()

    prev_bot_ts = row["last_bot_ts"]
    msg_count = row["msg_count"] + 1
    trap_next_at = row["trap_next_at"] or (msg_count + random.randint(5, 6))
    db.update(
        uid,
        msg_count=msg_count,
        last_user_ts=now,
        nudge_stage=2,
        next_nudge_at=None,
        trap_next_at=trap_next_at,
    )

    if is_ai_question(text):
        reply = random.choice(DENY_AI_REPLIES)
        db.add_message(uid, "user", text)
        db.add_message(uid, "model", reply)
        await say(app, chat_id, reply)
        schedule_nudge(db, uid, time.time())
        return

    awaiting = bool(row["awaiting_name"])
    if awaiting and msg_count > 5:
        db.update(uid, awaiting_name=0)
        awaiting = False
    new_name = extract_name(text, awaiting)
    if new_name:
        await remember_name(app, uid, new_name)
        reply = random.choice(NAME_SAVED).format(n=new_name)
        db.add_message(uid, "user", text)
        db.add_message(uid, "model", reply)
        await say(app, chat_id, reply)
        schedule_nudge(db, uid, time.time())
        return

    pending = row["pending_trap"]
    if pending:
        db.update(uid, pending_trap=None)
        for tid, _q, pattern, punch in TRAPS:
            if tid == pending and pattern.search(text):
                db.add_message(uid, "user", text)
                db.add_message(uid, "model", punch)
                await say(app, chat_id, punch)
                schedule_nudge(db, uid, time.time())
                return

    extra = None
    if is_tech_request(text):
        tech_count = row["tech_count"] + 1
        if tech_count >= 3:
            forced = random.choice(TECH_FORCED)
            db.update(uid, tech_count=0)
            db.add_message(uid, "user", text)
            db.add_message(uid, "model", forced)
            await say(app, chat_id, forced)
            await asyncio.sleep(random.uniform(2, 4))
            db.add_message(uid, "model", TECH_FOLLOWUP)
            await say(app, chat_id, TECH_FOLLOWUP)
            schedule_nudge(db, uid, time.time())
            return
        db.update(uid, tech_count=tech_count)
        extra = (
            "The user asked for technical, coding, or study help. Do NOT answer it. "
            "Get annoyed, use heavy Gen-Z slang and abuses (like bc, sale, wtf), "
            "make an excuse that you hate studies, and change the topic."
        )
    elif row["tech_count"]:
        db.update(uid, tech_count=0)

    context_text = build_context(msg_count, now, prev_bot_ts, extra, row["chosen_name"])
    payload = {
        "message": text,
        "user_id": str(uid),
        "gender": gender,
        "context": context_text,
        "history": db.history(uid),
    }
    try:
        data = await call_api(http, payload)
    except Exception as exc:
        log.error("API call failed for user %s: %s", uid, exc)
        await say(app, chat_id, random.choice(FALLBACK_ERRORS + API_FAIL_REPLIES), typing=False)
        return

    reply = (data.get("reply") or "").strip() or random.choice(EMPTY_REPLIES)
    db.add_message(uid, "user", text)
    db.add_message(uid, "model", reply)
    due = voice_due(app, uid)
    want_voice = VOICE_ENABLED and len(reply) <= VOICE_MAX_CHARS and (is_voice_request(text) or due)
    if want_voice and await send_voice_reply(app, chat_id, reply):
        app.bot_data.setdefault("voice_state", {})[uid] = 0
    else:
        await say(app, chat_id, reply)
    await maybe_sticker(app, chat_id, data.get("mood"), uid)
    schedule_nudge(db, uid, time.time())

    fresh = db.get_user(uid)
    if msg_count >= fresh["trap_next_at"] and not extra:
        tid, question, _pattern, _punch = random.choice(TRAPS)
        await asyncio.sleep(random.uniform(2, 4))
        db.add_message(uid, "model", question)
        await say(app, chat_id, question)
        db.update(uid, pending_trap=tid, trap_next_at=msg_count + random.randint(5, 6))
        schedule_nudge(db, uid, time.time())


# ---------------------------------------------------------------------------
# Telegram handlers
# ---------------------------------------------------------------------------
async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, msg = update.effective_user, update.effective_message
    if not user or not msg:
        return
    row = await load_user(context.application, user)
    if not row["gender"]:
        await msg.reply_text(WELCOME_TEXT, reply_markup=gender_keyboard())
    else:
        await msg.reply_text(random.choice(WELCOME_BACK[row["gender"]]))


async def on_gender(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q or not q.data:
        return
    app = context.application
    db: DB = app.bot_data["db"]
    uid = q.from_user.id
    row = await load_user(app, q.from_user)

    if row["gender"]:
        await q.answer(text="⚠️ Aapne apna gender pehle hi choose kar liya hai! Ye change nahi ho sakta.", show_alert=True)
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except BadRequest:
            pass
        return

    gender = q.data.split(":", 1)[1] if ":" in q.data else ""
    if gender not in ("boy", "girl"):
        return

    alert_msg = f"Selected: {gender.upper()} 👦👧\n⚠️ Confirm! Aap ise aage kabhi change nahi kar payenge."
    await q.answer(text=alert_msg, show_alert=True)

    now = time.time()
    db.update(uid, gender=gender, awaiting_name=0 if row["chosen_name"] else 1)

    store: Optional[ProfileStore] = app.bot_data.get("profiles")
    if store and store.enabled:
        ok = await store.save(uid, {"gender": gender})
        if ok:
            app.bot_data.setdefault("synced", set()).add(uid)

    try:
        await q.edit_message_reply_markup(reply_markup=None)
    except BadRequest:
        pass

    chat_id = q.message.chat_id if q.message else uid
    hello = random.choice(FIRST_HELLO[gender])
    db.add_message(uid, "model", hello)
    await say(app, chat_id, hello)
    schedule_nudge(db, uid, now)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg, user = update.effective_message, update.effective_user
    if not msg or not msg.text or not user:
        return
    row = await load_user(context.application, user)
    if not row["gender"]:
        await msg.reply_text(PICK_GENDER_TEXT, reply_markup=gender_keyboard())
        return
    await process_message(context.application, msg.chat_id, user.id, msg.text)


async def on_other(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg, user = update.effective_message, update.effective_user
    if not msg or not user:
        return
    row = await load_user(context.application, user)
    if not row["gender"]:
        await msg.reply_text(PICK_GENDER_TEXT, reply_markup=gender_keyboard())
        return
    reply = random.choice(
        ["ye kya bheja sale? mujhe nahi dikh raha yrr 🥺 likh ke bol na bc", "mera net slow hai yrr, text me bata na mc 🥺"]
    )
    await msg.reply_text(reply)


async def on_about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(ABOUT_TEXT)


async def on_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, msg = update.effective_user, update.effective_message
    if not user or not msg:
        return
    db: DB = context.application.bot_data["db"]
    db.get_user(user.id)
    db.clear_history(user.id)
    db.update(user.id, pending_trap=None, tech_count=0, nudge_stage=2, next_nudge_at=None)
    await msg.reply_text("done 🥹 chat fresh kar di, ab nayi shuruaat sale ✨")


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("Unhandled error while handling update: %s", update, exc_info=context.error)


# ---------------------------------------------------------------------------
# Seen-nudge scanner (Strictly IST Hours Checked)
# ---------------------------------------------------------------------------
async def scan_nudges(app: Application, now: Optional[float] = None) -> None:
    db: DB = app.bot_data["db"]
    now = now if now is not None else time.time()
    for row in db.due_nudges(now):
        uid = row["user_id"]
        gender = row["gender"] or "boy"
        hour = datetime.fromtimestamp(now, IST).hour
        if QUIET_START_HOUR <= hour < QUIET_END_HOUR:
            db.update(uid, nudge_stage=2, next_nudge_at=None)
            continue
        try:
            if row["nudge_stage"] == 0:
                base = row["last_bot_ts"] or now
                if random.random() < 0.70:
                    text = random.choice(NUDGE_1[gender])
                    db.add_message(uid, "model", text)
                    await say(app, uid, text, typing=False)
                    db.update(uid, nudge_stage=1, next_nudge_at=now + random.uniform(600, 1200))
                else:
                    db.update(
                        uid,
                        nudge_stage=1,
                        next_nudge_at=max(now + 60, base + random.uniform(900, 1500)),
                    )
            else:
                text = random.choice(NUDGE_2)
                db.add_message(uid, "model", text)
                await say(app, uid, text, typing=False)
                db.update(uid, nudge_stage=2, next_nudge_at=None)
        except Forbidden:
            db.update(uid, nudge_stage=2, next_nudge_at=None)
        except Exception:
            db.update(uid, nudge_stage=2, next_nudge_at=None)


async def nudge_loop(app: Application) -> None:
    while True:
        try:
            await scan_nudges(app)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(30)


async def health_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        await asyncio.wait_for(reader.read(1024), timeout=5)
    except Exception:
        pass
    body = b"Maya bot is alive"
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

    uris = mongo_uris_from_env()
    store = ProfileStore(uris)
    app.bot_data["profiles"] = store
    if store.enabled:
        await store.check()

    try:
        app.bot_data["stickers"] = await load_stickers(app)
    except Exception:
        app.bot_data["stickers"] = {}

    port = os.environ.get("PORT")
    if port:
        app.bot_data["health_server"] = await asyncio.start_server(health_handler, "0.0.0.0", int(port))
    app.bot_data["nudge_task"] = asyncio.create_task(nudge_loop(app))


async def post_shutdown(app: Application) -> None:
    task = app.bot_data.get("nudge_task")
    if task:
        task.cancel()
    server = app.bot_data.get("health_server")
    if server:
        server.close()
    store = app.bot_data.get("profiles")
    if store:
        await store.close()
    http = app.bot_data.get("http")
    if http:
        await http.aclose()


def build_app() -> Application:
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is not set.")
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    private = filters.ChatType.PRIVATE
    app.add_handler(CommandHandler("start", on_start, filters=private))
    app.add_handler(CommandHandler("about", on_about, filters=private))
    app.add_handler(CommandHandler("reset", on_reset, filters=private))
    app.add_handler(CallbackQueryHandler(on_gender, pattern=r"^g:(boy|girl)$"))
    app.add_handler(MessageHandler(private & filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(MessageHandler(private & ~filters.TEXT & ~filters.COMMAND, on_other))
    app.add_error_handler(on_error)
    return app


if __name__ == "__main__":
    build_app().run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
