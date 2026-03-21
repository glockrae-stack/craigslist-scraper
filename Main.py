from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from flask import Flask, request

# ---------------- CONFIG ----------------
BOT_TOKEN = "8761442506:AAFO9mZHLhxlEFf0yjW0YArbc0lLmOBQg9Y"
WEBHOOK_PATH = f"/{BOT_TOKEN}"      # path Telegram will POST to
PORT = 8000                         # Railway will expose this port
# ---------------------------------------

# Initialize Flask app
app = Flask(__name__)

# Bot application
application = ApplicationBuilder().token(BOT_TOKEN).build()
bot = application.bot

# --------- COMMAND HANDLERS ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot is online ✅")

application.add_handler(CommandHandler("start", start))

# --------- FLASK WEBHOOK ROUTE --------
@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    application.update_queue.put(update)  # push update to PTB application
    return "ok"

# --------- SET WEBHOOK ON TELEGRAM ----
async def set_webhook():
    url = f"https://YOUR_RAILWAY_APP_URL{WEBHOOK_PATH}"  # replace with Railway app URL
    await bot.set_webhook(url)
    print(f"Webhook set to {url}")

# --------- RUN BOT -------------------
if __name__ == "__main__":
    import asyncio
    asyncio.run(set_webhook())
    app.run(host="0.0.0.0", port=PORT)
