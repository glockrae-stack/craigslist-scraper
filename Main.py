import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE"

# ---------------- Handlers ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot is running! Scanning cities...")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"You said: {update.message.text}")

# ---------------- City Scanner ----------------

async def check_city(city: str):
    # Replace this with your real city check logic
    print(f"[inf] Checking {city}...")

async def city_loop():
    while True:
        await check_city("Chicago")
        await check_city("Indianapolis")
        wait_time = 1343  # seconds
        print(f"[inf] ⏳ Waiting {wait_time}s...")
        await asyncio.sleep(wait_time)

# ---------------- Main ----------------

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Start city scanner in background
    asyncio.create_task(city_loop())

    # Run bot polling
    await app.run_polling(poll_interval=2)

# ---------------- Entrypoint ----------------

if __name__ == "__main__":
    # Use the existing loop to avoid "event loop already running"
    loop = asyncio.get_event_loop()
    loop.create_task(main())
    loop.run_forever()
