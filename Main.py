"""
Virtual Broker Bot v5 — FINAL
─────────────────────────────────────────────
- Craigslist: 17 cities via RSS (cto + boo + zip) — every 90s
- OfferUp:    27 cities via mobile API — every 5 mins, 8s between cities
- WebShare rotating proxies — bypasses Railway geo-block
- seen_ids.txt is append-only (survives Railway restarts)

Install:
    pip install python-telegram-bot feedparser httpx
"""

import asyncio
import feedparser
import httpx
import os
import re
import logging
import random
import urllib.request
from functools import partial
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
TOKEN    = "8761442506:AAFPCQyaKuSbjuc4s8SwzKYvMAFHQ5QlgXY"
CHAT_ID  = "6549307194"
DB_FILE  = "seen_ids.txt"
CL_SLEEP = 90    # Craigslist: 90s between full cycles
OU_SLEEP = 300   # OfferUp: 5 mins between full cycles
OU_DELAY = 8     # 8s between each OfferUp city — looks human

# ─────────────────────────────────────────────
# WEBSHARE PROXIES
# All 5 rotate randomly — if one gets flagged others keep running
# To refresh: webshare.io → Proxy → List → swap IPs below
# ─────────────────────────────────────────────
PROXY_USER = "oyexvpgk"
PROXY_PASS = "tde8ndie2iu8"
PROXY_LIST = [
    f"http://{PROXY_USER}:{PROXY_PASS}@23.95.150.145:6114",
    f"http://{PROXY_USER}:{PROXY_PASS}@198.23.239.134:6540",
    f"http://{PROXY_USER}:{PROXY_PASS}@107.172.163.27:6543",
    f"http://{PROXY_USER}:{PROXY_PASS}@216.10.27.159:6837",
    f"http://{PROXY_USER}:{PROXY_PASS}@191.96.254.138:6185",
]

def get_proxy() -> str:
    return random.choice(PROXY_LIST)

# ─────────────────────────────────────────────
# CRAIGSLIST — 17 cities
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

# ─────────────────────────────────────────────
# OFFERUP — 27 cities by zip code
# ─────────────────────────────────────────────
OU_CITIES = {
    "San Francisco":  "94102",
    "Los Angeles":    "90001",
    "San Diego":      "91911",
    "Sacramento":     "94203",
    "Colorado":       "80014",
    "Seattle":        "98198",
    "Tampa Bay":      "33593",
    "Atlanta":        "30033",
    "Chicago":        "60007",
    "Boston":         "02108",
    "Minneapolis":    "55111",
    "Las Vegas":      "88901",
    "Cleveland":      "44101",
    "Portland":       "97229",
    "Austin":         "73301",
    "Dallas":         "75001",
    "Houston":        "77001",
    "Miami":          "33101",
    "Baltimore":      "21201",
    "Birmingham AL":  "35242",
    "St. Louis":      "63101",
    "Detroit":        "48127",
    "Phoenix":        "85001",
    "Hawaii":         "96731",
    "Salt Lake City": "84044",
    "Nashville":      "37011",
    "Philadelphia":   "19019",
}

OU_HEADERS = {
    "User-Agent":      "OfferUp/app iOS/17.0 CFNetwork/1474 Darwin/23.0.0",
    "Accept":          "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection":      "keep-alive",
}

OU_BASE = "https://offerup.com/api/search/"

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
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

