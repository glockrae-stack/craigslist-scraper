import asyncio
import os
import re
import random
import json
import logging
import signal
import sys
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
import aiohttp
from aiohttp import web
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ─── LOGGING ───
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger("scanner")

# ─── CONFIG ───
TOKEN = os.environ.get("TELEGRAM_TOKEN", "8712723612:AAFMSfy8dOyEpOoE-vQXAaMM2oIKVs7zsNA")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "6549307194")
DB_FILE = "seen_ids.json"

# ─── TIMING ───
MAX_AGE_MINUTES = 30       # Only alert listings posted within 30 minutes
SCAN_INTERVAL = 25         # Scan every 25 seconds for real-time alerts
SEEN_EXPIRY_HOURS = 4      # Expire seen IDs after 4 hours
PARALLEL_WORKERS = 15      # Number of parallel scan workers
PAGE_FETCH_WORKERS = 20    # Workers for fetching individual pages

# ─── 24/7 AUTOMATION ───
AUTO_RESTART_ON_ERROR = True
MAX_CONSECUTIVE_ERRORS = 10
ERROR_COOLDOWN_SECONDS = 60
HEALTH_CHECK_INTERVAL = 300  # Health check every 5 minutes

# ─── PROXY CONFIGURATION ───
USE_PROXY_FOR_OFFERUP = True
PROXY_RETRY_WITHOUT = True

PROXY_LIST = [
    "http://23.88.88.105:80",
    "http://65.108.203.35:18080",
    "http://4.213.98.253:80",
    "http://98.64.128.182:3129",
    "http://38.180.226.51:3129",
    "http://48.210.225.96:80",
    "http://174.138.119.88:80",
    "http://65.108.203.37:18080",
    "http://129.150.39.242:8118",
    "http://97.74.87.226:80",
    "http://167.71.60.190:8080",
    "http://35.225.22.61:80",
    "http://51.141.175.118:80",
    "http://47.89.184.18:3129",
    "http://150.136.153.231:80",
    "http://74.176.195.135:80",
    "http://142.93.202.130:3129",
    "http://172.183.241.1:8080",
    "http://20.205.61.143:80",
    "http://52.226.125.228:8080",
    "http://20.206.106.192:80",
    "http://47.251.70.179:80",
    "http://20.219.176.57:3129",
    "http://20.44.188.17:3129",
    "http://20.204.212.76:3129",
    "http://20.204.214.79:3129",
]

working_proxies = list(PROXY_LIST)
failed_proxies = set()

def get_proxy():
    if not USE_PROXY_FOR_OFFERUP:
        return None
    if working_proxies:
        return random.choice(working_proxies)
    if failed_proxies:
        working_proxies.extend(PROXY_LIST)
        failed_proxies.clear()
    return random.choice(PROXY_LIST) if PROXY_LIST else None

def mark_proxy_failed(proxy):
    if proxy and proxy in working_proxies:
        working_proxies.remove(proxy)
        failed_proxies.add(proxy)

def mark_proxy_success(proxy):
    if proxy and proxy in failed_proxies:
        failed_proxies.remove(proxy)
        if proxy not in working_proxies:
            working_proxies.append(proxy)

async def refresh_proxy_list(session):
    global working_proxies
    try:
        url = "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=5000&country=us&ssl=all&anonymity=elite"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                text = await resp.text()
                new_proxies = [f"http://{p.strip()}" for p in text.strip().split('\n') if p.strip()]
                added = 0
                for p in new_proxies[:30]:
                    if p not in working_proxies and p not in failed_proxies:
                        working_proxies.append(p)
                        added += 1
                if added > 0:
                    log.info(f"Added {added} fresh proxies (total: {len(working_proxies)})")
    except Exception as e:
        log.debug(f"Could not refresh proxies: {e}")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"

