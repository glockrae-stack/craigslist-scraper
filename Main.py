import asyncio
import feedparser
import aiohttp
import os
from datetime import datetime
from aiohttp import web
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- CONFIG ---
TOKEN = "8761442506:AAFRij1t2Wkm1MWD27Yoys4Gm-q4ZCjpT9M" # Use NEW token if revoked
CHAT_ID = "6549307194"
CITIES = ["phoenix", "miami", "atlanta", "chicago", "houston", "losangeles"]
CATEGORIES = ["cta", "boo", "zip"] 

seen_ids = set()
last_scan_time = "Waiting..."

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"✅ **PULSE OK**\nCache: {len(seen_ids)}\nLast Scan: {last_scan_time}")

async def run_scanner(app: Application):
    global last_scan_time
    while True:
        try:
            # Send the scanning heartbeat
            scan_msg = await app.bot.send_message(CHAT_ID, "🔍 *Scanning markets...*", parse_mode="Markdown")
            
            async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
                for city in CITIES:
                    for cat in CATEGORIES:
                        url = f"https://{city}.craigslist.org/search/{cat}?format=rss"
                        async with session.get(url, timeout=10) as resp:
                            if resp.status == 200:
                                feed = feedparser.parse(await resp.text())
                                for entry in feed.entries:
                                    if entry.id not in seen_ids:
                                        is_initial = len(seen_ids) < 10
                                        seen_ids.add(entry.id)
                                        if not is_initial:
                                            await app.bot.send_message(CHAT_ID, f"🚨 **NEW DEAL**\n📍 {city.upper()}\n📝 {entry.title}\n🔗 {entry.link}")
            
            last_scan_time = datetime.now().strftime('%H:%M:%S')
            await app.bot.delete_message(CHAT_ID, scan_msg.message_id)
        except Exception as e:
            print(f"Scanner Error: {e}")
            
        await asyncio.sleep(300) 

async def handle_health(request):
    return web.Response(text="ALIVE")

async def main():
    # 1. Start Web Server IMMEDIATELY for Railway health check
    server = web.Application()
    server.router.add_get("/", handle_health)
    runner = web.AppRunner(server)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    await web.TCPSite(runner, "0.0.0.0", port).start()

    # 2. Build Bot
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("status", status_command))
    
    async with app:
        await app.initialize()
        await app.start()
        
        # 3. Launch background tasks
        asyncio.create_task(run_scanner(app))
        
        # 4. drop_pending_updates=True is CRITICAL to fix the Conflict error
        await app.updater.start_polling(drop_pending_updates=True)
        
        # Keep alive
        await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
