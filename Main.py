import requests
from bs4 import BeautifulSoup
import time

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

WEBHOOK = "YOUR_DISCORD_WEBHOOK"

CATEGORIES = {
    "cars+trucks": "cta",
    "boats": "boa",
}

CITIES = [
    "indianapolis",
    "chicago",
    "detroit"
]

seen = set()

def send(msg):
    requests.post(WEBHOOK, json={"content": msg})


def check_craigslist():
    global seen

    for city in CITIES:
        for name, code in CATEGORIES.items():
            url = f"https://{city}.craigslist.org/search/{code}?sort=date"

            try:
                res = requests.get(url, headers=HEADERS)
                soup = BeautifulSoup(res.text, "html.parser")

                posts = soup.select(".result-row")[:20]

                for post in posts:
                    post_id = post["data-pid"]

                    if post_id in seen:
                        continue

                    seen.add(post_id)

                    title = post.select_one(".result-title").text
                    link = post.select_one(".result-title")["href"]

                    send(f"📦 {city.upper()} | {name}\n{title}\n{link}")

            except Exception as e:
                print("CL ERROR:", e)


def offerup_links():
    links = [
        "https://offerup.com/search/?q=cars",
        "https://offerup.com/search/?q=boats"
    ]

    for link in links:
        send(f"🟣 OfferUp Live Feed:\n{link}")


while True:
    print("Scanning...")

    check_craigslist()
    offerup_links()

    time.sleep
