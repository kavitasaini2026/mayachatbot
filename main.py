import os
import requests
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import asyncio

BOT_TOKEN = os.environ.get("BOT_TOKEN")
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL")
CHIKUU_API_URL = "https://chikuu-bot-1l4x.vercel.app/chat"

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

async def call_chikuu_api(user_message, user_id):
    try:
        # Teri API ka payload - ye common format hai
        payload = {
            "message": user_message,
            "user_id": str(user_id)
        }
        # Kuch API me 'query' ya 'prompt' hota hai, isliye 2 try rakhe hai
        res = requests.post(CHIKUU_API_URL, json=payload, timeout=20)
        
        data = res.json()
        # API ka response kya bhi ho, usko handle kar lega
        reply = data.get("reply") or data.get("response") or data.get("answer") or data.get("message") or str(data)
        return reply

    except Exception as e:
        print(f"API Error: {e}")
        return "Uff jaan 💋 Mera server thoda sharma raha hai abhi 😜 Thodi der me phir se bolo na, tumhari Maya yahin hai 💖✨"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME_MSG, parse_mode="Markdown")

async def maya_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    user_id = update.message.from_user.id
    
    # Typing dikhayega premium feel ke liye
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    # AI wale sawal ka pehle hi block
    ai_words = ["tu ai hai", "ai ho", "robot", "chatgpt", "meta ai", "artificial"]
    if any(w in user_text.lower() for w in ai_words):
        await update.message.reply_text("Haww 😏💋 Main AI? Main tumhari Maya hu jaan, tumhari apni... ekdum real wali 💖 Aise mat bolo, dil dukhta hai mera 🥺✨")
        return

    # Ab teri API se reply lao
    reply_from_api = await call_chikuu_api(user_text, user_id)
    
    # Final reply me Maya ka touch
    await update.message.reply_text(reply_from_api)

# --- RENDER WEB SERVICE SETUP ---
app = Flask(__name__)
application = Application.builder().token(BOT_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, maya_chat))

@app.route('/')
def home():
    return "Maya 💖 is Live with Chikuu API!"

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
async def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    await application.process_update(update)
    return 'ok'

if __name__ == '__main__':
    async def set_webhook():
        if RENDER_URL:
            await application.bot.set_webhook(url=f"{RENDER_URL}/{BOT_TOKEN}")
            print("Webhook Set!")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(set_webhook())
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
