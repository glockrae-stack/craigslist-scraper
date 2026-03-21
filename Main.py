import asyncio
import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

SEEN = set()

CITIES = {
    "indianapolis": "https://indianapolis.craigslist.org",
    "chicago": "https://chicago.craigslist.org",
}

CATEGORIES = {
    "cars": "cta",        # cars & trucks
    "free": "zip",        # free stuff
    "boats": "boa"        # boats
}

MAX_AGE_MINUTES = 40


# ---------------------------
# TIME FILTER
# ---------------------------
def is_recent(post_time_str):
    try:
        post_time = datetime.fromisoformat(post_time_str)
        return datetime.utcnow() - post_time <= timedelta(minutes=MAX_AGE_MINUTES)
    except:
        return False


# ---------------------------
# CRAIGSLIST SCRAPER
# ---------------------------
async def fetch_craigslist(client, base_url, category_code):
    url = f"{base_url}/search/{category_code}?sort=date"

    try:
        r = await client.get(url, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        links = []

        for row in soup.select(".cl-search-result"):
            link_tag = row.select_one("a")
            time_tag = row.select_one("time")

            if not link_tag or not time_tag:
                continue

            link = link_tag.get("href")
            post_time = time_tag.get("datetime")

            if link and post_time and is_recent(post_time):
                if link not in SEEN:
                    SEEN.add(link)
                    links.append(link)

        return links

    except Exception as e:
        print(f"[CL ERROR] {url} → {e}")
        return []


# ---------------------------
# OFFERUP SCRAPER (NO API)
# ---------------------------
async def fetch_offerup(client, query):
    url = f"https://offerup.com/search/?q={query}"

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    try:
        r = await client.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        links = []

        for a in soup.select("a[href*='/item/detail/']"):
            link = "https://offer
