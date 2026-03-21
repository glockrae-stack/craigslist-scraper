import asyncio
import feedparser
import os
import random
import re
from functools import partial
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application

# ─── CONFIG ───
TOKEN   = "8761442506:AAGs-ec3RXZ_9O86DIxMCSlEjiN9r0ytLk4"
CHAT_ID = "6549307194"
DB_FILE = "seen_ids.txt"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

CATEGORIES = {
    "cars":  "cto",
    "boats": "boo",
    "free":  "zip",
}

CITIES = {
    "Phoenix":          "phoenix",
    "Los Angeles":      "losangeles",
    "San Diego":        "sandiego",
    "SF Bay":           "sfbay",
    "Colorado Springs": "cosprings",
    "Washington DC":    "washingtondc",
    "Atlanta":          "atlanta",
    "Chicago":          "chicago",
    "New Orleans":      "neworleans",
    "Boston":           "boston",
    "Detroit":          "detroit",
    "Minneapolis":      "minneapolis",
    "Las Vegas":        "lasvegas",
    "Albuquerque":      "albuquerque",
    "New York":         "newyork",
    "Portland":         "portland",
    "Dallas":           "dallas",
    "Austin":           "austin",
    "Miami":            "miami",
    "Seattle":          "seattle",
}

# ─── SEEN IDs ───
def load_seen():
    if os.path.exists(DB_FILE):
        with open(DB_FILE) as f:
            return set(f.read().splitlines())
    return set()

def mark_seen(lid):
    with open(DB_FILE, "a") as f:
        f.write(f"{lid}\n")

seen = load_seen()

# ─── HELPERS ───
def get_price(text):
    m = re.search(r'\(\s*(\$[\d,]+)\s*\)', text) or re.search(r'\$[\d,]+', text)
    return m.group(0) if m else ""

def get_mileage(text):
    m = re.search(r'odometer[:\s]+([0-9,]+)|([0-9,]+)\s*(?:miles|mi\b)', text, re.I)
    if m:
        raw = (m.group(1) or m.group(2)).replace(",", "")
        try: return f"{int(raw):,} mi"
        except: pass
    return ""

def fetch_feed(url):
    return feedparser.parse(url, request_headers=HEADERS)

# ─── SEND ALERT ───
async def send(app, title, link, city, price="", mileage=""):
    parts = []
    if price:   parts.append(f"💰 {price}")
    if mileage: parts.append(f"🛣️ {mileage}")
    parts.append(f"🏙️ {city}")

    msg = f"*{title.upper()}*\n{' • '.join(parts)}"
    kb  = InlineKeyboardMarkup([[InlineKeyboardButton("⚡ OPEN PULSE", url=link)]])
    await app.bot.send_message(CHAT_ID, msg, parse_mode="Markdown", reply_markup=kb, disable_web_page_preview=True)
    print(f"✅ [{city}] {title[:60]}")

# ─── SCAN LOOP ───
async def scan(app):
    loop = asyncio.get_event_loop()
    print("🤖 Bot scanning...")

    while True:
        for city_label, city_slug in CITIES.items():
            for cat_name, cat_code in CATEGORIES.items():
                url = f"https://{city_slug}.craigslist.org/search/{cat_code}?format=rss"
                try:
                    feed = await loop.run_in_executor(None, partial(fetch_feed, url))
                    print(f"CL [{city_label} | {cat_name}] → {len(feed.entries)} entries")

                    for entry in feed.entries:
                        eid = getattr(entry, "id", entry.link)
                        if eid in seen:
                            continue

                        title = entry.title.strip()

                        # Free section: only alert if 'free' in title
                        if cat_name == "free" and "free" not in title.lower():
                            seen.add(eid)
                            mark_seen(eid)
                            continue

                        price   = get_price(title)
                        desc    = getattr(entry, "summary", "") or ""
                        mileage = get_mileage(desc) if cat_name == "cars" else ""

                        await send(app, title, entry.link, city_label, price, mileage)
                        seen.add(eid)
                        mark_seen(eid)

                except Exception as e:
                    print(f"ERROR [{city_label} | {cat_name}]: {e}")

                await asyncio.sleep(random.uniform(3, 6))

        print("🔄 Cycle done. Sleeping 90s...")
        await asyncio.sleep(90)

# ─── START ───
async def post_init(app):
    asyncio.create_task(scan(app))

def main():
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
