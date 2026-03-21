import asyncio
import feedparser
import os
import random
import re
import time
from datetime import datetime, timedelta
from functools import partial
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application

# ─── CONFIG ───
TOKEN   = "8761442506:AAGs-ec3RXZ_9O86DIxMCSlEjiN9r0ytLk4"
CHAT_ID = "6549307194"
DB_FILE = "seen_ids.txt"
CONCURRENT_TASKS = 3  # Speed: Checks 3 cities at a time
MAX_AGE_MINUTES  = 40 # Precision: Only alerts for items < 40 mins old

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
]

CATEGORIES = {"cars": "cto", "boats": "boo", "free": "zip"}

# Mapped directly from your OfferUp Zip Code PDF
CITIES = {
    "San Francisco": "sfbay",
    "Los Angeles":   "losangeles",
    "San Diego":     "sandiego",
    "Sacramento":    "sacramento",
    "Seattle":       "seattle",
    "Tampa Bay":     "tampa",
    "Atlanta":       "atlanta",
    "Chicago":       "chicago",
    "Boston":        "boston",
    "Minneapolis":   "minneapolis",
    "Las Vegas":     "lasvegas",
    "Portland":      "portland",
    "Austin":        "austin",
    "Dallas":        "dallas",
    "Houston":       "houston",
    "Miami":         "miami",
    "Detroit":       "detroit",
    "Phoenix":       "phoenix",
    "Philadelphia":  "philadelphia",
    "Baltimore":     "baltimore",
    "St. Louis":     "stlouis",
    "Nashville":     "nashville",
    "Salt Lake":     "saltlakecity",
    "Honolulu":      "honolulu"
}

# ─── DATABASE ───
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
    headers = {"User-Agent": random.choice(USER_AGENTS), "Referer": "https://www.google.com/"}
    return feedparser.parse(url, request_headers=headers)

async def send(app, title, link, city, price="", mileage=""):
    parts = []
    if price:   parts.append(f"💰 {price}")
    if mileage: parts.append(f"🛣️ {mileage}")
    parts.append(f"🏙️ {city}")

    msg = f"*{title.upper()}*\n{' • '.join(parts)}"
    kb  = InlineKeyboardMarkup([[InlineKeyboardButton("⚡ OPEN PULSE", url=link)]])
    try:
        await app.bot.send_message(CHAT_ID, msg, parse_mode="Markdown", reply_markup=kb, disable_web_page_preview=True)
    except Exception: pass

# ─── WORKER ───
async def check_city(app, city_label, city_slug, semaphore):
    async with semaphore:
        loop = asyncio.get_event_loop()
        now = datetime.utcnow()
        
        for cat_name, cat_code in CATEGORIES.items():
            url = f"https://{city_slug}.craigslist.org/search/{cat_code}?format=rss"
            try:
                feed = await loop.run_in_executor(None, partial(fetch_feed, url))
                
                for entry in feed.entries:
                    eid = getattr(entry, "id", entry.link)
                    if eid in seen: continue

                    # 40-MINUTE TIMESTAMP FILTER
                    published = entry.get('published_parsed')
                    if published:
                        dt_published = datetime.fromtimestamp(time.mktime(published))
                        if (now - dt_published) > timedelta(minutes=MAX_AGE_MINUTES):
                            continue

                    title = entry.title.strip()
                    if cat_name == "free" and "free" not in title.lower():
                        seen.add(eid); mark_seen(eid); continue

                    price = get_price(title)
                    desc = getattr(entry, "summary", "") or ""
                    mileage = get_mileage(desc) if cat_name == "cars" else ""

                    await send(app, title, entry.link, city_label, price, mileage)
                    seen.add(eid); mark_seen(eid)
                    
            except Exception: pass
            await asyncio.sleep(random.uniform(1, 3))

# ─── MAIN LOOP ───
async def scan(app):
    semaphore = asyncio.Semaphore(CONCURRENT_TASKS)
    print(f"🚀 Scanning {len(CITIES)} cities (from OfferUp list) for items < {MAX_AGE_MINUTES}m.")

    while True:
        city_items = list(CITIES.items())
        random.shuffle(city_items) # Randomize order each time
        
        tasks = [check_city(app, label, slug, semaphore) for label, slug in city_items]
        await asyncio.gather(*tasks)

        # 15-18 min wait between sweeps
        wait = random.randint(900, 1080) 
        print(f"✅ Sweep complete. Next in {wait // 60}m.")
        await asyncio.sleep(wait)

async def post_init(app):
    asyncio.create_task(scan(app))

def main():
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
