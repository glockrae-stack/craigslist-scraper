import asyncio
import os
import random
import re
import time
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application
import httpx
import feedparser

# ─── CONFIG ───
# DOUBLE CHECK THIS TOKEN MATCHES BOTFATHER EXACTLY
TOKEN   = "8761442506:AAFRij1t2Wkm1MWD27Yoys4Gm-q4ZCjpT9M"
CHAT_ID = "8761442506"
DB_FILE = "seen_ids.txt"
MAX_AGE_MINUTES = 40

PROXIES = [
    "http://oyexvpgk-us-1:tde8ndie2iu8@p.webshare.io:80",
    "http://oyexvpgk-us-2:tde8ndie2iu8@p.webshare.io:80",
    "http://oyexvpgk-us-3:tde8ndie2iu8@p.webshare.io:80",
    "http://oyexvpgk-us-4:tde8ndie2iu8@p.webshare.io:80",
    "http://oyexvpgk-us-5:tde8ndie2iu8@p.webshare.io:80",
    "http://oyexvpgk-us-6:tde8ndie2iu8@p.webshare.io:80",
    "http://oyexvpgk-us-7:tde8ndie2iu8@p.webshare.io:80",
]

CL_CITIES = {
    "San Francisco": "sfbay", "Los Angeles": "losangeles", "San Diego": "sandiego",
    "Sacramento": "sacramento", "Seattle": "seattle", "Tampa Bay": "tampa",
    "Atlanta": "atlanta", "Chicago": "chicago", "Boston": "boston",
    "Minneapolis": "minneapolis", "Las Vegas": "lasvegas", "Portland": "portland",
    "Austin": "austin", "Dallas": "dallas", "Houston": "houston", "Miami": "miami",
    "Detroit": "detroit", "Phoenix": "phoenix", "Philadelphia": "philadelphia",
    "Baltimore": "baltimore", "St. Louis": "stlouis", "Nashville": "nashville",
    "Salt Lake": "saltlakecity", "Honolulu": "honolulu"
}

CATEGORIES = {"cars": "cta", "boats": "boo", "free": "zip"}

def load_seen():
    if os.path.exists(DB_FILE):
        with open(DB_FILE) as f: return set(f.read().splitlines())
    return set()

def mark_seen(lid):
    with open(DB_FILE, "a") as f: f.write(f"{lid}\n")

seen = load_seen()

async def check_cl_city(app, label, slug, semaphore):
    async with semaphore:
        now = datetime.utcnow()
        for cat_name, cat_code in CATEGORIES.items():
            url = f"https://{slug}.craigslist.org/search/{cat_code}?format=rss"
            try:
                async with httpx.AsyncClient(proxy=random.choice(PROXIES), timeout=20) as client:
                    resp = await client.get(url)
                    feed = feedparser.parse(resp.text)
                    for entry in feed.entries[:8]:
                        eid = getattr(entry, "id", entry.link)
                        if eid in seen: continue
                        
                        pub = entry.get("published_parsed")
                        if pub:
                            dt = datetime.fromtimestamp(time.mktime(pub))
                            if (now - dt) > timedelta(minutes=MAX_AGE_MINUTES): continue

                        cat_label = "🆓 FREE" if cat_name == "free" else "🚤 BOAT" if cat_name == "boats" else "🚗 CAR"
                        msg = f"*{cat_label} | {label}*\n\n📌 {entry.title}"
                        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚡ OPEN PULSE", url=entry.link)]])
                        
                        await app.bot.send_message(CHAT_ID, msg, parse_mode="Markdown", reply_markup=kb)
                        seen.add(eid)
                        mark_seen(eid)
            except: continue
            await asyncio.sleep(random.uniform(2, 4))

async def scan(app):
    semaphore = asyncio.Semaphore(1)
    while True:
        items = list(CL_CITIES.items())
        random.shuffle(items)
        for label, slug in items:
            await check_cl_city(app, label, slug, semaphore)
        
        wait = random.randint(900, 1080)
        print(f"✅ Sweep done. Sleeping {wait//60}m...")
        await asyncio.sleep(wait)

async def main():
    print("⏳ Starting up... Waiting 15s for Railway to settle.")
    await asyncio.sleep(15)
    
    # Initialize application
    app = Application.builder().token(TOKEN).build()
    
    await app.initialize()
    await app.start()
    
    # Start polling and background scan
    print("🚀 Taking control of the token...")
    asyncio.create_task(app.updater.start_polling(drop_pending_updates=True))
    asyncio.create_task(scan(app))
    
    # Keep the script alive
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
