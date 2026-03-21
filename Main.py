import requests
from bs4 import BeautifulSoup
import time

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

# -----------------------
# CRAIGSLIST CONFIG
# -----------------------
CITIES = {
    "indianapolis": "https://indianapolis.craigslist.org",
    "chicago": "https://chicago.craigslist.org"
}

CL_SECTIONS = {
    "cars": "cta",   # cars & trucks
    "boats": "boa",  # boats
    "free": "zip"    # free stuff
}

# -----------------------
# OFFERUP CONFIG
# -----------------------
OFFERUP_URLS = {
    "cars": "https://offerup.com/explore/k/cars-trucks/",
    "boats": "https://offerup.com/explore/k/boats/"
}

seen = set()

# -----------------------
# CRAIGSLIST SCRAPER
# -----------------------
def get_craigslist_links(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")

        links = []
        for a in soup.select(".cl-search-result a"):
            href = a.get("href")
            if href and href.startswith("http"):
                links.append(href)

        return links[:10]

    except Exception as e:
        print("CL ERROR:", e)
        return []

# -----------------------
# OFFERUP SCRAPER
# -----------------------
def get_offerup_links(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")

        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]

            if "/item/detail/" in href:
                full_link = "https://offerup.com" + href
                links.append(full_link)

        return list(set(links))[:10]

    except Exception as e:
        print("OU ERROR:", e)
        return []

# -----------------------
# MAIN LOOP
# -----------------------