# ─── CRAIGSLIST CITIES ───
CL_CITIES = {
    "Phoenix, AZ": "phoenix", "Los Angeles, CA": "losangeles", "San Diego, CA": "sandiego",
    "San Francisco, CA": "sfbay", "Colorado Springs, CO": "cosprings", "Washington DC": "washingtondc",
    "Atlanta, GA": "atlanta", "Chicago, IL": "chicago", "New Orleans, LA": "neworleans",
    "Boston, MA": "boston", "Detroit Metro": "detroit", "Minneapolis, MN": "minneapolis",
    "Las Vegas, NV": "lasvegas", "Albuquerque, NM": "albuquerque", "New York City, NY": "newyork",
    "Portland, OR": "portland", "Dallas, TX": "dallas",
}

# ─── OFFERUP LOCATIONS ───
OU_LOCS = {
    "San Francisco": (37.7749, -122.4194, "94102"), "Los Angeles": (34.0522, -118.2437, "90001"),
    "San Diego": (32.7157, -117.1611, "91911"), "Sacramento": (38.5816, -121.4944, "94203"),
    "Colorado": (39.7392, -104.9903, "80014"), "Seattle": (47.6062, -122.3321, "98198"),
    "Tampa Bay": (27.9506, -82.4572, "33593"), "Atlanta": (33.7490, -84.3880, "30033"),
    "Chicago": (41.8781, -87.6298, "60007"), "Boston": (42.3601, -71.0589, "02108"),
    "Minneapolis": (44.9778, -93.2650, "55111"), "Las Vegas": (36.1699, -115.1398, "88901"),
    "Cleveland": (41.4993, -81.6944, "44101"), "Portland": (45.5152, -122.6784, "97229"),
    "Austin": (30.2672, -97.7431, "73301"), "Dallas": (32.7767, -96.7970, "75001"),
    "Houston": (29.7604, -95.3698, "77001"), "Miami": (25.7617, -80.1918, "33101"),
    "Baltimore": (39.2904, -76.6122, "21201"), "St. Louis": (38.6270, -90.1994, "63101"),
    "Detroit": (42.3314, -83.0458, "48127"), "Phoenix": (33.4484, -112.0740, "85001"),
    "Hawaii": (21.3069, -157.8583, "96731"), "Salt Lake City": (40.7608, -111.8910, "84044"),
    "Nashville": (36.1627, -86.7816, "37011"), "Philadelphia": (39.9526, -75.1652, "19019"),
}

# ─── SEEN IDs (TIME-BASED) ───
seen = {}

def load_seen():
    global seen
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                data = json.load(f)
                now = datetime.now(timezone.utc)
                expiry = timedelta(hours=SEEN_EXPIRY_HOURS)
                seen = {}
                for lid, ts_str in data.items():
                    try:
                        ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                        if now - ts < expiry:
                            seen[lid] = ts_str
                    except:
                        pass
        except:
            seen = {}
    log.info(f"Loaded {len(seen)} active seen IDs")

def save_seen():
    try:
        with open(DB_FILE, 'w') as f:
            json.dump(seen, f)
    except Exception as e:
        log.warning(f"Failed to save seen IDs: {e}")

def mark_seen(lid):
    seen[lid] = datetime.now(timezone.utc).isoformat()
    if len(seen) % 100 == 0:
        save_seen()

def is_seen(lid):
    if lid not in seen:
        return False
    try:
        ts = datetime.fromisoformat(seen[lid].replace('Z', '+00:00'))
        if datetime.now(timezone.utc) - ts > timedelta(hours=SEEN_EXPIRY_HOURS):
            del seen[lid]
            return False
        return True
    except:
        return False

def cleanup_seen():
    global seen
    now = datetime.now(timezone.utc)
    expiry = timedelta(hours=SEEN_EXPIRY_HOURS)
    old_count = len(seen)
    seen = {lid: ts for lid, ts in seen.items() 
            if now - datetime.fromisoformat(ts.replace('Z', '+00:00')) < expiry}
    if old_count != len(seen):
        log.info(f"Cleanup: {old_count} -> {len(seen)} seen IDs")
    save_seen()

load_seen()

