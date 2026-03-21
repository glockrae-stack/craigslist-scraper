"""
Virtual Broker Bot — main.py
─────────────────────────────────────────────
Craigslist:  Individual alert per listing (title, price, mileage, city)
OfferUp:     Individual alert per city+category (direct deep link)
Proxy:       WebShare rotating residential — US IPs, bypasses all blocks
"""

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
TOKEN   = os.getenv("8761442506:AAGs-ec3RXZ_9O86DIxMCSlEjiN9r0ytLk4")  # Set this in your env vars
CHAT_ID = 6549307194                   # Your chat ID (hardcoded safely)

DB_FILE = "seen_ids.txt"

# ─────────────────────────────────────────────
# PROXY CONFIG
# ─────────────────────────────────────────────
PROXY_HOST = "p.webshare.io"
PROXY_PORT = "80"
PROXY_USER = "oyexvpgk-ad-ae-af-ag-rotate"
PROXY_PASS = "tde8ndie2iu8"
PROXY_URL  = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}"

# ─────────────────────────────────────────────
# CITIES
# ─────────────────────────────────────────────
CL_CITIES = {
    "Phoenix": "phoenix",
    "Los Angeles": "losangeles",
    "San Diego": "sandiego",
    "SF Bay": "sfbay",
    "Colorado Springs": "cosprings",
    "Washington DC": "washingtondc",
    "Atlanta": "atlanta",
    "Chicago": "chicago",
    "New Orleans": "neworleans",
    "Boston": "boston",
    "Detroit": "detroit",
    "Minneapolis": "minneapolis",
    "Las Vegas": "lasvegas",
    "Albuquerque": "albuquerque",
    "New York": "newyork",
    "Portland": "portland",
    "Dallas": "dallas",
}

OU_CITIES = {
    "Phoenix": "phoenix-az",
    "Los Angeles": "los-angeles-ca",
    "San Diego": "san-diego-ca",
    "SF Bay": "san-francisco-ca",
    "Colorado Springs": "colorado-springs-co",
    "Washington DC": "washington-dc",
    "Atlanta": "atlanta-ga",
    "Chicago": "chicago-il",
    "New Orleans": "new-orleans-la",
    "Boston": "boston-ma",
    "Detroit": "detroit-mi",
    "Minneapolis": "minneapolis-mn",
    "Las Vegas": "las-vegas-nv",
    "Albuquerque": "albuquerque-nm",
    "New York": "new-york-ny",
    "Portland": "portland-or",
    "Dallas": "dallas-tx",
}

OU_CATEGORIES = {
    "cars":  "🚗 CARS BY OWNER",
    "boats": "⛵ BOATS BY OWNER",
    "free":  "🆓 FREE STUFF",
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
# SEEN IDS
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
    paren = re.search(r'\s*(\$[\d,]+)\s*', text)
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
