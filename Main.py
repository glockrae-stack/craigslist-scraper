import asyncio
import os
import httpx
import feedparser
import threading
from datetime import datetime
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ContextTypes

# ─── CONFIG ───
TOKEN = "8601205854:AAF5lME-PScrRA__JxfRP1PRJ0bp00IkSBU"
CHAT_ID = "6549307194" 
PORT = int(os.environ.get("PORT", 8080))

# ─── SCANNER LOGIC ───
CL_CITIES = {"SF": "sfbay", "LA": "losangeles", "Chi": "chicago", "Mia": "miami"}
CATEGORIES = {"cars": "cta", "boats": "boo"}
seen = set()

async def check_cl(app):
    print(f"🔍 Scanning... {datetime.now().strftime('%H:%M:%S')}")
    for label, slug in CL_CITIES.items():
        for cat_name, cat_code in CATEGORIES.items():
            url = f"https://{slug}.craigslist.org/search/{cat_code}?format=rss"
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    r = await client.get(url)
                    feed = feedparser.parse(r.text)
                    for entry in feed.entries[:3]:
                        if entry.link not in seen:
                            kb = InlineKeyboardMarkup([[InlineKeyboardButton("View", url=entry.link)]])
                            # Safety: Try/Except so a message error doesn't kill the bot
                            try:
                                await app.bot.send_message(CHAT_ID, f"🔔 {cat_name.upper()} ({label}):\n{entry.title}", reply_markup=kb)
                            except Exception as e:
                                print(f"⚠️ Message failed: {e}")
                            seen.add(entry.link)
            except: continue

# ─── RAILWAY HEALTH CHECK ───
async def health_check(request):
    return web.Response(text="Bot is alive")

async def main():
    # 1. Start the Health Server for Railway
    server = web.Application()
    server.router.add_get("/", health_check)
    runner = web.AppRunner(server)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    print(f"📡 Heartbeat active on port {PORT}")

    # 2. Setup Telegram
    print("🤖 Initializing Bot...")
    app = Application.builder().token(TOKEN).build()
    await app.initialize()
    
    # Force kill old polling sessions
    await app.bot.delete_webhook(drop_pending_updates=True)
    await app.start()
    print("🚀 BOT IS LIVE. No more conflicts.")

    # 3. Main Loop
    while True:
        await check_cl(app)
        await asyncio.sleep(600) # Scan every 10 mins

if __name__ == "__main__":
    asyncio.run(main())