# ─── RUNTIME STATE ───
scan_running = False
shutdown_event = asyncio.Event()
consecutive_errors = 0
stats = {
    "scans_completed": 0,
    "alerts_sent": 0,
    "errors": 0,
    "uptime_start": datetime.now(timezone.utc).isoformat()
}

# ─── ALERT QUEUE ───
alert_queue = asyncio.Queue()

# ─── HELPERS ───
def get_mileage(text):
    if not text:
        return ""
    match = re.search(r'(\d{2,3})[kK]\s*(?:mi|miles?)', text)
    if match:
        return f"{match.group(1)}k mi"
    match = re.search(r'(\d{1,3},\d{3})\s*(?:mi|miles?)', text)
    if match:
        return f"{match.group(1)} mi"
    return ""

def parse_cl_timestamp(time_str):
    """Parse Craigslist timestamp to datetime."""
    if not time_str:
        return None
    try:
        # Format: "2024-03-23T10:30:00-0700" or similar
        dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
        return dt.astimezone(timezone.utc)
    except:
        return None

def parse_relative_time(text):
    """Parse relative time like '5 minutes ago' to datetime."""
    if not text:
        return None
    text = text.lower().strip()
    now = datetime.now(timezone.utc)
    
    # "just now", "moments ago"
    if "just" in text or "moment" in text or "now" in text:
        return now
    
    # "X minutes ago"
    match = re.search(r'(\d+)\s*min', text)
    if match:
        return now - timedelta(minutes=int(match.group(1)))
    
    # "X hours ago"
    match = re.search(r'(\d+)\s*hour', text)
    if match:
        return now - timedelta(hours=int(match.group(1)))
    
    # "X days ago"
    match = re.search(r'(\d+)\s*day', text)
    if match:
        return now - timedelta(days=int(match.group(1)))
    
    return None


async def fetch_cl_listing_details(session, url):
    """Fetch individual CL listing page for timestamp and image."""
    try:
        async with session.get(url, headers={"User-Agent": UA}, timeout=aiohttp.ClientTimeout(total=6)) as resp:
            if resp.status != 200:
                return None, None
            html = await resp.text()
            
            # Extract timestamp
            timestamp = None
            # Try datetime attribute
            time_match = re.search(r'<time[^>]*datetime="([^"]+)"', html)
            if time_match:
                timestamp = parse_cl_timestamp(time_match.group(1))
            
            # Try posted date text
            if not timestamp:
                posted_match = re.search(r'posted:\s*<time[^>]*>([^<]+)</time>', html, re.I)
                if posted_match:
                    timestamp = parse_relative_time(posted_match.group(1))
            
            # Extract image
            image = None
            img_match = re.search(r'<meta property="og:image" content="([^"]+)"', html)
            if img_match:
                image = img_match.group(1)
            
            return timestamp, image
    except Exception as e:
        log.debug(f"Failed to fetch CL details: {e}")
        return None, None


