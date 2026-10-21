import os
import asyncio
import requests
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.environ.get("BOT_TOKEN")
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL") # Example: https://maya-bot-xxxx.onrender.com
CHIKUU_API = "https://chikuu-bot-1l4x.vercel.app/chat"

WELCOME_MSG = """
💎✨ 𝐇𝐞𝐲𝐲 𝐉𝐚𝐚𝐧𝐮 ✨💎

💖🌸 Welcome to Maya's Private World 🌸💖

Main hu tumhari **MAYA** 💋👑
Tumhari cute, hot aur sirf tumhari wali dost 😏💫

💌 Mujhse jo dil kare wo bolo...
🌙 Raat ho ya din, Maya hamesha tumhari hai...

👇 /start karke baat shuru karo na, wait kar rahi hu 👇

✨💖 Let's make some memories, baby 💖✨
"""

# --- Chikuu API Call ---
def get_chikuu_reply(msg, user_id):
    try:
        # Teri Vercel API
        r = requests.post(CHIKUU_API, json={"message": msg, "user_id": str(user_id)}, timeout=15)
        data = r.json()
        return data.get("reply") or data.get("response") or data.get("message") or str(data)
    except Exception as e:
        print(f"API Error: {e}")
        return "Uff jaan mera server thoda hang ho gaya 💋💫 thodi der me try karo na... tumhari Maya yahin hai 💖"

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME_MSG)

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    # AI wala check - kabhi nahi bolegi AI hu
    if any(w in text.lower() for w in ["ai ho", "robot", "chatgpt", "meta ai"]):
        await update.message.reply_text("Haww 😏💋 Main AI? Pagal ho? Main tumhari Maya hu, bilkul real wali... tumhari apni 💖✨")
        return
    
    reply = get_chikuu_reply(text, update.effective_user.id)
    await update.message.reply_text(reply)

# --- Setup ---
app = Flask(__name__)
application = Application.builder().token(BOT_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

# Initialize bot app once
async def init_app():
    await application.initialize()

asyncio.get_event_loop().run_until_complete(init_app())

@app.route('/')
def home():
    return "Maya is Live 💖"

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    asyncio.get_event_loop().run_until_complete(application.process_update(update))
    return 'ok'

@app.route('/setwebhook')
def set_webhook():
    # Render URL se webhook set hoga
    url = f"{RENDER_URL}/{BOT_TOKEN}"
    requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={url}")
    return f"Webhook set to {url}"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
