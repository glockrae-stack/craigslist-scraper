import asyncio
import feedparser
import aiohttp
from datetime import datetime
from aiohttp import web
from telegram import Bot

# --- CONFIGURATION ---
TOKEN = "YOUR_BOT_TOKEN_HERE"
CHAT_ID = "YOUR_CHAT_ID_HERE"
# 17 High-velocity cities for Cars (cto), Boats (boo), and Free (zip)
CITIES = ["newyork", "losangeles", "chicago", "houston", "miami", "atlanta", "phoenix", "seattle", "dallas", "sfbay", "detroit", "denver", "boston", "tampa", "austin", "lasvegas", "philadelphia"]
CATEGORIES = ["cto", "boo", "zip"]
SCAN_INTERVAL = 600  # 10 minutes

bot = Bot(token=TOKEN)
seen_ids = set()

# --- RAILWAY HEALTH CHECK SERVER ---
async def handle_health(request):
    return web.Response(text="ALIVE")

async def setup_health_server():
    app = web.Application()
    app.router.add_get("/", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    print("📡 Heartbeat active on port 8080")

# --- SCRAPER LOGIC ---
async def fetch_city_feed(city, cat, session):
    url = f"https://{city}.craigslist.org/search/{cat}?format=rss"
    try:
        async with session.get(url, timeout=15) as response:
            if response.status == 200:
                content = await response.text()
                return feedparser.parse(content)
    except Exception as e:
        print(f"⚠️ Error fetching {city}/{cat}: {e}")
    return None

async def scrape_and_notify():
    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
        tasks = []
        for city in CITIES:
            for cat in CATEGORIES:
                tasks.append(fetch_city_feed(city, cat, session))
        
        results = await asyncio.gather(*tasks)
        
        for feed in results:
            if not feed or not feed.entries:
                continue
                
            for entry in feed.entries:
                item_id = entry.id
                if item_id not in seen_ids:
                    seen_ids.add(item_id)
                    
                    # Basic "Money Magnet" Logic
                    title = entry.title.lower()
                    link = entry.link
                    
                    # Filtering for "Free" in zip or distress keywords in cars/boats
                    if "zip" in link and "free" not in title:
                        continue
                        
                    msg = (
                        f"🧲 **NEW PULSE FOUND**\n"
                        f"━━━━━━━━━━━━━━\n"
                        f"📝 {entry.title}\n"
                        f"🔗 [OPEN LISTING]({link})"
                    )
                    
                    try:
                        await bot.send_message(CHAT_ID, msg, parse_mode="Markdown")
                        await asyncio.sleep(1) # Prevent Telegram rate limiting
                    except Exception as e:
                        print(f"❌ Telegram Send Error: {e}")

# --- MAIN ENGINE ---
async def main():
    await setup_health_server()
    print("🤖 Initializing Bot...")
    
    # Send startup confirmation
    try:
        await bot.send_message(CHAT_ID, "🚀 **MONEY MAGNET IS LIVE**\nScanning 17 cities for Cars & Boats.")
    except:
        print("⚠️ Initial message failed. Ensure you have started the bot in Telegram!")

    while True:
        print(f"🔍 Scanning... {datetime.now().strftime('%H:%M:%S')}")
        await scrape_and_notify()
        
        # Keep seen_ids from bloating memory
        if len(seen_ids) > 5000:
            seen_ids.clear()
            
        await asyncio.sleep(SCAN_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
