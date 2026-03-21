import asyncio
import feedparser
import logging
import os
import random
import re
import urllib.request
from functools import partial
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
TOKEN   = "8761442506:AAGs-ec3RXZ_9O86DIxMCSlEjiN9r0ytLk4"
CHAT_ID = "6549307194"
DB_FILE = "seen_ids.txt"

# ─────────────────────────────────────────────
# PROXY (Webshare)
# ─────────────────────────────────────────────
PROXY_HOST = "p.webshare.io"
PROXY_PORT = "80"
PROXY_USER = "oyexvpgk-ad-ae-af-ag-rotate"
PROXY_PASS = "tde8ndie2iu8"
PROXY_URL  = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}"

# ─────────────────────────────────────────────
# USER AGENTS
# ─────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Version/16.0 Mobile Safari/604.1",
]

# ─────────────────────────────────────────────
# CITIES
# ─────────────────────────────────────────────
CL_CITIES = {
    "Chicago": "chicago",
    "Dallas": "dallas",
    "Atlanta": "atlanta",
    "Phoenix": "phoenix",
}

OU_CITIES = {
    "Chicago": "chicago-il",
    "Dallas": "dallas-tx",
    "Atlanta": "atlanta-ga",
    "Phoenix": "phoenix-az",
}

OU_CATEGORIES = {
    "cars":  "🚗 CARS BY OWNER",
    "boats": "⛵ BOATS BY OWNER",
    "free":  "🆓 FREE STUFF",
}

def ou_link(slug: str, query: str) -> str:
    return f"https://offerup.com/search/?q={query}&location={slug}&sort=-p"

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# SEEN IDS
# ─────────────────────────────────────────────
def load_seen_ids():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return set(line.strip() for line in f)
    return set()

def mark_seen(lid):
    with open(DB_FILE, "a") as f:
        f.write(f"{lid}\n")

seen_ids = load_seen_ids()

# ─────────────────────────────────────────────
# FETCH
# ─────────────────────────────────────────────
def fetch_feed(url):
    ua = random.choice(USER_AGENTS)

    proxy_handler = urllib.request.ProxyHandler({
        "http": PROXY_URL,
        "https": PROXY_URL,
    })

    opener = urllib.request.build_opener(proxy_handler)

    opener.addheaders = [
        ("User-Agent", ua),
        ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
        ("Accept-Language", "en-US,en;q=0.9"),
        ("Connection", "keep-alive"),
        ("Upgrade-Insecure-Requests", "1"),
    ]

    res = opener.open(url, timeout=15)
    return feedparser.parse(res.read())

# ─────────────────────────────────────────────
# ALERT
# ─────────────────────────────────────────────
async def send_alert(app, title, link, city):
    msg = f"*{title.upper()}*\n🏙️ {city}"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("OPEN", url=link)]
    ])

    await app.bot.send_message(
        CHAT_ID,
        msg,
        parse_mode="Markdown",
        reply_markup=kb,
        disable_web_page_preview=True
    )

# ─────────────────────────────────────────────
# HUMAN DELAY
# ─────────────────────────────────────────────
async def human_delay():
    delay = random.uniform(6, 12)

    if random.random() < 0.2:
        delay += random.uniform(10, 25)

    await asyncio.sleep(delay)

# ─────────────────────────────────────────────
# CRAIGSLIST LOOP
# ─────────────────────────────────────────────
async def craigslist_loop(app):
    loop = asyncio.get_event_loop()

    while True:
        for city, slug in CL_CITIES.items():
            urls = [
                f"https://{slug}.craigslist.org/search/cto?format=rss",
                f"https://{slug}.craigslist.org/search/boo?format=rss",
                f"https://{slug}.craigslist.org/search/zip?format=rss",
            ]

            for url in urls:
                try:
                    feed = await loop.run_in_executor(None, partial(fetch_feed, url))

                    for entry in feed.entries:
                        eid = getattr(entry, "id", entry.link)

                        if eid in seen_ids:
                            continue

                        await send_alert(app, entry.title, entry.link, city)

                        seen_ids.add(eid)
                        mark_seen(eid)

                except Exception as e:
                    log.error(f"CL ERROR [{city}]: {e}")

                await human_delay()

        await asyncio.sleep(120)

# ─────────────────────────────────────────────
# OFFERUP LOOP
# ─────────────────────────────────────────────
async def offerup_loop(app):
    while True:
        for city, slug in OU_CITIES.items():
            for cat, title in OU_CATEGORIES.items():
                key = f"{slug}_{cat}"

                if key in seen_ids:
                    continue

                link = ou_link(slug, cat)

                await send_alert(app, f"{title} — {city}", link, city)

                seen_ids.add(key)
                mark_seen(key)

                await human_delay()

        await asyncio.sleep(300)

# ─────────────────────────────────────────────
# COMMAND
# ─────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot running.")

# ─────────────────────────────────────────────
# START
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

    app.add_handler(CommandHandler("start", start))

    app.run_polling()

if __name__ == "__main__":
    main()
