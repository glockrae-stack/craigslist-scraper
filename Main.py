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
TOKEN = "8761442506:AAF6cJWgclG50qdWZfumtBsih8ZpZ_4unC0"
CHAT_ID = "6549307194"
DB_FILE = "seen_ids.txt"
MAX_AGE_MINUTES = 40 

# WebShare Proxies - Rotating format
PROXIES = [f"http://oyexvpgk-us-{i}:tde8ndie2iu8@p.webshare.io:80" for i in range(1, 8)]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
]

CATEGORIES = {"cars": "cto", "boats": "boo", "free": "zip"}

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

# ─── SEEN IDs ───
def load_seen():
    if os.path.exists(DB_FILE):
        with open(DB_FILE) as f: return set(f.read().splitlines())
    return set()

def mark_seen(lid):
    with open(DB_FILE, "a") as f: f.write(f"{lid}\n")

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

async def fetch_feed(url: str):
    headers = {"User-Agent": random.choice(USER_AGENTS), "Referer": "https://www.google.com/"}
    proxy = {"all://": random.choice(PROXIES)} # Correct httpx proxy format
    
    async with httpx.AsyncClient(proxies=proxy, timeout=20.0, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code == 200:
            return feedparser.parse(resp.text).entries
    return []

async def send_alert(app, title, link, city, price="", mileage=""):
    parts = [f"🏙️ {city}"]
    if price: parts.insert(0, f"💰 {price}")
    if mileage: parts.insert(1, f"🛣️ {mileage}")

    msg = f"*{title.upper()}*\n{' • '.join(parts)}"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚡ OPEN PULSE", url=link)]])
    
    try:
        await app.bot.send_message(CHAT_ID, msg, parse_mode="Markdown", reply_markup=kb, disable_web_page_preview=True)
        print(f"✅ [SENT] {city}: {title[:40]}")
    except Exception as e:
        print(f"❌ SEND ERROR: {e}")

# ─── SCANNER ───
async def check_city(app, city_label, city_slug, semaphore):
    async with semaphore:
        now = datetime.utcnow()
        for cat_name, cat_code in CATEGORIES.items():
            url = f"https://{city_slug}.craigslist.org/search/{cat_code}?format=rss"
            try:
                entries = await fetch_feed(url)
                for entry in entries:
                    eid = getattr(entry, "id", entry.link)
                    if eid in seen: continue

                    # 40-minute freshness check
                    published = entry.get("published_parsed")
                    if published:
                        dt = datetime.fromtimestamp(time.mktime(published))
                        if (now - dt) > timedelta(minutes=MAX_AGE_MINUTES):
                            continue

                    title = entry.title.strip()
                    if cat_name == "free" and "free" not in title.lower():
                        seen.add(eid); mark_seen(eid); continue

                    price = get_price(title)
                    desc = getattr(entry, "summary", "") or ""
                    mileage = get_mileage(desc) if cat_name == "cars" else ""

                    await send_alert(app, title, entry.link, city_label, price, mileage)
                    seen.add(eid); mark_seen(eid)
            except Exception as e:
                print(f"⚠️ ERROR [{city_label}]: {e}")
            
            await asyncio.sleep(random.uniform(2, 4)) # Small break between categories

async def scan_loop(app):
    semaphore = asyncio.Semaphore(3) # Check 3 cities at a time
    print(f"🚀 Bot Active. Target: Listings < {MAX_AGE_MINUTES}m old.")

    while True:
        city_items = list(CITIES.items())
        random.shuffle(city_items)
        
        tasks = [check_city(app, label, slug, semaphore) for label, slug in city_items]
        await asyncio.gather(*tasks)

        wait_time = random.randint(900, 1080) # 15-18 min cycle
        print(f"💤 Sweep done. Sleeping {wait_time // 60}m...")
        await asyncio.sleep(wait_time)

async def post_init(app):
    asyncio.create_task(scan_loop(app))

def main():
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
