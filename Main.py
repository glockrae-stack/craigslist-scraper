# Main.py
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
import logging
import asyncio

# ---- CONFIG ----
BOT_TOKEN = "8761442506:AAFO9mZHLhxlEFf0yjW0YArbc0lLmOBQg9Y"

# ---- LOGGING ----
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ---- HANDLERS ----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot is running! ✅")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"You said: {update.message.text}")

# ---- MAIN ----
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Start polling
    await app.run_polling(poll_interval=2, allowed_updates=None)

if __name__ == "__main__":
    asyncio.run(main())
