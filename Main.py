import asyncio
import os
import httpx
import feedparser
from datetime import datetime
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ContextTypes

# ─── CONFIG ───
TOKEN = "8601205854:AAF5lME-PScrRA__JxfRP1PRJ0bp00IkSBU"
CHAT_ID = "8761442506"
PORT = int(os.environ.get("PORT", 8080))
# Using your Railway domain
URL = "https://craigslist-scraper-production.up.railway.app" 

# ─── SCANNER LOGIC ───
CL_CITIES = {"SF": "sfbay", "LA": "losangeles", "Chi": "chicago", "Mia": "miami", "Phx": "phoenix"}
CATEGORIES = {"cars": "cta", "boats": "boo"}
seen = set()

async def scan_craigslist(context: ContextTypes.DEFAULT_TYPE):
    print(f"🔍 Scanning Craigslist at {datetime.now().strftime('%H:%M:%S')}...")
    for label, slug in CL_CITIES.items():
        for cat_name, cat_code in CATEGORIES.items():
            rss_url = f"https://{slug}.craigslist.org/search/{cat_code}?format=rss"
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    r = await client.get(rss_url)
                    feed = feedparser.parse(r.text)
                    for entry in feed.entries[:3]:
                        eid = getattr(entry, "id", entry.link)
                        if eid not in seen:
                            kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚡ VIEW DEAL", url=entry.link)]])
                            await context.bot.send_message(
                                CHAT_ID, 
                                f"🚗 *NEW {cat_name.upper()}* ({label})\n{entry.title}", 
                                parse_mode="Markdown", 
                                reply_markup=kb
                            )
                            seen.add(eid)
            except Exception as e:
                print(f"❌ Error scanning {label}: {e}")
                continue
        await asyncio.sleep(1)

# ─── WEBHOOK HANDLER ───
async def handle_webhook(request):
    app = request.app['bot_app']
    try:
        body = await request.json()
        update = Update.de_json(body, app.bot)
        await app.process_update(update)
    except Exception as e:
        print(f"⚠️ Webhook Error: {e}")
    return web.Response(text="OK")

async def main():
    # 1. Setup Application
    app = Application.builder().token(TOKEN).build()
    await app.initialize()
    
    # 2. Schedule the scanner (Runs every 10 minutes)
    # We use the JobQueue so the bot stays active
    app.job_queue.run_repeating(scan_craigslist, interval=600, first=5)
    await app.job_queue.start()

    # 3. Setup Web Server
    server = web.Application()
    server['bot_app'] = app
    server.router.add_post(f"/{TOKEN}", handle_webhook)

    # 4. Set Webhook (This instantly DISCONNECTS the old bot)
    await app.bot.set_webhook(url=f"{URL}/{TOKEN}", drop_pending_updates=True)
    
    print(f"🚀 Webhook active at {URL}")
    
    runner = web.AppRunner(server)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()

    # Confirm start in Telegram
    try:
        await app.bot.send_message(CHAT_ID, "✅ Bot is LIVE using Webhooks. No more conflicts!")
    except: pass

    # Keep alive
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
