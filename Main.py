"""
Virtual Broker Bot — main.py
─────────────────────────────────────────────
Craigslist:  Rotates between 3 free RSS proxy services
             so no single one gets rate limited
             Real listing titles + price + mileage
OfferUp:     Individual deep link alerts per city
Priority:    Scoring on every listing
"""

import asyncio
import httpx
import logging
import os
import random
import re
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
TOKEN   = "8761442506:AAGs-ec3RXZ_9O86DIxMCSlEjiN9r0ytLk4"
CHAT_ID = "6549307194"
DB_FILE = "seen_ids.txt"

# Wave timing
BREAK_MIN      = 60
BREAK_MAX      = 120
LONG_BREAK_MIN = 300
LONG_BREAK_MAX = 600
REQ_DELAY_MIN  = 12
REQ_DELAY_MAX  = 25

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
# CRAIGSLIST FETCH
# Tries 3 different free RSS proxy services
# rotates so none get rate limited
# ─────────────────────────────────────────────
async def fetch_cl_feed(client: httpx.AsyncClient, rss_url: str) -> list:
    proxies = [
        # Service 1: rss2json
        lambda url: (
            "https://api.rss2json.com/v1/api.json",
            {"rss_url": url, "count": 50},
            "rss2json"
        ),
        # Service 2: Toptal feed2json
        lambda url: (
            f"https://www.toptal.com/developers/feed2json/convert?url={url}",
            {},
            "toptal"
        ),
        # Service 3: x2j.dev
        lambda url: (
            "https://x2j.dev/api/rss",
            {"url": url},
            "x2j"
        ),
    ]

    random.shuffle(proxies)

    for proxy_fn in proxies:
        endpoint, params, name = proxy_fn(rss_url)
        try:
            resp = await client.get(endpoint, params=params, timeout=20)
            if resp.status_code != 200:
                continue

            data = resp.json()

            # rss2json format
            if name == "rss2json":
                if data.get("status") != "ok":
                    continue
                items = data.get("items", [])
                if items:
                    log.info("CL via rss2json → %d items", len(items))
                    return [{"title": i.get("title",""), "link": i.get("link",""), "guid": i.get("guid",""), "description": i.get("description","")} for i in items]

            # Toptal format: returns RSS as JSON with channel.item array
            elif name == "toptal":
                channel = data.get("rss", {}).get("channel", {})
                raw_items = channel.get("item", [])
                if isinstance(raw_items, dict):
                    raw_items = [raw_items]
                if raw_items:
                    log.info("CL via toptal → %d items", len(raw_items))
                    return [{"title": i.get("title",""), "link": i.get("link",""), "guid": i.get("guid",""), "description": i.get("description","")} for i in raw_items]

            # x2j format
            elif name == "x2j":
                raw_items = data.get("items", [])
                if raw_items:
                    log.info("CL via x2j → %d items", len(raw_items))
                    return [{"title": i.get("title",""), "link": i.get("link",""), "guid": i.get("guid",""), "description": i.get("description","")} for i in raw_items]

        except Exception as e:
            log.warning("RSS proxy %s failed: %s", name, e)
            continue

    return []

# ─────────────────────────────────────────────
# CRAIGSLIST WAVE
# ─────────────────────────────────────────────
async def craigslist_wave(app, feed_type: str, client: httpx.AsyncClient):
    city_items = list(CL_CITIES.items())
    random.shuffle(city_items)
    wave_cities = city_items[:random.randint(8, len(city_items))]

    high_priority = []
    normal        = []

    category_map = {"cars": "cto", "boats": "boo", "free": "zip"}
    cl_cat = category_map[feed_type]

    for city_label, cl_slug in wave_cities:
        rss_url = f"https://{cl_slug}.craigslist.org/search/{cl_cat}?format=rss"
        try:
            items = await fetch_cl_feed(client, rss_url)
            log.info("CL [%s | %s] → %d items", city_label, feed_type, len(items))

            for item in items:
                entry_id = item.get("guid") or item.get("link", "")
                if entry_id in seen_ids:
                    continue

                title = item.get("title", "").strip()
                if not title:
                    continue

                if feed_type == "free" and "free" not in title.lower():
                    seen_ids.add(entry_id)
                    mark_seen(entry_id)
                    continue

                link    = item.get("link", "")
                price   = extract_price(title)
                desc    = item.get("description", "") or ""
                mileage = extract_mileage(desc) if feed_type == "cars" else ""
                score   = score_listing(title)

                seen_ids.add(entry_id)
                mark_seen(entry_id)

                if score >= 5:
                    await send_alert(app, title, link, city_label, price, mileage, priority=True)
                elif score >= 2:
                    high_priority.append((title, link, city_label, price, mileage))
                else:
                    normal.append((title, link, city_label, price, mileage))

        except Exception as e:
            log.error("CL ERROR [%s | %s]: %s", city_label, feed_type, e)
            continue

        delay = random.randint(REQ_DELAY_MIN, REQ_DELAY_MAX)
        await asyncio.sleep(delay)

    for title, link, city, price, mileage in high_priority:
        await send_alert(app, title, link, city, price, mileage, priority=True)
        await asyncio.sleep(1)

    for title, link, city, price, mileage in normal:
        await send_alert(app, title, link, city, price, mileage)
        await asyncio.sleep(0.5)

# ─────────────────────────────────────────────
# MAIN CRAIGSLIST LOOP
# ─────────────────────────────────────────────
async def craigslist_loop(app):
    log.info("✅ Craigslist loop started — rotating RSS proxies")

    async with httpx.AsyncClient() as client:
        while True:
            categories = ["cars", "boats", "free"]
            random.shuffle(categories)

            for cat in categories:
                log.info("🌊 Wave: %s", cat)
                await craigslist_wave(app, cat, client)
                break_time = random.randint(BREAK_MIN, BREAK_MAX)
                log.info("😴 Break: %ds", break_time)
                await asyncio.sleep(break_time)

            long_break = random.randint(LONG_BREAK_MIN, LONG_BREAK_MAX)
            log.info("💤 Long break: %ds", long_break)
            await asyncio.sleep(long_break)

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
# COMMANDS
# ─────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚡ *Virtual Broker Bot is live.*\n\n"
        f"🚗 Craigslist: {len(CL_CITIES)} cities | Rotating RSS proxies\n"
        f"📲 OfferUp: {len(OU_CITIES)} cities | Deep links\n"
        f"🔥 Priority scoring active\n\n"
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
