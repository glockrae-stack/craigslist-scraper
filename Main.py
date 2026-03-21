import asyncio
import feedparser
import aiohttp
import os
from datetime import datetime
from aiohttp import web
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- CONFIG ---
TOKEN = "8761442506:AAFRij1t2Wkm1MWD27Yoys4Gm-q4ZCjpT9M"
CHAT_ID = "6549307194"
CITIES = ["phoenix", "miami", "atlanta", "chicago", "houston", "losangeles"]
CATEGORIES = ["cta", "boo", "zip"] 

seen_ids = set()
last_scan_time = "Waiting..."

# --- 1. THE STATUS COMMAND ---
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = (
        f"📊 **SYSTEM PULSE**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🌐 **Index:** {len(seen_ids)} cached\n"
        f"🕒 **Last Scan:** {last_scan_time}\n"
        f"✅ **Status:** Active"
    )
    await update.message.reply_text(status_msg, parse_mode="Markdown")

# --- 2. THE AUTO-CLEAN SCANNER ---
async def run_scanner(app: Application):
    global last_scan_time
    while True:
        # Send scanning heartbeat
        scan_msg = await app.bot.send_message(CHAT_ID, "🔍 *Scanning Craigslist...*", parse_mode="Markdown")
        
        async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
            for city in CITIES:
                for cat in CATEGORIES:
                    url = f"https://{city}.craigslist.org/search/{cat}?format=rss"
                    try:
                        async with session.get(url, timeout=15) as resp:
                            if resp.status == 200:
                                feed = feedparser.parse(await resp.text())
                                for entry in feed.entries:
                                    if entry.id not in seen_ids:
                                        # Initial load: Build index first 10 items
                                        is_initial = len(seen_ids) < 10
                                        seen_ids.add(entry.id)
                                        
                                        if not is_initial:
                                            msg = f"🚨 **NEW DEAL**\n\n📍 {city.upper()}\n📝 {entry.title}\n🔗 {entry.link}"
                                            await app.bot.send_message(CHAT_ID, msg, parse_mode="Markdown")
                    except Exception as e:
                        print(f"⚠️ CL Error ({city}): {e}")
        
        last_scan_time = datetime.now().strftime('%H:%M:%S')
        
        # Cleanup scanning message
        try:
            await app.bot.delete_message(CHAT_ID, scan_msg.message_id)
        except:
            pass
            
        await asyncio.sleep(300) 

# --- 3. THE RAILWAY FIX: WEB APP HANDLER ---
async def handle_health(request):
    return web.Response(text="ALIVE")

async def main():
    # 1. Setup Telegram Application
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("ping", status_command))
    
    # 2. Setup Web Server (The Heartbeat)
    server = web.Application()
    server.router.add_get("/", handle_health)
    runner = web.AppRunner(server)
    await runner.setup()
    
    # Railway looks for PORT environment variable or 8080
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"📡 Heartbeat server active on port {port}")

    # 3. Start Bot and Scanner
    async with app:
        await app.initialize()
        await app.start()
        await app.bot.send_message(CHAT_ID, "🚀 **BOT REBOOTED: CLEAN MODE ACTIVE**")
        
        # Run the scanner as a background task
        asyncio.create_task(run_scanner(app))
        
        # Keep polling for /status commands
        await app.updater.start_polling()
        
        # Keep the process alive forever
        await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
