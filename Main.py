import asyncio
import feedparser
import aiohttp
from datetime import datetime
from aiohttp import web
from telegram import Bot

# --- YOUR PRIVATE CONFIG ---
TOKEN = "8761442506:AAFRij1t2Wkm1MWD27Yoys4Gm-q4ZCjpT9M"
CHAT_ID = "6549307194"

# 12 Major markets for high-volume flips
CITIES = ["newyork", "losangeles", "chicago", "houston", "miami", "atlanta", "phoenix", "seattle", "dallas", "sfbay", "detroit", "denver"]
CATEGORIES = ["cto", "boo"] # cto = Cars by Owner, boo = Boats

bot = Bot(token=TOKEN)
seen_ids = set()

# --- RAILWAY HEARTBEAT SERVER ---
async def handle_health(request):
    return web.Response(text="MONEY_MAGNET_ALIVE")

async def start_health_server():
    app = web.Application()
    app.router.add_get("/", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    # Railway looks for a process on 0.0.0.0:8080
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    print("📡 Heartbeat server active on port 8080")

# --- SCRAPER ENGINE ---
async def scrape_and_notify():
    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
        for city in CITIES:
            for cat in CATEGORIES:
                url = f"https://{city}.craigslist.org/search/{cat}?format=rss"
                try:
                    async with session.get(url, timeout=10) as resp:
                        if resp.status == 200:
                            feed = feedparser.parse(await resp.text())
                            for entry in feed.entries:
                                if entry.id not in seen_ids:
                                    is_new_run = len(seen_ids) == 0
                                    seen_ids.add(entry.id)
                                    
                                    # Don't spam 1000 old listings on the very first run
                                    if not is_new_run:
                                        msg = f"🔔 **NEW LEAD FOUND**\n\n📍 {city.upper()}\n📝 {entry.title}\n🔗 {entry.link}"
                                        await bot.send_message(CHAT_ID, msg, parse_mode="Markdown")
                                        await asyncio.sleep(1) # Prevent Telegram flood kick
                except Exception as e:
                    print(f"⚠️ Error scanning {city}: {e}")

# --- MAIN RUNNER ---
async def main():
    # 1. Start the health server so Railway doesn't kill the container
    await start_health_server()
    
    # 2. Test Connection
    print("🤖 Initializing Bot...")
    try:
        await bot.send_message(CHAT_ID, "🚀 **MONEY MAGNET ONLINE**\nScanning for Cars and Boats...")
    except Exception as e:
        print(f"❌ Connection Error: {e}. Make sure you sent /start to the bot!")

    # 3. Infinite Loop
    while True:
        print(f"🔍 Scanning Craigslist... {datetime.now().strftime('%H:%M:%S')}")
        await scrape_and_notify()
        
        # Keep memory clean
        if len(seen_ids) > 10000:
            seen_ids.clear()
            
        # Wait 5 minutes before next scan
        await asyncio.sleep(300) 

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
