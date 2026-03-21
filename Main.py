import os
import re
import time
import html
import gzip
from io import BytesIO
from urllib.parse import urlencode, quote_plus
from urllib.request import Request, urlopen
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET

# =========================
# CONFIG
# =========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()

MAX_AGE = timedelta(minutes=40)
SLEEP_SECONDS = 60

# Craigslist city slugs
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
    "Austin": "austin",
    "Miami": "miami",
    "Seattle": "seattle",
}

# Craigslist correct sections
CL_SECTIONS = {
    "cars + trucks": "cta",
    "boats": "boa",
    "free": "zip",
}

# OfferUp location slugs
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
    "Austin": "austin-tx",
    "Miami": "miami-fl",
    "Seattle": "seattle-wa",
}

# OfferUp search queries
OU_QUERIES = {
    "cars + trucks": "cars trucks",
    "boats": "boats",
    "free": "free",
}

SEEN_FILE = "seen_ids.txt"
seen = set()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

# =========================
# PERSISTENCE
# =========================
def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            for line in f:
                v = line.strip()
                if v:
                    seen.add(v)

def mark_seen(item_id: str):
    if item_id in seen:
        return
    seen.add(item_id)
    with open(SEEN_FILE, "a", encoding="utf-8") as f:
        f.write(item_id + "\n")

# =========================
# HTTP
# =========================
def fetch_text(url: str) -> str:
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=20) as resp:
        data = resp.read()
        enc = resp.headers.get("Content-Encoding", "").lower()
        if enc == "gzip":
            data = gzip.decompress(data)
        return data.decode("utf-8", errors="replace")

# =========================
# TELEGRAM
# =========================
def send_telegram(message: str):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print(message)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = urlencode(
        {
            "chat_id": CHAT_ID,
            "text": message,
            "disable_web_page_preview": "false",
        }
    ).encode("utf-8")

    req = Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": HEADERS["User-Agent"],
        },
    )
    with urlopen(req, timeout=20) as resp:
        resp.read()

# =========================
# CRAIGSLIST
# =========================
def is_recent(pub_date: str) -> bool:
    try:
        dt = parsedate_to_datetime(pub_date)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return now - dt <= MAX_AGE
    except Exception:
        return False

def fetch_craigslist_links(city_slug: str, section_code: str):
    url = f"https://{city_slug}.craigslist.org/search/{section_code}?format=rss"
    try:
        xml_text = fetch_text(url)
        root = ET.fromstring(xml_text)

        out = []
        for item in root.findall(".//item"):
            link = (item.findtext("link") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()

            if not link:
                continue
            if pub_date and not is_recent(pub_date):
                continue

            out.append(link)
        return out

    except Exception as e:
        print(f"[CL ERROR] {city_slug} | {section_code} → {e}")
        return []

# =========================
# OFFERUP
# =========================
def fetch_offerup_links(city_slug: str, query: str):
    url = f"https://offerup.com/search/?q={quote_plus(query)}&location={quote_plus(city_slug)}&sort=-p"
    try:
        page = fetch_text(url)

        links = []
        seen_local = set()

        # Grab any href that looks like an OfferUp item link or short link
        hrefs = re.findall(r'href="([^"]+)"', page)

        for href in hrefs:
            href = html.unescape(href)

            if href.startswith("//"):
                href = "https:" + href
            elif href.startswith("/"):
                href = "https://offerup.com" + href

            if "offerup.co/" in href or "/item/" in href or "/item/detail/" in href:
                href = href.split("?")[0]
                if href not in seen_local:
                    seen_local.add(href)
                    links.append(href)

        return links[:10]

    except Exception as e:
        print(f"[OU ERROR] {city_slug} | {query} → {e}")
        return []

# =========================
# MAIN LOOP
# =========================
def run():
    load_seen()
    print(f"[INFO] Loaded {len(seen)} seen IDs")

    while True:
        # Craigslist
        for city_name, city_slug in CL_CITIES.items():
            for label, section_code in CL_SECTIONS.items():
                links = fetch_craigslist_links(city_slug, section_code)

                for link in links:
                    item_id = f"cl::{link}"
                    if item_id in seen:
                        continue
                    mark_seen(item_id)
                    send_telegram(link)

        # OfferUp
        for city_name, city_slug in OU_CITIES.items():
            for label, query in OU_QUERIES.items():
                links = fetch_offerup_links(city_slug, query)

                for link in links:
                    item_id = f"ou::{link}"
                    if item_id in seen:
                        continue
                    mark_seen(item_id)
                    send_telegram(link)

        print(f"[INFO] Waiting {SLEEP_SECONDS}s before next cycle...")
        time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    run()
