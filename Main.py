"""
Virtual Broker Bot — main.py
─────────────────────────────────────────────
Craigslist:  Individual alert per listing (title, price, mileage, city)
OfferUp:     Individual alert per city+category (direct deep link, same format)
Both fire the same clean alert format with ⚡ OPEN PULSE button.
"""

import asyncio
import feedparser
import logging
import os
import random
import re
from functools import partial
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
TOKEN   = "8761442506:AAFPCQyaKuSbjuc4s8SwzKYvMAFHQ5QlgXY"
CHAT_ID = "6549307194"
DB_FILE = "seen_ids.txt"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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
}

# OfferUp categories — cars, boats, free
OU_CATEGORIES = {
    "cars":  ("🚗 CARS BY OWNER",  "cars"),
    "boats": ("⛵ BOATS BY OWNER", "boats"),
    "free":  ("🆓 FREE STUFF",     "free"),
}

def ou_link(slug: str, query: str) -> str:
    return f"https://offerup.com/search/?q={query}&location={slug}&delivery_param=p&sort=-p"

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
    patterns = [
        r'odometer[:\s]+([0-9,]+)',
        r'([0-9,]+)\s*(?:miles|mi\b)',
    ]
    for pat in patterns:
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
async def send_alert(app, title: str, link: str, city: str, price: str = "", mileage: str = ""):
    parts = []
    if price:
        parts.append(f"💰 {price}")
    if mileage:
        parts.append(f"🛣️ {mileage}")
    parts.append(f"🏙️ {city}")

    msg = f"*{title.upper()}*\n{' • '.join(parts)}"
    kb  = InlineKeyboardMarkup([[InlineKeyboardButton("⚡ OPEN PULSE", url=link)]])

    await app.bot.send_message(
        CHAT_ID, msg,
        parse_mode="Markdown",
        reply_markup=kb,
        disable_web_page_preview=True
    )
    log.info("✅ [%s] %s", city, title[:60])

# ─────────────────────────────────────────────
# CRAIGSLIST LOOP
# ─────────────────────────────────────────────
def _fetch_feed(url: str):
    return feedparser.parse(url, request_headers=HEADERS)

async def craigslist_loop(app):
    loop = asyncio.get_event_loop()
    log.info("✅ Craigslist loop started — %d cities", len(CL_CITIES))

    while True:
        for city_label, cl_slug in CL_CITIES.items():
            feeds = [
                (f"https://{cl_slug}.craigslist.org/search/cto?format=rss", "cars"),
                (f"https://{cl_slug}.craigslist.org/search/boo?format=rss", "boats"),
                (f"https://{cl_slug}.craigslist.org/search/zip?format=rss", "free"),
            ]
            for url, feed_type in feeds:
                try:
                    feed = await loop.run_in_executor(None, partial(_fetch_feed, url))
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

                        await send_alert(app, title, entry.link, city_label, price, mileage)
                        seen_ids.add(entry_id)
                        mark_seen(entry_id)

                    await asyncio.sleep(random.uniform(2, 4))

                except Exception as e:
                    log.error("CL ERROR [%s | %s]: %s", city_label, feed_type, e)
                    continue

        log.info("🔄 CL cycle done. Sleeping 90s...")
        await asyncio.sleep(90)

# ─────────────────────────────────────────────
# OFFERUP LOOP
# One alert per city per category — same format
# as Craigslist but links straight to OfferUp
# search filtered to pickup only + newest first
# ─────────────────────────────────────────────
async def offerup_loop(app):
    log.info("✅ OfferUp loop started — %d cities", len(OU_CITIES))

    while True:
        for city_label, slug in OU_CITIES.items():
            for cat_key, (cat_title, cat_query) in OU_CATEGORIES.items():
                # Use city+category as ID so it fires once per cycle
                alert_id = f"ou_{slug}_{cat_key}"
                if alert_id in seen_ids:
                    continue

                link = ou_link(slug, cat_query)

                await send_alert(
                    app,
                    title   = f"{cat_title} — {city_label}",
                    link    = link,
                    city    = city_label,
                )

                seen_ids.add(alert_id)
                mark_seen(alert_id)

                await asyncio.sleep(random.uniform(2, 4))

        log.info("📲 OU cycle done. Sleeping 300s...")
        # Clear OU seen IDs every cycle so links refresh
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
        f"🚗 Craigslist: {len(CL_CITIES)} cities | CTO + BOO + ZIP\n"
        f"📲 OfferUp: {len(OU_CITIES)} cities | Cars + Boats + Free\n\n"
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
