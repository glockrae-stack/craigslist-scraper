import asyncio
import os
import random
import re
import time
import httpx
import feedparser
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder

# ─── CONFIG ───
TOKEN = "8761442506:AAFO9mZHLhxlEFf0yjW0YArbc0lLmOBQg9Y"
CHAT_ID = "6549307194"
DB_FILE = "seen_ids.txt"
MAX_AGE_MINUTES = 60

CITIES = {
    "Chicago": "chicago",
    "Detroit": "detroit",
    "Indianapolis": "indianapolis",
    "Atlanta": "atlanta",
    "Dallas": "dallas",
    "Miami": "miami"
}

# ─── STORAGE ───
def load_seen():
    if os.path.exists(DB_FILE):
        with open(DB_FILE) as f:
            return set(f.read().splitlines())
    return set()

def mark_seen(lid):
    with open(DB_FILE, "a") as f:
        f.write(f"{lid}\n")

seen = load_seen()

# ─── FETCH ───
async def fetch_feed(url: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        try:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                return []
            return feedparser.parse(resp.text).entries
        except:
            return []

# ─── FILTER ───
def is_valid(title):
    title = title.lower()
    keywords = ["couch", "sofa", "sectional", "dresser", "table", "desk", "bed", "frame", "mattress", "nightstand", "chair"]
    return any(k in title for k in keywords) and ("free" in title or "$0" in title)

# ─── SCAN CITY ───
async def check_city(app, city_label, city_slug):
    now = datetime.utcnow()
    url = f"https://{city_slug}.craigslist.org/search/zip?format=rss"

    entries = await fetch_feed(url)
    for entry in entries:
        eid = getattr(entry, "id", entry.link)
        if eid in seen:
            continue
        published = entry.get("published_parsed")
        if published:
            dt = datetime.fromtimestamp(time.mktime(published))
            if (now - dt) > timedelta(minutes=MAX_AGE_MINUTES):
                continue
        title = entry.title
        if not is_valid(title):
            continue
        msg = f"🔥 {title.upper()}\n📍 {city_label}\n💰 FREE"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚡ OPEN LISTING", url=entry.link)]])
        try:
            await app.bot.send_message(chat_id=CHAT_ID, text=msg, reply_markup=kb, disable_web_page_preview=True)
        except:
            pass
        seen.add(eid)
        mark_seen(eid)
        await asyncio.sleep(random.uniform(3, 6))

# ─── LOOP ───
async def scan_loop(app):
    print("🚀 Scanner running...")
    while True:
        city_items = list(CITIES.items())
        random.shuffle(city_items)
        for label, slug in city_items:
            try:
                print(f"Checking {label}...")
                await check_city(app, label, slug)
                await asyncio.sleep(random.uniform(10, 20))
            except Exception as e:
                print(f"City error: {e}")
        wait_time = random.randint(900, 1500)
        print(f"⏳ Waiting {wait_time}s...")
        await asyncio.sleep(wait_time)

# ─── START ───
async def main():
    print("🤖 Starting bot...")
    app = ApplicationBuilder().token(TOKEN).build()
    await app.initialize()
    await app.start()
    asyncio.create_task(scan_loop(app))
    print("✅ Bot running.")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
