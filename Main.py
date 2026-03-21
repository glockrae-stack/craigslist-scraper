import asyncio
import httpx
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

CITIES = {
    "New York": "newyork",
    "Los Angeles": "losangeles",
    "Chicago": "chicago",
    "Dallas": "dallas",
    "Miami": "miami",
}

CATEGORIES = {
    "cars": "sss",
    "boats": "boa",
    "free": "zip"
}

async def fetch_craigslist(city_name, city_slug, category_name, category_code):
    url = f"https://{city_slug}.craigslist.org/search/{category_code}?sort=date"

    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=10) as client:
            res = await client.get(url)
            res.raise_for_status()

        soup = BeautifulSoup(res.text, "html.parser")
        listings = soup.select(".cl-static-search-result a")

        links = []
        for item in listings[:5]:  # limit spam
            link = item.get("href")
            if link and link.startswith("http"):
                links.append(link)

        print(f"\n[{city_name}] {category_name.upper()}")
        for l in links:
            print(l)

    except Exception as e:
        print(f"[CL ERROR] {city_name} | {category_name} → {e}")


async def main():
    while True:
        tasks = []

        for city_name, city_slug in CITIES.items():
            for category_name, category_code in CATEGORIES.items():
                tasks.append(
                    fetch_craigslist(city_name, city_slug, category_name, category_code)
                )

        await asyncio.gather(*tasks)

        print("\n[INFO] Waiting 60s before next cycle...\n")
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
