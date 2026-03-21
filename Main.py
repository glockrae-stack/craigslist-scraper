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
TOKEN   = "8761442506:AAFO9mZHLhxlEFf0yjW0YArbc0lLmOBQg9Y"
CHAT_ID = "8761442506"
DB_FILE = "seen_ids.txt"
MAX_AGE_MINUTES = 40

# WebShare rotating residential proxies
PROXIES = [
    "http://oyexvpgk-us-1:tde8ndie2iu8@p.webshare.io:80",
    "http://oyexvpgk-us-2:tde8ndie2iu8@p.webshare.io:80",
    "http://oyexvpgk-us-3:tde8ndie2iu8@p.webshare.io:80",
    "http://oyexvpgk-us-4:tde8ndie2iu8@p.webshare.io:80",
    "http://oyexvpgk-us-5:tde8ndie2iu8@p.webshare.io:80",
    "http://oyexvpgk-us-6:tde8ndie2iu8@p.webshare.io:80",
    "http://oyexvpgk-us-7:tde8ndie2iu8@p.webshare.io:80",
]

# CRAIGSLIST TARGETS
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

# OFFERUP TARGETS (ZIPs)
OU_ZIPS = [
    "94102", "90001", "91911", "94203", "80014", "98198", "33593", "30033",
    "60007", "02108", "55111", "88901", "44101", "97229", "73301", "75001",
    "77001", "98039", "33101", "21201", "35242", "63101", "48127", "85001",
    "96731", "84044", "37011", "19019"
]

CATEGORIES = {"cars": "cta", "boats": "boo", "free": "zip"}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
]

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

def get_proxy():
    return random.choice(PROXIES)

# ─── WORKER ───
async def check_cl_city(app, label, slug, semaphore):
    async with semaphore:
        now = datetime.utcnow()
        for cat_name, cat_code in CATEGORIES.items():
            url = f"https://{slug}.craigslist.org/search/{cat_code}?format=rss"
            try:
                headers = {"User-Agent": random.choice(USER_AGENTS)}
                # Use a fresh client for every city to save RAM
                async with httpx.AsyncClient(proxy=get_proxy(), timeout=20) as client:
                    resp = await client.get(url, headers=headers)
                    feed = feedparser.parse(resp.text)
                    
                    for entry in feed.entries[:8]:
                        eid = getattr(entry, "id", entry.link)
                        if eid in seen: continue
                        
                        pub = entry.get("published_parsed")
                        if pub:
                            dt = datetime.fromtimestamp(time.mktime(pub))
                            if (now - dt) > timedelta(minutes=MAX_AGE_MINUTES): continue

                        if cat_name == "free" and "free" not in entry.title.lower():
                            seen.add(eid)
                            mark_seen(eid)
                            continue

                        price = get_price(entry.title)
                        desc = getattr(entry, "summary", "") or ""
                        mileage = get_mileage(desc) if cat_name == "cars" else ""
                        
                        cat_label = "🆓 FREE" if cat_name == "free" else "🚤 BOAT" if cat_name == "boats" else "🚗 CAR"
                        msg = f"*{cat_label} | CL {label.upper()}*\n\n📌 {entry.title}\n"
                        if price: msg += f"💰 {price}\n"
                        if mileage: msg += f"🛣️ {mileage}\n"
                        
                        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚡ OPEN PULSE", url=entry.link)]])
                        await app.bot.send_message(CHAT_ID, msg, parse_mode="Markdown", reply_markup=kb)
                        seen.add(eid)
                        mark_seen(eid)
            except: continue
            await asyncio.sleep(random.uniform(2, 4))

# ─── MAIN LOOP ───
async def scan(app):
    # LEAN MODE: Semaphore 1 prevents Exit Code 137 (Out of Memory)
    semaphore = asyncio.Semaphore(1)
    print(f"🚀 Dual-Scout Live: {len(CL_CITIES)} CL Cities | {len(OU_ZIPS)} OU Zips")
    
    while True:
        cl_items = list(CL_CITIES.items())
        random.shuffle(cl_items)
        # Check cities one by one to keep RAM usage extremely low
        for label, slug in cl_items:
            await check_cl_city(app, label, slug, semaphore)
        
        wait = random.randint(900, 1080)
        print(f"✅ Sweep complete. Pausing {wait // 60}m.")
        await asyncio.sleep(wait)

async def post_init(app):
    asyncio.create_task(scan(app))

def main():
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