async def fetch_ou_listing_details(session, listing_id):
    """Fetch individual OfferUp listing for timestamp."""
    try:
        url = f"https://offerup.com/item/detail/{listing_id}"
        proxy = get_proxy()
        proxy_kwargs = {"proxy": proxy} if proxy else {}
        
        async with session.get(url, headers={"User-Agent": UA}, **proxy_kwargs, 
                              timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status != 200:
                return None
            html = await resp.text()
            
            # Look for __NEXT_DATA__ with listing details
            match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
            if not match:
                return None
            
            data = json.loads(match.group(1))
            listing = data.get("props", {}).get("pageProps", {}).get("listing", {})
            
            # Get posted date
            posted_date = listing.get("postedDate") or listing.get("createdDate")
            if posted_date:
                try:
                    return datetime.fromisoformat(posted_date.replace('Z', '+00:00'))
                except:
                    pass
            
            # Try relative time
            time_ago = listing.get("timeAgo") or listing.get("postedTimeAgo")
            if time_ago:
                return parse_relative_time(time_ago)
            
            return None
    except Exception as e:
        log.debug(f"Failed to fetch OU details: {e}")
        return None


async def send_alert(bot, session, listing):
    """Send Telegram alert."""
    parts = []
    if listing.get("price") and listing["price"] not in ["FREE", "$0", ""]:
        parts.append(f"💰 {listing['price']}")
    if listing.get("mileage"):
        parts.append(f"🛣️ {listing['mileage']}")
    parts.append(f"🏙️ {listing['location']}")

    cat = listing.get("category", "")
    if cat == "free":
        parts.append("🆓 FREE")
    elif cat == "cars":
        parts.append("🚗 CARS")
    elif cat == "boats":
        parts.append("🚤 BOATS")

    # Show actual timestamp
    if listing.get("time"):
        age_seconds = (datetime.now(timezone.utc) - listing["time"]).total_seconds()
        mins = max(0, int(age_seconds / 60))
        if mins < 1:
            parts.append("⏰ JUST POSTED!")
        elif mins < 60:
            parts.append(f"⏰ {mins}m ago")
        else:
            hours = mins // 60
            parts.append(f"⏰ {hours}h ago")
    else:
        parts.append("⏰ NEW")

    safe_title = re.sub(r'[*_`\[\]]', '', str(listing.get("title", "")))[:80].upper()
    caption = f"🔔 *{listing['source']}* | {safe_title}\n{' • '.join(parts)}"
    kb = [[InlineKeyboardButton(text="🔗 VIEW LISTING", url=listing["link"])]]
    
    price_display = listing.get('price', 'N/A')
    img = listing.get("image", "")
    
    if img:
        try:
            if "craigslist" in img:
                async with session.get(img, headers={"User-Agent": UA}, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                    if resp.status == 200:
                        await bot.send_photo(chat_id=CHAT_ID, photo=await resp.read(),
                                           caption=caption, parse_mode="Markdown",
                                           reply_markup=InlineKeyboardMarkup(kb))
                        log.info(f"✅ SENT: {listing['source']} - {safe_title[:30]}... ({price_display})")
                        return True
            else:
                await bot.send_photo(chat_id=CHAT_ID, photo=img, caption=caption, 
                                   parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
                log.info(f"✅ SENT: {listing['source']} - {safe_title[:30]}... ({price_display})")
                return True
        except Exception as e:
            log.debug(f"Image send failed: {e}")

    try:
        await bot.send_message(chat_id=CHAT_ID, text=caption, parse_mode="Markdown",
                              reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
        log.info(f"✅ SENT (text): {listing['source']} - {safe_title[:30]}... ({price_display})")
        return True
    except Exception as e:
        log.error(f"❌ Alert send FAILED: {e}")
        return False


async def alert_sender(bot, session, counter):
    """Process alert queue and send messages."""
    while True:
        try:
            listing = await alert_queue.get()
            
            if listing is None:
                break
            if is_seen(listing["id"]):
                alert_queue.task_done()
                continue

            # Age filter with actual timestamp
            if listing.get("time"):
                age_minutes = (datetime.now(timezone.utc) - listing["time"]).total_seconds() / 60
                if age_minutes > MAX_AGE_MINUTES:
                    mark_seen(listing["id"])
                    alert_queue.task_done()
                    continue

            if await send_alert(bot, session, listing):
                counter["sent"] += 1
                stats["alerts_sent"] += 1
                mark_seen(listing["id"])

            await asyncio.sleep(0.05)
            alert_queue.task_done()

        except Exception as e:
            log.error(f"alert_sender error: {e}")
            try:
                alert_queue.task_done()
            except:
                pass


# ─── CRAIGSLIST SCANNER WITH INDIVIDUAL PAGE FETCH ───
async def process_cl_listing(session, href, city, cat_name, title, price, counter, semaphore):
    """Process individual CL listing - fetch page for timestamp."""
    async with semaphore:
        try:
            id_match = re.search(r'/(\d+)\.html', href)
            lid = f"cl_{id_match.group(1)}" if id_match else f"cl_{hash(href)}"
            
            if is_seen(lid):
                return
            
            # Fetch individual page for timestamp
            timestamp, image = await fetch_cl_listing_details(session, href)
            
            # Skip if too old
            if timestamp:
                age_minutes = (datetime.now(timezone.utc) - timestamp).total_seconds() / 60
                if age_minutes > MAX_AGE_MINUTES:
                    mark_seen(lid)
                    return
            
            mileage = get_mileage(title) if cat_name in ["cars", "boats"] else ""
            
            counter["new"] += 1
            await alert_queue.put({
                "id": lid, "source": "CL", "title": title, "link": href,
                "price": price, "location": city, "category": cat_name,
                "mileage": mileage, "time": timestamp, "image": image or ""
            })
        except Exception as e:
            log.debug(f"CL listing error: {e}")


async def scan_cl_city(session, city, slug, categories, counter, semaphore):
    """Scan a single CL city."""
    for cat_name, cat_code in categories:
        try:
            url = f"https://{slug}.craigslist.org/search/{cat_code}?sort=date"
            
            async with session.get(url, headers={"User-Agent": UA},
                                  timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    continue
                html = await resp.text()
                soup = BeautifulSoup(html, "html.parser")
                results = soup.select(".cl-static-search-result")[:10]
                counter["found"] += len(results)
                
                # Process each listing in parallel
                tasks = []
                for r in results:
                    link_tag = r.select_one("a")
                    if not link_tag:
                        continue
                    href = link_tag.get("href", "")
                    if not href:
                        continue
                    
                    title_el = r.select_one(".title")
                    title = title_el.get_text(strip=True) if title_el else "Item"
                    price_el = r.select_one(".price")
                    price = price_el.get_text(strip=True) if price_el else "FREE"
                    
                    tasks.append(process_cl_listing(session, href, city, cat_name, title, price, counter, semaphore))
                
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                    
        except Exception as e:
            log.debug(f"CL city error {city}/{cat_name}: {e}")
        await asyncio.sleep(0.02)


async def scan_craigslist_parallel(session):
    """Scan all CL cities in parallel with individual page fetching."""
    categories = [("free", "zip"), ("cars", "cta"), ("boats", "boo")]
    counter = {"found": 0, "new": 0}
    semaphore = asyncio.Semaphore(PAGE_FETCH_WORKERS)
    
    tasks = [scan_cl_city(session, city, slug, categories, counter, semaphore) 
             for city, slug in CL_CITIES.items()]
    
    for i in range(0, len(tasks), PARALLEL_WORKERS):
        batch = tasks[i:i + PARALLEL_WORKERS]
        await asyncio.gather(*batch, return_exceptions=True)
    
    log.info(f"CL scan: {counter['found']} found, {counter['new']} new (with timestamps)")


# ─── OFFERUP SCANNER WITH INDIVIDUAL PAGE FETCH ───
async def process_ou_listing(session, listing_data, loc, zipcode, cat_name, counter, semaphore):
    """Process individual OU listing - fetch page for timestamp."""
    async with semaphore:
        try:
            lid_raw = str(listing_data.get("listingId", ""))
            title = listing_data.get("title", "")
            if not lid_raw or not title:
                return
            
            lid = f"ou_{lid_raw}"
            if is_seen(lid):
                return
            
            # Fetch individual page for timestamp
            timestamp = await fetch_ou_listing_details(session, lid_raw)
            
            # Skip if too old
            if timestamp:
                age_minutes = (datetime.now(timezone.utc) - timestamp).total_seconds() / 60
                if age_minutes > MAX_AGE_MINUTES:
                    mark_seen(lid)
                    return
            
            img = listing_data.get("image", {})
            img_url = img.get("url", "") if isinstance(img, dict) else (img if isinstance(img, str) else "")
            
            raw_price = listing_data.get("price", 0)
            try:
                price_val = float(raw_price)
                price_str = "FREE" if price_val == 0 else f"${int(price_val)}"
            except:
                price_str = "FREE"
            
            mileage = ""
            if cat_name in ["cars", "boats"]:
                vm = listing_data.get("vehicleMiles")
                mileage = f"{vm} mi" if vm else get_mileage(title)
            
            loc_name = listing_data.get("locationName", loc)
            
            counter["new"] += 1
            await alert_queue.put({
                "id": lid, "source": "OU", "title": title,
                "link": f"https://offerup.com/item/detail/{lid_raw}",
                "price": price_str, "location": f"{loc_name} ({zipcode})",
                "category": cat_name, "mileage": mileage,
                "time": timestamp, "image": img_url
            })
        except Exception as e:
            log.debug(f"OU listing error: {e}")


async def fetch_ou_search(session, url):
    """Fetch OfferUp search page."""
    try:
        proxy = get_proxy()
        proxy_kwargs = {"proxy": proxy} if proxy else {}
        
        async with session.get(url, headers={"User-Agent": UA}, **proxy_kwargs,
                              timeout=aiohttp.ClientTimeout(total=12)) as resp:
            if resp.status == 200:
                if proxy:
                    mark_proxy_success(proxy)
                return await resp.text()
            elif resp.status in [403, 407, 429] and proxy:
                mark_proxy_failed(proxy)
        
        # Retry without proxy
        if PROXY_RETRY_WITHOUT and proxy:
            async with session.get(url, headers={"User-Agent": UA},
                                  timeout=aiohttp.ClientTimeout(total=12)) as resp:
                if resp.status == 200:
                    return await resp.text()
    except Exception as e:
        log.debug(f"OU fetch error: {e}")
    return None


async def scan_ou_location(session, loc, lat, lon, zipcode, categories, counter, semaphore):
    """Scan a single OU location."""
    for cat_name, cat_param, query in categories:
        try:
            if query:
                url = f"https://offerup.com/search?q={query}&lat={lat}&lon={lon}&radius=50&{cat_param}"
            else:
                url = f"https://offerup.com/search?q=&lat={lat}&lon={lon}&radius=50&{cat_param}"
            
            html = await fetch_ou_search(session, url)
            if not html:
                continue
            
            match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
            if not match:
                continue
            
            data = json.loads(match.group(1))
            tiles = (data.get("props", {}).get("pageProps", {})
                        .get("searchFeedResponse", {}).get("looseTiles", []))
            
            if not tiles:
                continue
            
            tasks = []
            for tile in tiles[:10]:
                listing = tile.get("listing")
                if listing:
                    counter["found"] += 1
                    tasks.append(process_ou_listing(session, listing, loc, zipcode, cat_name, counter, semaphore))
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                
        except Exception as e:
            log.debug(f"OU location error {loc}/{cat_name}: {e}")
        await asyncio.sleep(0.02)


async def scan_offerup_parallel(session):
    """Scan all OU locations in parallel with individual page fetching."""
    categories = [("free", "price_max=0", ""), ("cars", "CATEGORY_ID=5", ""), ("boats", "CATEGORY_ID=5", "boat")]
    counter = {"found": 0, "new": 0}
    semaphore = asyncio.Semaphore(PAGE_FETCH_WORKERS)
    
    tasks = [scan_ou_location(session, loc, lat, lon, zipcode, categories, counter, semaphore)
             for loc, (lat, lon, zipcode) in OU_LOCS.items()]
    
    for i in range(0, len(tasks), PARALLEL_WORKERS):
        batch = tasks[i:i + PARALLEL_WORKERS]
        await asyncio.gather(*batch, return_exceptions=True)
    
    log.info(f"OU scan: {counter['found']} found, {counter['new']} new (with timestamps)")


# ─── MAIN SCAN ───
async def do_scan(bot):
    """Main scan function."""
    global consecutive_errors
    
    log.info(f"{'='*60}")
    log.info(f"SCAN START — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    log.info(f"Seen IDs: {len(seen)} | Workers: {PARALLEL_WORKERS} | Page fetch: {PAGE_FETCH_WORKERS}")
    log.info(f"{'='*60}")

    counter = {"sent": 0}
    connector = aiohttp.TCPConnector(force_close=True, limit=100)
    
    try:
        async with aiohttp.ClientSession(connector=connector) as session:
            await refresh_proxy_list(session)
            
            consumer_task = asyncio.create_task(alert_sender(bot, session, counter))
            
            await asyncio.gather(
                scan_craigslist_parallel(session),
                scan_offerup_parallel(session),
            )
            
            await alert_queue.join()
            await alert_queue.put(None)
            await consumer_task
            
            log.info(f"{'='*60}")
            log.info(f"SCAN COMPLETE — Sent {counter['sent']} alerts")
            log.info(f"{'='*60}")
            
            save_seen()
            stats["scans_completed"] += 1
            consecutive_errors = 0
            
            return counter["sent"]
    except Exception as e:
        log.error(f"Scan error: {e}")
        consecutive_errors += 1
        stats["errors"] += 1
        return 0


# ─── TELEGRAM COMMANDS ───
async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global scan_running
    if scan_running:
        await update.message.reply_text("⏳ Scan already running...")
        return
    
    scan_running = True
    msg = await update.message.reply_text(
        "🔍 *SCANNING WITH TIMESTAMPS...*\n\n"
        f"📋 {len(CL_CITIES)} CL cities\n"
        f"🟠 {len(OU_LOCS)} OU locations\n"
        f"⚡ {PARALLEL_WORKERS} workers\n"
        f"📄 Fetching individual pages for real timestamps",
        parse_mode="Markdown"
    )
    
    start = datetime.now(timezone.utc)
    total = await do_scan(context.bot)
    scan_running = False
    elapsed = int((datetime.now(timezone.utc) - start).total_seconds())
    
    await msg.edit_text(
        f"✅ *SCAN COMPLETE*\n\n"
        f"📤 Sent: {total} alerts\n"
        f"⏱️ Time: {elapsed}s\n"
        f"📂 Tracking: {len(seen)} IDs",
        parse_mode="Markdown"
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *24/7 LISTING SCANNER*\n\n"
        "/scan - Manual scan\n"
        "/status - Bot status\n"
        "/stats - Statistics\n"
        "/clear - Clear seen IDs\n\n"
        f"🔄 Auto-scan: every {SCAN_INTERVAL}s\n"
        f"⏰ Max age: {MAX_AGE_MINUTES}m\n"
        f"📄 Individual page timestamps: ON",
        parse_mode="Markdown"
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uptime_start = datetime.fromisoformat(stats["uptime_start"])
    uptime = datetime.now(timezone.utc) - uptime_start
    uptime_str = f"{uptime.days}d {uptime.seconds // 3600}h {(uptime.seconds // 60) % 60}m"
    
    await update.message.reply_text(
        f"📊 *STATUS*\n\n"
        f"✅ Running 24/7\n"
        f"⏱️ Uptime: {uptime_str}\n"
        f"📂 Seen IDs: {len(seen)}\n"
        f"🔄 Interval: {SCAN_INTERVAL}s\n"
        f"🔌 Proxies: {len(working_proxies)} working",
        parse_mode="Markdown"
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cl_count = sum(1 for lid in seen if lid.startswith("cl_"))
    ou_count = sum(1 for lid in seen if lid.startswith("ou_"))
    
    await update.message.reply_text(
        f"📈 *STATISTICS*\n\n"
        f"🔄 Scans completed: {stats['scans_completed']}\n"
        f"📤 Alerts sent: {stats['alerts_sent']}\n"
        f"❌ Errors: {stats['errors']}\n"
        f"📂 Tracked: {len(seen)} ({cl_count} CL, {ou_count} OU)",
        parse_mode="Markdown"
    )


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global seen
    old_count = len(seen)
    seen = {}
    save_seen()
    await update.message.reply_text(f"🧹 Cleared {old_count} seen IDs.")


# ─── 24/7 AUTO SCANNER ───
async def auto_scanner(bot):
    """Continuous 24/7 scanning loop with error recovery."""
    global scan_running, consecutive_errors
    
    log.info(f"🚀 24/7 Auto-scanner started: scanning every {SCAN_INTERVAL}s")
    
    while not shutdown_event.is_set():
        if not scan_running:
            scan_running = True
            
            try:
                await do_scan(bot)
            except Exception as e:
                log.error(f"Auto-scan error: {e}")
                consecutive_errors += 1
                stats["errors"] += 1
            finally:
                scan_running = False
            
            # Error recovery
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                log.warning(f"⚠️ {consecutive_errors} consecutive errors. Cooling down for {ERROR_COOLDOWN_SECONDS}s...")
                await asyncio.sleep(ERROR_COOLDOWN_SECONDS)
                consecutive_errors = 0
            
            cleanup_seen()
        
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=SCAN_INTERVAL)
            break
        except asyncio.TimeoutError:
            pass
    
    log.info("Auto-scanner stopped")


# ─── HEALTH CHECK ───
async def health_checker(bot):
    """Periodic health check."""
    while not shutdown_event.is_set():
        try:
            await asyncio.sleep(HEALTH_CHECK_INTERVAL)
            uptime_start = datetime.fromisoformat(stats["uptime_start"])
            uptime = datetime.now(timezone.utc) - uptime_start
            log.info(f"💚 Health OK | Uptime: {uptime.days}d {uptime.seconds // 3600}h | "
                    f"Scans: {stats['scans_completed']} | Alerts: {stats['alerts_sent']}")
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error(f"Health check error: {e}")


# ─── HEALTH ENDPOINT ───
async def health(request):
    if shutdown_event.is_set():
        return web.Response(text="SHUTTING DOWN", status=503)
    return web.Response(text=json.dumps({
        "status": "OK",
        "uptime_start": stats["uptime_start"],
        "scans_completed": stats["scans_completed"],
        "alerts_sent": stats["alerts_sent"],
        "seen_ids": len(seen)
    }), content_type="application/json")


# ─── GRACEFUL SHUTDOWN ───
def handle_signal(sig):
    log.info(f"Received {sig.name} — shutting down gracefully")
    shutdown_event.set()


# ─── MAIN ───
async def main():
    loop = asyncio.get_running_loop()
    
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_signal, sig)
    
    # Health server
    app_web = web.Application()
    app_web.router.add_get("/", health)
    runner = web.AppRunner(app_web)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    await web.TCPSite(runner, "0.0.0.0", port).start()
    log.info(f"Health server on port {port}")
    
    # Telegram bot
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("scan", scan_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("clear", clear_command))
    
    await app.initialize()
    await app.bot.delete_webhook(drop_pending_updates=True)
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    
    log.info("✅ Bot ready - 24/7 mode")
    
    await app.bot.send_message(
        CHAT_ID,
        f"🚀 *24/7 BOT STARTED*\n\n"
        f"🔄 Scanning every {SCAN_INTERVAL}s\n"
        f"⏰ Max listing age: {MAX_AGE_MINUTES}m\n"
        f"📄 Individual page timestamps: ON\n"
        f"📦 FREE • CARS • BOATS\n"
        f"📂 Tracking {len(seen)} IDs",
        parse_mode="Markdown"
    )
    
    # Start background tasks
    scanner_task = asyncio.create_task(auto_scanner(app.bot))
    health_task = asyncio.create_task(health_checker(app.bot))
    
    await shutdown_event.wait()
    
    # Cleanup
    log.info("Stopping...")
    scanner_task.cancel()
    health_task.cancel()
    
    try:
        await scanner_task
    except asyncio.CancelledError:
        pass
    
    try:
        await health_task
    except asyncio.CancelledError:
        pass
    
    await app.updater.stop()
    await app.stop()
    await app.shutdown()
    await runner.cleanup()
    save_seen()
    
    log.info("Clean exit.")


if __name__ == "__main__":
    asyncio.run(main())
