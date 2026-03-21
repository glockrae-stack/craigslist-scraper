"""
Virtual Broker Bot — main.py
─────────────────────────────────────────────
Craigslist:  Wave-based RSS scanning with priority scoring
OfferUp:     Deep link alerts per city
Proxy:       WebShare Rotating Residential — real US IPs
"""

import asyncio
import feedparser
import logging
import os
import random
import re
from functools import partial
import urllib.request
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
TOKEN   = "8761442506:AAGs-ec3RXZ_9O86DIxMCSlEjiN9r0ytLk4"
CHAT_ID = "6549307194"
DB_FILE = "seen_ids.txt"

# WebShare Rotating Residential Proxy
PROXY_URL = "http://oyexvpgk-AD-AE-AF-AG-AI-AL-AM-AO-AR-AT-AU-AW-AX-AZ-BA-BB-BD-BE-BF-BG-BH-BI-BJ-BM-BN-BO-BQ-BR-BS-BT-BW-BY-BZ-CA-CD-CG-CH-CI-CL-CM-CN-CO-CR-CU-CV-CW-CY-CZ-DJ-DK-DM-DO-DZ-EC-EE-EG-ER-ET-FI-FJ-FM-FO-GA-GB-GD-GE-GF-GG-GH-GI-GL-GM-GN-GP-GQ-GR-GT-GU-GW-GY-HK-HN-HR-HT-HU-ID-IE-IL-IM-IN-IQ-IR-IS-JE-JM-JO-JP-KE-KG-KH-KM-KN-KR-KW-KY-KZ-LA-LB-LC-LI-LK-LR-LS-LT-LU-LV-LY-MA-MC-MD-ME-MF-MG-MH-MK-ML-MM-MN-MO-MP-MQ-MR-MS-MT-MU-MV-MW-MX-MY-MZ-NA-NC-NE-NG-NI-NL-NO-NP-NZ-OM-PA-PE-PF-PG-PH-PK-PL-PR-PS-PT-PW-PY-QA-RE-RO-RS-RU-RW-SA-SB-SC-SD-SE-SG-SH-SI-SK-SL-SM-SN-SO-SR-SS-ST-SV-SX-SY-SZ-TC-TG-TH-TJ-TL-TN-TO-TR-TT-TW-TZ-UA-UG-US-UY-UZ-VC-VE-VG-VI-VN-VU-WS-YE-YT-ZA-ZM-ZW-rotate:tde8ndie2iu8@p.webshare.io:80"

# Wave timing
BREAK_MIN      = 60
BREAK_MAX      = 180
LONG_BREAK_MIN = 360
LONG_BREAK_MAX = 720
REQ_DELAY_MIN  = 8
REQ_DELAY_MAX  = 22

# ─────────────────────────────────────────────
# USER AGENTS
# ─────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 Chrome/112.0.0.0 Mobile Safari/537.36",
]

def get_headers():
    return {
        "User-Agent":      random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer":         "https://www.google.com/",
    }

