"""
Virtual Broker Bot — main.py
─────────────────────────────────────────────
Craigslist: RSS feeds (cto + boo + zip) — 17 cities
OfferUp:    Deep links (cars, boats, free) — click to browse newest pickup
1000+ alerts/day target via async + 3s random delay
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
SLEEP   = 90  # seconds between full CL cycles

# ─────────────────────────────────────────────
# HEADERS — spoofs a real browser so Railway
# doesn't get 403'd by Craigslist
# ─────────────────────────────────────────────
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
}

# OfferUp search queries per city
# &delivery_param=p = pickup only, &sort=-p = newest first
OU_QUERIES = ["cars", "boats", "free"]

def offerup_link(city_slug: str, query: str) -> str:
    return (
        f"https://offerup.com/search/"
        f"?q={query}&location={city_slug}"
        f"&delivery_param=p&sort=-p"
    )

# OfferUp city slugs for deep links
OU_SLUGS = {
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

def mark_seen(listing_id: str):
    with open(DB_FILE, "a") as f:
        f.write(f"{listing_id}\n")

seen_ids = load_seen_ids()
log.info("Loaded %d seen IDs", len(seen_ids))

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def extract_price(text: str) -> str:
    paren = re.search(r'\(\s*(\$[\d,]+)\s*\)', text)
    if paren:
        return paren.group(1)
    bare = re.search(r'\$[\d,]+', text)
    if bare:
        return bare.group(0)
    return ""

async def send_alert(app, title: str, link: str, city_label: str):
    price     = extract_price(title)
    price_str = f"💰 {price} | " if price else ""

    msg = (
        f"*{title.upper()}*\n"
        f"{price_str}🏙️ {city_label}"
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("⚡ OPEN PULSE", url=link)
    ]])
    await app.bot.send_message(
        CHAT_ID, msg,
        parse_mode="Markdown",
        reply_markup=kb,
        disable_web_page_preview=True
    )
    log.info("✅ SENT [%s]: %s", city_label, title[:60])

# ─────────────────────────────────────────────
# CRAIGSLIST LOOP
# feedparser with browser User-Agent header
# ─────────────────────────────────────────────
def _fetch_feed(url: str) -> object:
    return feedparser.parse(url, request_headers=HEADERS)

async def craigslist_loop(app):
    loop = asyncio.get_event_loop()
    log.info("✅ Craigslist loop started — %d cities", len(CITIES))

    while True:
        for city_label, cl_slug in CITIES.items():
            feeds = [
                (f"https://{cl_slug}.craigslist.org/search/cto?format=rss", "cars"),
                (f"https://{cl_slug}.craigslist.org/search/boo?format=rss", "boats"),
                (f"https://{cl_slug}.craigslist.org/search/zip?format=rss", "free"),
            ]
            for url, feed_type in feeds:
                try:
                    feed = await loop.run_in_executor(None, partial(_fetch_feed, url))
                    log.info("CL [%s | %s] → %d entries", city_label, feed_type, len(feed.entries))

                    new_count = 0
                    for entry in feed.entries:
                        entry_id = getattr(entry, "id", entry.link)
                        if entry_id in seen_ids:
                            continue
                        title = entry.title.strip()

                        # ZIP: only fire if 'free' is in the title
                        if feed_type == "free" and "free" not in title.lower():
                            seen_ids.add(entry_id)
                            mark_seen(entry_id)
                            continue

                        await send_alert(app, title, entry.link, city_label)
                        seen_ids.add(entry_id)
                        mark_seen(entry_id)
                        new_count += 1

                    if new_count:
                        log.info("CL [%s | %s] → %d NEW", city_label, feed_type, new_count)

                    # 3s random delay between each feed — stays under radar
                    await asyncio.sleep(random.uniform(2, 4))

                except Exception as e:
                    log.error("CL ERROR [%s | %s]: %s", city_label, feed_type, e)
                    continue

        log.info("🔄 CL cycle done. Sleeping %ds...", SLEEP)
        await asyncio.sleep(SLEEP)

# ─────────────────────────────────────────────
# OFFERUP PULSE LOOP
# Sends clickable deep links — no scraping,
# no blocks, forces newest pickup mode in app
# ─────────────────────────────────────────────
async def offerup_pulse_loop(app):
    log.info("✅ OfferUp pulse loop started")

    while True:
        for city_label, ou_slug in OU_SLUGS.items():
            for query in OU_QUERIES:
                link     = offerup_link(ou_slug, query)
                pulse_id = f"ou_pulse_{city_label}_{query}_{asyncio.get_event_loop().time():.0f}"

                msg = (
                    f"🏙️ *OFFERUP PULSE: {city_label.upper()}*\n"
                    f"🔍 Tap to browse newest *{query.upper()}* — pickup only"
                )
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton(f"⚡ SCAN OFFERUP: {query.upper()}", url=link)
                ]])
                try:
                    await app.bot.send_message(
                        CHAT_ID, msg,
                        parse_mode="Markdown",
                        reply_markup=kb,
                        disable_web_page_preview=True
                    )
                    log.info("OU PULSE [%s | %s]", city_label, query)
                except Exception as e:
                    log.error("OU PULSE ERROR [%s]: %s", city_label, e)

                await asyncio.sleep(random.uniform(2, 4))

        log.info("📲 OfferUp pulse cycle done. Sleeping 300s...")
        await asyncio.sleep(300)

# ─────────────────────────────────────────────
# COMMANDS
# ─────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚡ *Virtual Broker Bot is live.*\n\n"
        f"🚗 Craigslist: {len(CITIES)} cities | CTO + BOO + ZIP\n"
        f"📲 OfferUp: {len(CITIES)} cities | Pulse links every 5 mins\n"
        f"🎯 Target: 1,000+ alerts/day\n\n"
        "Commands:\n/start — this message\n/status — stats",
        parse_mode="Markdown"
    )

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"👀 *{len(seen_ids):,}* listings tracked\n"
        f"🚗 Craigslist: *{len(CITIES)}* cities\n"
        f"📲 OfferUp: *{len(CITIES)}* cities | {len(OU_QUERIES)} queries each",
        parse_mode="Markdown"
    )

# ─────────────────────────────────────────────
# STARTUP
# ─────────────────────────────────────────────
async def post_init(app):
    asyncio.create_task(craigslist_loop(app))
    asyncio.create_task(offerup_pulse_loop(app))

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
