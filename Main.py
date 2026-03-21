import asyncio
import os
import random
import re
import time
from datetime import datetime, timedelta
import httpx
import feedparser
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application

# ─── CONFIG ───
TOKEN = "8761442506:AAFO9mZHLhxlEFf0yjW0YArbc0lLmOBQg9Y"
CHAT_ID = "8761442506"
DB_FILE = "seen_ids.txt"
MAX_AGE_MINUTES = 40

# WebShare Proxies from your script
PROXIES = [
    "http://oyexvpgk-us-1:tde8ndie2iu8@p.webshare.io:80",
    "http://oyexvpgk-us-2:tde8ndie2iu8@p.webshare.io:80",
    "http://oyexvpgk-us-3:tde8ndie2iu8@p.webshare.io:80",
    "http://oyexvpgk-us-4:tde8ndie2iu8@p.webshare.io:80",
    "http://oyexvpgk-us-5:tde8ndie2iu8@p.webshare.io:80"
]

# ENTER YOUR CITIES HERE (Lower Case)
CITIES = ["fortwayne", "tippecanoe", "bloomington", "muncie", "terrehaute", "kokomo"]

CATEGORIES = {"cars": "cta", "boats": "boo", "free": "zip"}

def load_seen():
    if os.path.exists(DB_FILE):
        with open(DB_FILE) as f: return set(f.read().splitlines())
    return set()

def mark_seen(lid):
    with open(DB_FILE, "a") as f: f.write(f"{lid}\n")

seen = load_seen()

# ─── EXTRACTION LOGIC ───
def get_price(text):
    m = re.search(r'\$[\d,]+', text)
    return m.group(0) if m else ""

async def fetch_feed(url):
    proxy = random.choice(PROXIES)
    async with httpx.AsyncClient(proxy=proxy, timeout=20) as client:
        resp = await client.get(url)
        return feedparser.parse(resp.text).entries

async def check_city(app, city_slug, semaphore):
    async with semaphore:
        now = datetime.utcnow()
        for cat_name, cat_code in CATEGORIES.items():
            url = f"https://{city_slug}.craigslist.org/search/{cat_code}?format=rss"
            try:
                entries = await fetch_feed(url)
                for entry in entries:
                    eid = entry.id
                    if eid in seen: continue
                    
                    # Age Check
                    pub = entry.get("published_parsed")
                    if pub:
                        dt = datetime.fromtimestamp(time.mktime(pub))
                        if (now - dt) > timedelta(minutes=MAX_AGE_MINUTES): continue

                    title = entry.title
                    price = get_price(title)
                    cat_label = "🆓 FREE" if cat_name == "free" else "🚤 BOAT" if cat_name == "boats" else "🚗 CAR"
                    
                    msg = f"*{cat_label} | {city_slug.upper()}*\n{title}\n{price}"
                    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚡ OPEN PULSE", url=entry.link)]])
                    
                    await app.bot.send_message(CHAT_ID, msg, parse_mode="Markdown", reply_markup=kb)
                    seen.add(eid)
                    mark_seen(eid)
            except: continue

async def scan(app):
    semaphore = asyncio.Semaphore(3)
    while True:
        tasks = [check_city(app, city, semaphore) for city in CITIES]
        await asyncio.gather(*tasks)
        await asyncio.sleep(300) # Wait 5 mins between sweeps

async def post_init(app):
    asyncio.create_task(scan(app))

def main():
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