# ─────────────────────────────────────────────
# CITIES
# ─────────────────────────────────────────────
CL_CITIES = {
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

OU_CITIES = {
    "Phoenix":          "phoenix-az",
    "Los Angeles":      "los-angeles-ca",
    "San Diego":        "san-diego-ca",
    "SF Bay":           "san-francisco-ca",
    "Colorado Springs": "colorado-springs-co",
    "Washington DC":    "washington-dc",
    "Atlanta":          "atlanta-ga",
    "Chicago":          "chicago-il",
    "New Orleans":      "new-orleans-la",
    "Boston":           "boston-ma",
    "Detroit":          "detroit-mi",
    "Minneapolis":      "minneapolis-mn",
    "Las Vegas":        "las-vegas-nv",
    "Albuquerque":      "albuquerque-nm",
    "New York":         "new-york-ny",
    "Portland":         "portland-or",
    "Dallas":           "dallas-tx",
    "Austin":           "austin-tx",
    "Miami":            "miami-fl",
    "Seattle":          "seattle-wa",
}

OU_CATEGORIES = {
    "cars":  "🚗 CARS BY OWNER",
    "boats": "⛵ BOATS BY OWNER",
    "free":  "🆓 FREE STUFF",
}

def ou_link(slug: str, query: str) -> str:
    return f"https://offerup.com/search/?q={query}&location={slug}&delivery_param=p&sort=-p"

# ─────────────────────────────────────────────
# PRIORITY SCORING
# ─────────────────────────────────────────────
HIGH_VALUE_KEYWORDS = ["must go", "asap", "first come", "moving", "today only", "free today"]
GOOD_CONDITION      = ["like new", "excellent", "clean", "barely used", "mint", "perfect"]
BAD_CONDITION       = ["needs work", "broken", "for parts", "not working", "as is"]
HIGH_DEMAND_ITEMS   = [
    "sectional", "dresser", "bed frame", "mattress", "nightstand",
    "ikea", "bookcase", "kallax", "fire pit", "patio", "outdoor",
    "weights", "dumbbell", "bench press", "squat rack",
    "air hockey", "ping pong", "arcade", "mini fridge",
]
BRANDS = [
    "apple", "macbook", "iphone", "sony", "samsung", "dyson",
    "nintendo", "ps5", "xbox", "milwaukee", "dewalt", "snap on",
    "herman miller", "steelcase", "honda", "toyota", "lexus",
]

def score_listing(title: str) -> int:
    t = title.lower()
    score = 0
    if any(k in t for k in HIGH_VALUE_KEYWORDS): score += 3
    if any(b in t for b in BRANDS):              score += 3
    if any(i in t for i in HIGH_DEMAND_ITEMS):   score += 2
    if any(g in t for g in GOOD_CONDITION):      score += 2
    if any(b in t for b in BAD_CONDITION):       score -= 2
    return score

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

# ─────────────────────────────────────────────
# SEEN IDs — APPEND ONLY
# ─────────────────────────────────────────────
def load_seen_ids() -> set:
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def mark_seen(lid: str):
    with open(DB_FILE, "a") as f:
        f.write(f"{lid}\n")

seen_ids = load_seen_ids()
log.info("Loaded %d seen IDs", len(seen_ids))

# ─────────────────────────────────────────────
# PARSERS
# ─────────────────────────────────────────────
def extract_price(text: str) -> str:
    paren = re.search(r'\(\s*(\$[\d,]+)\s*\)', text)
    if paren:
        return paren.group(1)
    bare = re.search(r'\$[\d,]+', text)
    if bare:
        return bare.group(0)
    return ""

def extract_mileage(text: str) -> str:
    for pat in [r'odometer[:\s]+([0-9,]+)', r'([0-9,]+)\s*(?:miles|mi\b)']:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            raw = m.group(1).replace(",", "")
            try:
                return f"{int(raw):,} mi"
            except:
                pass
    return ""

# ─────────────────────────────────────────────
# ALERT SENDER
# ─────────────────────────────────────────────
async def send_alert(app, title: str, link: str, city: str, price: str = "", mileage: str = "", priority: bool = False):
    parts = []
    if price:
        parts.append(f"💰 {price}")
    if mileage:
        parts.append(f"🛣️ {mileage}")
    parts.append(f"🏙️ {city}")

    prefix = "🔥 " if priority else ""
    msg = f"{prefix}*{title.upper()}*\n{' • '.join(parts)}"
    kb  = InlineKeyboardMarkup([[InlineKeyboardButton("⚡ OPEN PULSE", url=link)]])

    await app.bot.send_message(
        CHAT_ID, msg,
        parse_mode="Markdown",
        reply_markup=kb,
        disable_web_page_preview=True
    )
    log.info("%s[%s] %s", "🔥 " if priority else "✅ ", city, title[:60])

# ─────────────────────────────────────────────
# CRAIGSLIST FETCH — through rotating proxy
# ─────────────────────────────────────────────
def _fetch_feed(url: str, headers: dict):
    proxy_handler = urllib.request.ProxyHandler({
        "http":  PROXY_URL,
        "https": PROXY_URL,
    })
    opener = urllib.request.build_opener(proxy_handler)
    opener.addheaders = list(headers.items())
    try:
        response = opener.open(url, timeout=15)
        content  = response.read()
        return feedparser.parse(content)
    except Exception as e:
        raise e

# ─────────────────────────────────────────────
# CRAIGSLIST WAVE
# ─────────────────────────────────────────────
async def craigslist_wave(app, feed_type: str):
    loop       = asyncio.get_event_loop()
    city_items = list(CL_CITIES.items())
    random.shuffle(city_items)
    wave_cities = city_items[:random.randint(8, len(city_items))]

    high_priority = []
    normal        = []

    category_map = {"cars": "cto", "boats": "boo", "free": "zip"}
    cl_cat = category_map[feed_type]

    for city_label, cl_slug in wave_cities:
        url = f"https://{cl_slug}.craigslist.org/search/{cl_cat}?format=rss"
        try:
            feed = await loop.run_in_executor(None, partial(_fetch_feed, url, get_headers()))
            log.info("CL [%s | %s] → %d entries", city_label, feed_type, len(feed.entries))

            for entry in feed.entries:
                entry_id = getattr(entry, "id", entry.link)
                if entry_id in seen_ids:
                    continue

                title = entry.title.strip()

                if feed_type == "free" and "free" not in title.lower():
                    seen_ids.add(entry_id)
                    mark_seen(entry_id)
                    continue

                price   = extract_price(title)
                desc    = getattr(entry, "summary", "") or ""
                mileage = extract_mileage(desc) if feed_type == "cars" else ""
                score   = score_listing(title)

                item = (title, entry.link, city_label, price, mileage, score)
                seen_ids.add(entry_id)
                mark_seen(entry_id)

                if score >= 5:
                    await send_alert(app, title, entry.link, city_label, price, mileage, priority=True)
                elif score >= 2:
                    high_priority.append(item)
                else:
                    normal.append(item)

        except Exception as e:
            log.error("CL ERROR [%s | %s]: %s", city_label, feed_type, e)
            continue

        delay = random.randint(REQ_DELAY_MIN, REQ_DELAY_MAX)
        if random.random() < 0.1:
            delay += random.randint(20, 40)
        await asyncio.sleep(delay)

    for title, link, city, price, mileage, _ in high_priority:
        await send_alert(app, title, link, city, price, mileage, priority=True)
        await asyncio.sleep(1)

    for title, link, city, price, mileage, _ in normal:
        await send_alert(app, title, link, city, price, mileage)
        await asyncio.sleep(0.5)

# ─────────────────────────────────────────────
# OFFERUP LOOP
# ─────────────────────────────────────────────
async def offerup_loop(app):
    log.info("✅ OfferUp loop started — %d cities", len(OU_CITIES))

    while True:
        for city_label, slug in OU_CITIES.items():
            for cat_query, cat_title in OU_CATEGORIES.items():
                alert_id = f"ou_{slug}_{cat_query}"
                if alert_id in seen_ids:
                    continue
                link = ou_link(slug, cat_query)
                await send_alert(app, f"{cat_title} — {city_label}", link, city_label)
                seen_ids.add(alert_id)
                mark_seen(alert_id)
                await asyncio.sleep(random.uniform(2, 4))

        log.info("📲 OU cycle done. Sleeping 300s...")
        ou_keys = [k for k in seen_ids if k.startswith("ou_")]
        for k in ou_keys:
            seen_ids.discard(k)
        await asyncio.sleep(300)

# ─────────────────────────────────────────────
# MAIN CRAIGSLIST LOOP
# ─────────────────────────────────────────────
async def craigslist_loop(app):
    log.info("✅ Craigslist wave loop started")

    while True:
        categories = ["cars", "boats", "free"]
        random.shuffle(categories)

        for cat in categories:
            log.info("🌊 Starting wave: %s", cat)
            await craigslist_wave(app, cat)
            break_time = random.randint(BREAK_MIN, BREAK_MAX)
            log.info("😴 Break: %ds", break_time)
            await asyncio.sleep(break_time)

        long_break = random.randint(LONG_BREAK_MIN, LONG_BREAK_MAX)
        if random.random() < 0.2:
            long_break += random.randint(300, 600)
        log.info("💤 Long break: %ds", long_break)
        await asyncio.sleep(long_break)

# ─────────────────────────────────────────────
# COMMANDS
# ─────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚡ *Virtual Broker Bot is live.*\n\n"
        f"🚗 Craigslist: {len(CL_CITIES)} cities | Wave scanning\n"
        f"📲 OfferUp: {len(OU_CITIES)} cities | Deep links\n"
        f"🔥 Priority scoring active\n"
        f"🔒 Rotating residential proxy\n\n"
        "Commands:\n/start — this message\n/status — stats",
        parse_mode="Markdown"
    )

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"👀 *{len(seen_ids):,}* listings tracked\n"
        f"🚗 Craigslist: *{len(CL_CITIES)}* cities\n"
        f"📲 OfferUp: *{len(OU_CITIES)}* cities",
        parse_mode="Markdown"
    )

# ─────────────────────────────────────────────
# STARTUP
# ─────────────────────────────────────────────
async def post_init(app):
    asyncio.create_task(craigslist_loop(app))
    asyncio.create_task(offerup_loop(app))

def main():
    app = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    log.info("🤖 Virtual Broker Bot starting...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
