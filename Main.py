import asyncio
import os
import random
import re
import time
import httpx
import feedparser
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application

# ─── CONFIG ───
TOKEN = "8761442506:AAFO9mZHLhxlEFf0yjW0YArbc0lLmOBQg9Y" 
CHAT_ID = "6549307194"
DB_FILE = "seen_ids.txt"
MAX_AGE_MINUTES = 40 

PROXIES = [f"http://oyexvpgk-us-{i}:tde8ndie2iu8@p.webshare.io:80" for i in range(1, 8)]
USER_AGENTS = ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"]

CITIES = {
    "San Francisco": "sfbay", "Los Angeles": "losangeles", "San Diego": "sandiego",
    "Sacramento": "sacramento", "Seattle": "seattle", "Tampa Bay": "tampa",
    "Atlanta": "atlanta", "Chicago": "chicago", "Boston": "boston",
    "Minneapolis": "minneapolis", "Las Vegas": "lasvegas", "Portland": "portland",
    "Austin": "austin", "Dallas": "dallas", "Houston": "houston", "Miami": "miami",
    "Detroit": "detroit", "Phoenix": "phoenix", "Philadelphia": "philadelphia",
    "Baltimore": "baltimore", "St. Louis": "stlouis", "Nashville": "nashville",
    "Salt Lake": "saltlakecity", "Honolulu": "honolulu"
}

def load_seen():
    if os.path.exists(DB_FILE):
        with open(DB_FILE) as f: return set(f.read().splitlines())
    return set()

def mark_seen(lid):
    with open(DB_FILE, "a") as f: f.write(f"{lid}\n")

seen = load_seen()

async def force_clear_session():
    """Manually tell Telegram to drop all existing connections for this token."""
    print("🔄 Attempting to force-clear existing sessions...")
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset=-1"
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await client.get(url)
            await asyncio.sleep(2)  # Give Telegram time to process the drop
            print("✅ Session cleared.")
        except Exception as e:
            print(f"⚠️ Manual clear failed: {e}")

async def fetch_feed(url: str):
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    selected_proxy = random.choice(PROXIES)
    async with httpx.AsyncClient(proxy=selected_proxy, timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        return feedparser.parse(resp.text).entries if resp.status_code == 200 else []

async def check_city(app, city_label, city_slug, semaphore):
    async with semaphore:
        now = datetime.utcnow()
        for cat_code in ["cto", "boo", "zip"]:
            url = f"https://{city_slug}.craigslist.org/search/{cat_code}?format=rss"
            try:
                entries = await fetch_feed(url)
                for entry in entries:
                    eid = getattr(entry, "id", entry.link)
                    if eid in seen: continue
                    published = entry.get("published_parsed")
                    if published:
                        dt = datetime.fromtimestamp(time.mktime(published))
                        if (now - dt) > timedelta(minutes=MAX_AGE_MINUTES): continue
                    
                    price = (re.search(r'\$[\d,]+', entry.title) or re.search(r'\$[\d,]+', entry.summary or ""))
                    price_str = price.group(0) if price else "N/A"
                    
                    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚡ OPEN PULSE", url=entry.link)]])
                    await app.bot.send_message(CHAT_ID, f"*{entry.title.upper()}*\n💰 {price_str} • 🏙️ {city_label}", parse_mode="Markdown", reply_markup=kb, disable_web_page_preview=True)
                    seen.add(eid); mark_seen(eid)
            except Exception: pass
            await asyncio.sleep(random.uniform(2, 4))

async def scan_loop(app):
    semaphore = asyncio.Semaphore(1) 
    print("🚀 Stealth Scan Live...")
    while True:
        city_items = list(CITIES.items())
        random.shuffle(city_items)
        for label, slug in city_items:
            await check_city(app, label, slug, semaphore)
        await asyncio.sleep(random.randint(300, 600))

async def post_init(app):
    asyncio.create_task(scan_loop(app))

async def run_bot():
    # 1. Force clear the session before building the app
    await force_clear_session()
    
    # 2. Build and start
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    await app.initialize()
    await app.start()
    print("🤖 Bot Authorized. Monitoring...")
    await app.updater.start_polling(drop_pending_updates=True)
    
    # Keep the loop running
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"FATAL: {e}")
