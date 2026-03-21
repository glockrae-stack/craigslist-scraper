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
TOKEN   = "8761442506:AAF6cJWgclG50qdWZfumtBsih8ZpZ_4unC0"
CHAT_ID = "6549307194"
DB_FILE = "seen_ids.txt"
MAX_AGE_MINUTES = 40

# WebShare rotating residential proxy — confirmed format from WebShare docs
PROXY = "http://oyexvpgk-US-rotate:tde8ndie2iu8@p.webshare.io:80"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
]

CATEGORIES = {"cars": "cto", "boats": "boo", "free": "zip"}

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
    "Honolulu":      "honolulu",
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

# ─── FETCH via httpx + proxy ───
async def fetch_feed(url: str) -> list:
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/",
    }
    async with httpx.AsyncClient(proxy=PROXY, timeout=20) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
        return feed.entries

# ─── SEND ALERT ───
async def send(app, title, link, city, price="", mileage=""):
    parts = []
    if price:   parts.append(f"💰 {price}")
    if mileage: parts.append(f"🛣️ {mileage}")
    parts.append(f"🏙️ {city}")

    msg = f"*{title.upper()}*\n{' • '.join(parts)}"
    kb  = InlineKeyboardMarkup([[InlineKeyboardButton("⚡ OPEN PULSE", url=link)]])
    try:
        await app.bot.send_message(
            CHAT_ID, msg,
            parse_mode="Markdown",
            reply_markup=kb,
            disable_web_page_preview=True
        )
        print(f"✅ [{city}] {title[:60]}")
    except Exception as e:
        print(f"SEND ERROR: {e}")

# ─── WORKER ───
async def check_city(app, city_label, city_slug, semaphore):
    async with semaphore:
        now = datetime.utcnow()

        for cat_name, cat_code in CATEGORIES.items():
            url = f"https://{city_slug}.craigslist.org/search/{cat_code}?format=rss"
            try:
                entries = await fetch_feed(url)
                print(f"CL [{city_label} | {cat_name}] → {len(entries)} entries")

                for entry in entries:
                    eid = getattr(entry, "id", entry.link)
                    if eid in seen:
                        continue

                    # 40 min age filter
                    published = entry.get("published_parsed")
                    if published:
                        dt = datetime.fromtimestamp(time.mktime(published))
                        if (now - dt) > timedelta(minutes=MAX_AGE_MINUTES):
                            continue

                    title = entry.title.strip()
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

            await asyncio.sleep(random.uniform(2, 5))

# ─── MAIN LOOP ───
async def scan(app):
    semaphore = asyncio.Semaphore(3)
    print(f"🚀 Bot live — {len(CITIES)} cities, proxy ON")

    while True:
        city_items = list(CITIES.items())
        random.shuffle(city_items)
        tasks = [check_city(app, label, slug, semaphore) for label, slug in city_items]
        await asyncio.gather(*tasks)
        wait = random.randint(900, 1080)
        print(f"✅ Sweep done. Next in {wait // 60}m.")
        await asyncio.sleep(wait)

async def post_init(app):
    asyncio.create_task(scan(app))

def main():
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
