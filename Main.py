import asyncio
import httpx
import datetime
import random
from typing import List

# ---------------------------
# CONFIG
# ---------------------------
CL_CITIES = ["Las Vegas", "Austin", "Albuquerque", "SF Bay", "Chicago",
             "Phoenix", "Miami", "Los Angeles", "San Diego", "Washington DC",
             "Atlanta", "New York", "Portland", "Dallas", "Boston", "Detroit", "Minneapolis", "Colorado Springs"]

OU_CATEGORIES = ["cars", "boats", "free_stuff"]  # example categories

# store seen URLs to avoid reposting
seen_cl_items = set()
seen_ou_items = set()

# ---------------------------
# HELPERS
# ---------------------------
async def fetch_cl_feed(client: httpx.AsyncClient, city: str, category: str) -> List[dict]:
    """
    Fetch recent Craigslist items for a city/category
    Only keep items posted in the last 40 minutes
    """
    url = f"https://{city.lower().replace(' ', '')}.craigslist.org/search/{category}?sort=date"
    try:
        resp = await client.get(url, timeout=10)
        resp.raise_for_status()
        html = resp.text
        # Parse HTML: simple regex to extract links and timestamps
        # (replace with BeautifulSoup for more reliability)
        items = []
        import re
        for match in re.finditer(r'<a href="(https://[^"]+)".*?class="result-date" datetime="([^"]+)"', html):
            link, dt_str = match.groups()
            dt_posted = datetime.datetime.fromisoformat(dt_str)
            delta = datetime.datetime.now() - dt_posted
            if delta.total_seconds() <= 40 * 60 and link not in seen_cl_items:
                items.append({"link": link, "posted": dt_posted})
                seen_cl_items.add(link)
        return items
    except Exception as e:
        print(f"[CL ERROR] {city} | {category} → {e}")
        return []

async def fetch_ou_feed(client: httpx.AsyncClient, slug: str, category: str) -> List[dict]:
    """
    Fetch OfferUp feed for a category/slug
    Only keep new items
    """
    url = f"https://offerup.com/api/feed/{slug}/{category}"
    try:
        resp = await client.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        items = []
        for item in data.get("items", []):
            link = item.get("url")
            posted = datetime.datetime.fromisoformat(item.get("posted_at"))
            if link not in seen_ou_items:
                items.append({"link": link, "posted": posted})
                seen_ou_items.add(link)
        return items
    except Exception as e:
        print(f"[OU ERROR] {slug} | {category} → {e}")
        return []

async def process_cl():
    async with httpx.AsyncClient() as client:
        for city in CL_CITIES:
            for category in ["cars", "boats", "free_stuff"]:
                items = await fetch_cl_feed(client, city, category)
                for item in items:
                    print(f"✅ [CL] {city} | {category} → {item['link']}")
            await asyncio.sleep(random.uniform(1, 2))  # avoid hammering servers

async def process_ou():
    async with httpx.AsyncClient() as client:
        for category in OU_CATEGORIES:
            items = await fetch_ou_feed(client, "slug_placeholder", category)
            for item in items:
                print(f"✅ [OU] {category} → {item['link']}")
            await asyncio.sleep(random.uniform(1, 2))  # rate-limit

async def main_loop():
    while True:
        await asyncio.gather(process_cl(), process_ou())
        print(f"[INFO] Waiting 60s before next cycle...")
        await asyncio.sleep(60)  # cycle every minute

if __name__ == "__main__":
    asyncio.run(main_loop())
