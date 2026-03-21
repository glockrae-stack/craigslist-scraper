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

# WebShare Proxies
PROXIES = [f"http://oyexvpgk-us-{i}:tde8ndie2iu8@p.webshare.io:80" for i in range(1, 8)]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
]

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

async def fetch_feed(url: str):
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    # FIX: Changed 'proxies' to 'proxy' for compatibility
    selected_proxy = random.choice(PROXIES)
    
    async with httpx.AsyncClient(proxy=selected_proxy, timeout=30.0, follow_redirects=True) as client:
        await asyncio.sleep(random.uniform(1, 2))
        resp = await client.get(url, headers=headers)
        if resp.status_code == 200:
            return feedparser.parse(resp.text).entries
        return []

async def send_alert(app, title, link, city, price=""):
    msg = f"*{title.upper()}*\n💰 {price} • 🏙️ {city}"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚡ OPEN PULSE", url=link)]])
    try:
        await app.bot.send_message(CHAT_ID, msg, parse_mode="Markdown", reply_markup=kb, disable_web_page_preview=True)
    except Exception: pass

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
                        if (now - dt) > timedelta(minutes=MAX_AGE_MINUTES):
                            continue

                    title = entry.title.strip()
                    price_match = re.search(r'\$[\d,]+', title)
                    price = price_match.group(0) if price_match else "N/A"

                    await send_alert(app, title, entry.link, city_label, price)
                    seen.add(eid); mark_seen(eid)
            except Exception: pass
            await asyncio.sleep(random.uniform(3, 7))

async def scan_loop(app):
    semaphore = asyncio.Semaphore(1) 
    print("🚀 FIXED: Stealth Scan Live...")
    while True:
        city_items = list(CITIES.items())
        random.shuffle(city_items)
        for label, slug in city_items:
            await check_city(app, label, slug, semaphore)
        await asyncio.sleep(random.randint(600, 900))

async def post_init(app):
    asyncio.create_task(scan_loop(app))

def main():
    try:
        app = Application.builder().token(TOKEN).post_init(post_init).build()
        # drop_pending_updates=True clears the 'Conflict' error instantly
        app.run_polling(drop_pending_updates=True)
    except Exception as e:
        print(f"FATAL: {e}")

if __name__ == "__main__":
    main()
