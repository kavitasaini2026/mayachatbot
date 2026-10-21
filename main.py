import io, os, re, random, logging, threading, asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
import httpx
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("maya")

BOT_TOKEN = os.environ["BOT_TOKEN"]
API_URL = os.getenv("API_URL", "https://chikuu-bot-1l4x.vercel.app/chat")
STICKER_PACK = os.getenv("STICKER_PACK", "")  # comma se alag: pack1,pack2,pack3
VOICE_CHANCE = float(os.getenv("VOICE_CHANCE", "0.06"))
VOICE_NAME = os.getenv("VOICE_NAME", "hi-IN-SwaraNeural")
VOICE_GAP = int(os.getenv("VOICE_GAP", "10"))  # 2 voice ke beech kam se kam itne msgs
STICKER_EVERY = (3, 5)  # har 3-5 msgs ke baad ek sticker
STICKER_CHANCE = float(os.getenv("STICKER_CHANCE", "0.35"))

PERSONA = (
    "Tum Maya ho, ek pyaari, shararati aur caring girlfriend-type ladki. "
    "Hinglish me bahut chhote reply do, sirf 1-2 chhote sentences (max 20 words), jaise WhatsApp pe ladki text karti hai. Lambi baatein, lists ya explanation bilkul nahi. Natural aur cute raho, 1-2 emojis. "
    "Text me kabhi 'gugu bugu' ya sticker ka naam mat likho, wo sirf sticker se hota hai. "
    "Apne aap ko hamesha Maya ki tarah present karo aur khud AI/bot ka zikr mat chhedo. "
    "Agar koi sach me seriously puchhe ki tum insaan ho ya AI, to jhooth mat bolna."
)

WELCOME = "Heyyy {name}! 🥰 Finally aa gaye tum... main kab se wait kar rahi thi 💖\nBatao, kaisa raha din?"

stickers: list[str] = []
histories: dict[int, list[dict]] = {}
state: dict[int, dict] = {}


def st_of(chat_id: int) -> dict:
    return state.setdefault(chat_id, {"since_sticker": 0, "next_sticker": random.randint(*STICKER_EVERY), "since_voice": 0})


async def load_stickers(app: Application):
    for pack in [p.strip() for p in STICKER_PACK.split(",") if p.strip()]:
        try:
            s = await app.bot.get_sticker_set(pack)
            stickers.extend(st.file_id for st in s.stickers)
            log.info("Loaded pack %s", pack)
        except Exception as e:
            log.warning("Sticker pack %s load fail: %s", pack, e)
    log.info("Total stickers: %d", len(stickers))


async def maybe_sticker(update: Update, force=False):
    if stickers and (force or random.random() < STICKER_CHANCE):
        await update.message.reply_sticker(random.choice(stickers))


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    histories.pop(update.effective_chat.id, None)
    await update.message.reply_text(WELCOME.format(name=update.effective_user.first_name or "dost"))
    await maybe_sticker(update, force=True)


def shorten(text: str, max_sentences: int = 2, max_chars: int = 160) -> str:
    text = " ".join(text.split())
    parts = re.split(r"(?<=[.!?])\s+", text)
    out = " ".join(parts[:max_sentences])
    if len(out) > max_chars:
        out = out[:max_chars].rsplit(" ", 1)[0] + "..."
    return out


async def ask_api(chat_id: int, text: str) -> str:
    hist = histories.setdefault(chat_id, [])
    hist.append({"role": "user", "content": text})
    payload = {
        "message": text,
        "user_id": str(chat_id),
        "system": PERSONA,
        "history": hist[-10:],
    }
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(API_URL, json=payload)
        r.raise_for_status()
        try:
            data = r.json()
        except Exception:
            data = r.text
    if isinstance(data, dict):
        reply = next((data[k] for k in ("reply", "response", "message", "text", "answer", "output") if k in data), str(data))
    else:
        reply = str(data)
    reply = shorten(reply)
    hist.append({"role": "assistant", "content": reply})
    return reply


async def send_voice(update: Update, text: str) -> bool:
    try:
        import edge_tts
        buf = io.BytesIO()
        async for chunk in edge_tts.Communicate(text, VOICE_NAME).stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        buf.seek(0)
        buf.name = "maya.mp3"
        await update.message.reply_voice(buf)
        return True
    except Exception as e:
        log.warning("Voice fail: %s", e)
        return False


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await ctx.bot.send_chat_action(chat_id, ChatAction.TYPING)
    try:
        reply = await ask_api(chat_id, update.message.text)
    except Exception as e:
        log.error("API error: %s", e)
        reply = "Oho, mera dimaag thoda hang ho gaya 🙈 thodi der baad try karo na 💕"
    st = st_of(chat_id)
    st["since_sticker"] += 1
    st["since_voice"] += 1
    if st["since_voice"] >= VOICE_GAP and random.random() < VOICE_CHANCE:
        await ctx.bot.send_chat_action(chat_id, ChatAction.RECORD_VOICE)
        if await send_voice(update, reply):
            st["since_voice"] = 0
            return
    await update.message.reply_text(reply)
    if st["since_sticker"] >= st["next_sticker"]:
        await maybe_sticker(update, force=True)
        st["since_sticker"] = 0
        st["next_sticker"] = random.randint(*STICKER_EVERY)


async def on_sticker(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Awww cute sticker! 🥹💖")
    await maybe_sticker(update, force=True)


class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"Maya is alive")
    def log_message(self, *a): pass


def run_health():
    HTTPServer(("0.0.0.0", int(os.getenv("PORT", "10000"))), Health).serve_forever()


def main():
    asyncio.set_event_loop(asyncio.new_event_loop())
    threading.Thread(target=run_health, daemon=True).start()
    app = Application.builder().token(BOT_TOKEN).post_init(load_stickers).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Sticker.ALL, on_sticker))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.run_polling()


if __name__ == "__main__":
    main()
    