async def send_alert(app, city_label, title, link, price, source):
    price_str = f" | 💰 {price}" if price else ""
    icon      = "🚗" if source == "craigslist" else "📲"
    msg = (
        f"🚨 *NEW OWNER ALERT: {city_label.upper()}* {icon}\n"
        f"🔗 [VIEW LISTING]({link}){price_str}\n"
        f"📦 *ITEM: {title.upper()}*"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 VIEW POST", url=link)]])
    await app.bot.send_message(
        CHAT_ID, msg,
        parse_mode="Markdown",
        reply_markup=kb,
        disable_web_page_preview=True
    )
    log.info("✅ SENT [%s | %s]: %s", city_label, source.upper(), title)

# ─────────────────────────────────────────────
# CRAIGSLIST LOOP
# Uses urllib proxy handler since feedparser is sync
# ─────────────────────────────────────────────
def _fetch_feed(url: str, proxy: str):
    proxy_handler = urllib.request.ProxyHandler({
        "http":  proxy,
        "https": proxy,
    })
    opener = urllib.request.build_opener(proxy_handler)
    response = opener.open(url, timeout=15)
    content  = response.read()
    return feedparser.parse(content)

async def craigslist_loop(app):
    loop = asyncio.get_event_loop()
    log.info("✅ Craigslist loop started — %d cities.", len(CL_CITIES))

    while True:
        for city_label, cl_slug in CL_CITIES.items():
            feeds = [
                (f"https://{cl_slug}.craigslist.org/search/cto?format=rss", "cars"),
                (f"https://{cl_slug}.craigslist.org/search/boo?format=rss", "boats"),
                (f"https://{cl_slug}.craigslist.org/search/zip?format=rss", "free"),
            ]
            for url, feed_type in feeds:
                try:
                    proxy = get_proxy()
                    feed  = await loop.run_in_executor(None, partial(_fetch_feed, url, proxy))
                    log.info("CL [%s | %s] → %d entries", city_label, feed_type, len(feed.entries))

                    new_count = 0
                    for entry in feed.entries:
                        entry_id = getattr(entry, "id", entry.link)
                        if entry_id in seen_ids:
                            continue
                        title = entry.title.strip()
                        if feed_type == "free" and "free" not in title.lower():
                            seen_ids.add(entry_id)
                            mark_seen(entry_id)
                            continue
                        price = extract_price(title)
                        await send_alert(app, city_label, title, entry.link, price, "craigslist")
                        seen_ids.add(entry_id)
                        mark_seen(entry_id)
                        new_count += 1

                    if new_count:
                        log.info("CL [%s | %s] → %d NEW alerts sent", city_label, feed_type, new_count)

                    await asyncio.sleep(0.4)

                except Exception as e:
                    log.error("CL ERROR [%s | %s]: %s", city_label, feed_type, e)
                    continue

        log.info("🔄 CL cycle done. Sleeping %ds...", CL_SLEEP)
        await asyncio.sleep(CL_SLEEP)

# ─────────────────────────────────────────────
# OFFERUP LOOP
# Each city gets a fresh random proxy + 8s delay between cities
# ─────────────────────────────────────────────
async def fetch_offerup_city(city_label: str, zipcode: str, app):
    params = {
        "zip":                 zipcode,
        "radius":              30,
        "limit":               50,
        "sort":                "date",
        "delivery_preference": "local",
    }
    proxy = get_proxy()

    try:
        async with httpx.AsyncClient(proxy=proxy, timeout=20) as client:
            resp = await client.get(OU_BASE, params=params, headers=OU_HEADERS)
            resp.raise_for_status()
            data = resp.json()

        items = (
            data.get("data", {}).get("items", [])
            or data.get("items", [])
            or []
        )

        log.info("OU [%s | zip=%s] → %d items", city_label, zipcode, len(items))

        new_count = 0
        for item in items:
            item_id = str(item.get("id", ""))
            if not item_id:
                continue
            listing_id = f"ou_{item_id}"
            if listing_id in seen_ids:
                continue

            title     = item.get("title", "Untitled").strip()
            price_raw = item.get("price", {})
            if isinstance(price_raw, dict):
                amount = price_raw.get("amount", 0)
                price  = f"${amount:,.0f}" if amount else ""
            elif price_raw:
                price = f"${price_raw}"
            else:
                price = ""

            link = f"https://offerup.com/item/detail/{item_id}/"
            await send_alert(app, city_label, title, link, price, "offerup")
            seen_ids.add(listing_id)
            mark_seen(listing_id)
            new_count += 1

        if new_count:
            log.info("OU [%s] → %d NEW alerts sent", city_label, new_count)

    except httpx.HTTPStatusError as e:
        log.error("OU HTTP ERROR [%s | zip=%s]: %s", city_label, zipcode, e.response.status_code)
    except Exception as e:
        log.error("OU ERROR [%s | zip=%s]: %s", city_label, zipcode, e)

async def offerup_loop(app):
    log.info("✅ OfferUp loop started — %d cities, %ds delay, %ds cycle.", len(OU_CITIES), OU_DELAY, OU_SLEEP)
    while True:
        for city_label, zipcode in OU_CITIES.items():
            await fetch_offerup_city(city_label, zipcode, app)
            await asyncio.sleep(OU_DELAY)
        log.info("📲 OU cycle done. Sleeping %ds...", OU_SLEEP)
        await asyncio.sleep(OU_SLEEP)

# ─────────────────────────────────────────────
# COMMANDS
# ─────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ *Virtual Broker Bot v5 is live.*\n\n"
        f"🚗 Craigslist: {len(CL_CITIES)} cities | Every {CL_SLEEP}s\n"
        f"📲 OfferUp: {len(OU_CITIES)} cities | Every {OU_SLEEP}s\n"
        f"🔒 US proxies rotating on every request\n\n"
        "Commands:\n/start — this message\n/status — seen count",
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
    log.info("🤖 Virtual Broker Bot v5 starting...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
