import asyncio
import os
import re
import random
import json
import logging
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
DB_FILE = "seen_ids.json"  # Changed to JSON for time-based tracking

# ─── TIMING ───
MAX_AGE_MINUTES = 40       # Only alert listings within 40 minutes (when timestamp available)
SCAN_INTERVAL = 30         # Scan every 30 seconds
SEEN_EXPIRY_HOURS = 6      # Expire seen IDs after 6 hours (allows re-alerting old listings)
PARALLEL_WORKERS = 10      # Number of parallel scan workers

# ─── PROXY LIST ───
# Hardcoded reliable proxies + dynamic fetch as backup
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
    "http://104.168.158.236:10818",
    "http://167.71.60.190:8080",
    "http://35.225.22.61:80",
    "http://51.141.175.118:80",
    "http://47.89.184.18:3129",
    "http://4.213.167.178:80",
    "http://150.136.153.231:80",
    "http://74.176.195.135:80",
    "http://142.93.202.130:3129",
    "http://34.44.49.215:80",
    "http://143.42.66.91:80",
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

# Working proxies (validated during runtime)
working_proxies = list(PROXY_LIST)
failed_proxies = set()

def get_proxy():
    """Get a random working proxy with rotation."""
    if working_proxies:
        return random.choice(working_proxies)
    # Reset if all failed
    if not working_proxies and failed_proxies:
        working_proxies.extend(PROXY_LIST)
        failed_proxies.clear()
    return random.choice(PROXY_LIST) if PROXY_LIST else None

def mark_proxy_failed(proxy):
    """Mark a proxy as failed."""
    if proxy in working_proxies:
        working_proxies.remove(proxy)
        failed_proxies.add(proxy)

def mark_proxy_success(proxy):
    """Mark a proxy as working."""
    if proxy in failed_proxies:
        failed_proxies.remove(proxy)
        if proxy not in working_proxies:
            working_proxies.append(proxy)

async def refresh_proxy_list(session):
    """Fetch fresh proxies from ProxyScrape API to supplement list."""
    global working_proxies
    try:
        url = "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=5000&country=us&ssl=all&anonymity=elite"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                text = await resp.text()
                new_proxies = [f"http://{p.strip()}" for p in text.strip().split('\n') if p.strip()]
                # Add new unique proxies
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

# ─── TIME-BASED SEEN IDs ───
seen = {}  # {listing_id: timestamp_string}

def load_seen():
    """Load seen IDs with timestamps, expire old ones."""
    global seen
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                data = json.load(f)
                now = datetime.now(timezone.utc)
                expiry = timedelta(hours=SEEN_EXPIRY_HOURS)
                # Filter out expired entries
                seen = {}
                expired_count = 0
                for lid, ts_str in data.items():
                    try:
                        ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                        if now - ts < expiry:
                            seen[lid] = ts_str
                        else:
                            expired_count += 1
                    except:
                        pass
                if expired_count > 0:
                    log.info(f"Expired {expired_count} old seen IDs (>{SEEN_EXPIRY_HOURS}h)")
        except json.JSONDecodeError:
            log.warning("Could not parse seen_ids.json, starting fresh")
            seen = {}
    log.info(f"Loaded {len(seen)} active seen IDs")

def save_seen():
    """Save seen IDs to disk."""
    with open(DB_FILE, 'w') as f:
        json.dump(seen, f)

def mark_seen(lid):
    """Mark a listing as seen with current timestamp."""
    seen[lid] = datetime.now(timezone.utc).isoformat()
    # Save periodically (every 50 new entries)
    if len(seen) % 50 == 0:
        save_seen()

def is_seen(lid):
    """Check if listing was seen recently (within expiry window)."""
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
    """Remove expired entries and save."""
    global seen
    now = datetime.now(timezone.utc)
    expiry = timedelta(hours=SEEN_EXPIRY_HOURS)
    old_count = len(seen)
    seen = {lid: ts for lid, ts in seen.items() 
            if datetime.now(timezone.utc) - datetime.fromisoformat(ts.replace('Z', '+00:00')) < expiry}
    if old_count != len(seen):
        log.info(f"Cleanup: {old_count} -> {len(seen)} seen IDs")
    save_seen()

# Load on startup
load_seen()

# ─── SCAN FLAG ───
scan_running = False

# ─── HELPERS ───
async def fetch_cl_image(session, url):
    """Fetch og:image from a Craigslist listing page."""
    try:
        async with session.get(url, headers={"User-Agent": UA}, timeout=aiohttp.ClientTimeout(total=4)) as resp:
            if resp.status == 200:
                html = await resp.text()
                match = re.search(r'<meta property="og:image" content="([^"]+)"', html)
                if match:
                    return match.group(1)
    except Exception as e:
        log.debug(f"Failed to fetch CL image: {e}")
    return ""

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


async def send_alert(bot, session, listing):
    """Send a single Telegram alert with image."""
    parts = []
    if listing.get("price") and listing["price"] not in ["FREE", "$0", ""]:
        parts.append(f"💰 {listing['price']}")
    if listing.get("mileage"):
        parts.append(f"🛣️ {listing['mileage']}")
    parts.append(f"🏙️ {listing['location']}")

    # Category emoji
    cat = listing.get("category", "")
    if cat == "free":
        parts.append("🆓 FREE")
    elif cat == "cars":
        parts.append("🚗 CARS")
    elif cat == "boats":
        parts.append("🚤 BOATS")

    # Time since posted
    if listing.get("time"):
        age_seconds = (datetime.now(timezone.utc) - listing["time"]).total_seconds()
        mins = max(0, int(age_seconds / 60))
        if mins < 1:
            parts.append("⏰ Just now")
        else:
            parts.append(f"⏰ {mins}m ago")
    else:
        parts.append("⏰ NEW")

    safe_title = re.sub(r'[*_`\[\]]', '', str(listing.get("title", "")))[:80].upper()
    caption = f"🔔 *{listing['source']}* | {safe_title}\n{' • '.join(parts)}"
    kb = [[InlineKeyboardButton(text="🔗 VIEW LISTING", url=listing["link"])]]

    img = listing.get("image", "")
    if img:
        try:
            if "craigslist" in img:
                async with session.get(img, headers={"User-Agent": UA}, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                    if resp.status == 200:
                        await bot.send_photo(
                            chat_id=CHAT_ID, photo=await resp.read(),
                            caption=caption, parse_mode="Markdown",
                            reply_markup=InlineKeyboardMarkup(kb)
                        )
                        log.info(f"✅ SENT: {listing['source']} - {safe_title[:30]}... ({'FREE' if is_free else listing.get('price', 'N/A')})")
                        return True
            else:
                await bot.send_photo(
                    chat_id=CHAT_ID, photo=img,
                    caption=caption, parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(kb)
                )
                log.info(f"✅ SENT: {listing['source']} - {safe_title[:30]}... ({'FREE' if is_free else listing.get('price', 'N/A')})")
                return True
        except Exception as e:
            log.debug(f"Image send failed, falling back to text: {e}")

    try:
        await bot.send_message(
            chat_id=CHAT_ID, text=caption, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb),
            disable_web_page_preview=True
        )
        log.info(f"✅ SENT (text): {listing['source']} - {safe_title[:30]}... ({'FREE' if is_free else listing.get('price', 'N/A')})")
        return True
    except Exception as e:
        log.error(f"❌ Alert send FAILED: {e}")
        return False


# ─── ALERT QUEUE (real-time sending) ───
alert_queue = asyncio.Queue()

async def alert_sender(bot, session, counter):
    """Drains the alert queue and sends each listing."""
    while True:
        listing = None
        try:
            listing = await alert_queue.get()
            
            if listing is None:  # poison pill = scan done
                break
            if is_seen(listing["id"]):
                continue

            # ─── AGE FILTER: if timestamp available, skip old listings ───
            if listing.get("time"):
                age_minutes = (datetime.now(timezone.utc) - listing["time"]).total_seconds() / 60
                if age_minutes > MAX_AGE_MINUTES:
                    mark_seen(listing["id"])
                    continue

            # Fetch CL image just-in-time
            if listing["source"] == "CL" and not listing.get("image"):
                listing["image"] = await fetch_cl_image(session, listing["link"])

            if await send_alert(bot, session, listing):
                counter["sent"] += 1
                mark_seen(listing["id"])

            await asyncio.sleep(0.03)

        except Exception as e:
            log.error(f"alert_sender error: {e}", exc_info=True)
        finally:
            if listing is not None:
                try:
                    alert_queue.task_done()
                except ValueError:
                    pass


# ─── CRAIGSLIST SCANNER (PARALLEL) ───
async def scan_cl_city(session, city, slug, categories, counter):
    """Scan a single CL city across all categories."""
    for cat_name, cat_code in categories:
        try:
            url = f"https://{slug}.craigslist.org/search/{cat_code}?sort=date"
            
            async with session.get(
                url, headers={"User-Agent": UA},
                timeout=aiohttp.ClientTimeout(total=8)
            ) as resp:
                if resp.status != 200:
                    continue
                html = await resp.text()
                soup = BeautifulSoup(html, "html.parser")

                results = soup.select(".cl-static-search-result")[:15]
                counter["found"] += len(results)

                for r in results:
                    link_tag = r.select_one("a")
                    if not link_tag:
                        continue
                    href = link_tag.get("href", "")
                    if not href:
                        continue

                    id_match = re.search(r'/(\d+)\.html', href)
                    lid = f"cl_{id_match.group(1)}" if id_match else f"cl_{hash(href)}"

                    if is_seen(lid):
                        continue

                    title_el = r.select_one(".title")
                    title = title_el.get_text(strip=True) if title_el else "Item"

                    price_el = r.select_one(".price")
                    price = price_el.get_text(strip=True) if price_el else "FREE"

                    mileage = get_mileage(title) if cat_name in ["cars", "boats"] else ""

                    counter["new"] += 1
                    await alert_queue.put({
                        "id": lid, "source": "CL", "title": title, "link": href,
                        "price": price, "location": city, "category": cat_name,
                        "mileage": mileage, "time": None, "image": ""
                    })

        except Exception as e:
            log.debug(f"CL error {city}/{cat_name}: {e}")
        await asyncio.sleep(0.05)  # Small delay between categories


async def scan_craigslist_parallel(session):
    """Scan all CL cities in PARALLEL."""
    categories = [
        ("free", "zip"),
        ("cars", "cta"),
        ("boats", "boo"),
    ]
    
    counter = {"found": 0, "new": 0}
    
    # Create tasks for all cities
    tasks = [
        scan_cl_city(session, city, slug, categories, counter)
        for city, slug in CL_CITIES.items()
    ]
    
    # Run in batches to avoid overwhelming
    batch_size = PARALLEL_WORKERS
    for i in range(0, len(tasks), batch_size):
        batch = tasks[i:i + batch_size]
        await asyncio.gather(*batch, return_exceptions=True)
    
    log.info(f"CL parallel scan: {counter['found']} found, {counter['new']} new")


# ─── OFFERUP SCANNER (PARALLEL) ───
async def scan_ou_location(session, loc, lat, lon, zipcode, categories, counter):
    """Scan a single OU location across all categories."""
    for cat_name, cat_param, query in categories:
        try:
            if query:
                url = f"https://offerup.com/search?q={query}&lat={lat}&lon={lon}&radius=50&{cat_param}"
            else:
                url = f"https://offerup.com/search?q=&lat={lat}&lon={lon}&radius=50&{cat_param}"

            proxy = get_proxy()
            proxy_kwargs = {"proxy": proxy} if proxy else {}
            
            async with session.get(
                url, headers={"User-Agent": UA},
                **proxy_kwargs,
                timeout=aiohttp.ClientTimeout(total=12)
            ) as resp:
                if resp.status != 200:
                    if resp.status in [403, 407, 429] and proxy:
                        mark_proxy_failed(proxy)
                    continue
                
                # Proxy worked
                if proxy:
                    mark_proxy_success(proxy)
                    
                html = await resp.text()

                match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
                if not match:
                    continue

                data = json.loads(match.group(1))

                tiles = (data.get("props", {})
                             .get("pageProps", {})
                             .get("searchFeedResponse", {})
                             .get("looseTiles", []))

                if not tiles:
                    continue

                count = 0
                for tile in tiles:
                    if count >= 15:
                        break

                    listing = tile.get("listing")
                    if not listing:
                        continue

                    lid_raw = str(listing.get("listingId", ""))
                    title = listing.get("title", "")
                    if not lid_raw or not title:
                        continue

                    lid = f"ou_{lid_raw}"
                    if is_seen(lid):
                        continue

                    counter["found"] += 1

                    img = listing.get("image", {})
                    if isinstance(img, dict):
                        img_url = img.get("url", "")
                    elif isinstance(img, str):
                        img_url = img
                    else:
                        img_url = ""

                    raw_price = listing.get("price", 0)
                    try:
                        price_val = float(raw_price)
                        price_str = "FREE" if price_val == 0 else f"${int(price_val)}"
                    except (ValueError, TypeError):
                        price_str = "FREE"

                    mileage = ""
                    if cat_name in ["cars", "boats"]:
                        vm = listing.get("vehicleMiles")
                        if vm:
                            mileage = f"{vm} mi"
                        else:
                            mileage = get_mileage(title)

                    loc_name = listing.get("locationName", loc)

                    counter["new"] += 1
                    await alert_queue.put({
                        "id": lid, "source": "OU", "title": title,
                        "link": f"https://offerup.com/item/detail/{lid_raw}",
                        "price": price_str, "location": f"{loc_name} ({zipcode})",
                        "category": cat_name, "mileage": mileage,
                        "time": None, "image": img_url
                    })
                    count += 1

        except json.JSONDecodeError:
            pass
        except Exception as e:
            log.debug(f"OU error {loc}/{cat_name}: {e}")
        await asyncio.sleep(0.05)


async def scan_offerup_parallel(session):
    """Scan all OU locations in PARALLEL with proxy rotation."""
    categories = [
        ("free", "price_max=0", ""),
        ("cars", "CATEGORY_ID=5", ""),
        ("boats", "CATEGORY_ID=5", "boat"),
    ]
    
    counter = {"found": 0, "new": 0}
    
    # Create tasks for all locations
    tasks = [
        scan_ou_location(session, loc, lat, lon, zipcode, categories, counter)
        for loc, (lat, lon, zipcode) in OU_LOCS.items()
    ]
    
    # Run in batches
    batch_size = PARALLEL_WORKERS
    for i in range(0, len(tasks), batch_size):
        batch = tasks[i:i + batch_size]
        await asyncio.gather(*batch, return_exceptions=True)
    
    log.info(f"OU parallel scan: {counter['found']} found, {counter['new']} new (proxies: {len(working_proxies)} working)")


# ─── DO SCAN ───
async def do_scan(bot):
    """
    Main scan — runs CL and OU in PARALLEL, sends alerts in REAL TIME.
    Uses parallel workers for maximum speed.
    """
    log.info(f"{'='*50}")
    log.info(f"SCAN START — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    log.info(f"Active seen IDs: {len(seen)} | Workers: {PARALLEL_WORKERS}")
    log.info(f"{'='*50}")

    counter = {"sent": 0}
    connector = aiohttp.TCPConnector(force_close=True, limit=50)  # Higher limit for parallel
    async with aiohttp.ClientSession(connector=connector) as session:
        # Refresh proxy list
        await refresh_proxy_list(session)
        log.info(f"Proxies ready: {len(working_proxies)} working")

        # Start alert sender in background
        consumer_task = asyncio.create_task(alert_sender(bot, session, counter))

        # Run BOTH scanners in parallel
        await asyncio.gather(
            scan_craigslist_parallel(session),
            scan_offerup_parallel(session),
        )

        # Wait for queue to drain
        await alert_queue.join()
        await alert_queue.put(None)  # poison pill
        await consumer_task

        log.info(f"{'='*50}")
        log.info(f"SCAN COMPLETE — Sent {counter['sent']} alerts")
        log.info(f"{'='*50}")
        
        # Save seen IDs
        save_seen()
        
        return counter["sent"]


# ─── /scan COMMAND ───
async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global scan_running

    if scan_running:
        await update.message.reply_text("⏳ Scan already running...")
        return

    scan_running = True

    msg = await update.message.reply_text(
        "🔍 *PARALLEL SCANNING...*\n\n"
        f"📋 {len(CL_CITIES)} CL cities\n"
        f"🟠 {len(OU_LOCS)} OU locations\n"
        f"⚡ {PARALLEL_WORKERS} workers\n"
        "📦 FREE • CARS • BOATS",
        parse_mode="Markdown"
    )

    start = datetime.now(timezone.utc)
    total = 0
    try:
        total = await do_scan(context.bot)
    except Exception as e:
        log.error(f"scan_command error: {e}", exc_info=True)
    finally:
        scan_running = False

    elapsed = int((datetime.now(timezone.utc) - start).total_seconds())

    await msg.edit_text(
        f"✅ *SCAN COMPLETE*\n\n"
        f"📤 Sent: {total} alerts\n"
        f"⏱️ Time: {elapsed}s\n"
        f"📂 Tracking: {len(seen)} IDs",
        parse_mode="Markdown"
    )


# ─── /start COMMAND ───
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *LISTING SCANNER*\n\n"
        "/scan - Scan now\n"
        "/status - Status\n"
        "/clear - Clear seen IDs\n"
        "/stats - View statistics\n\n"
        f"🔄 Auto-scan: every {SCAN_INTERVAL}s\n"
        f"⏰ ID expiry: {SEEN_EXPIRY_HOURS}h",
        parse_mode="Markdown"
    )


# ─── /status COMMAND ───
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📊 *STATUS*\n\n"
        f"✅ Running\n"
        f"📂 Seen IDs: {len(seen)}\n"
        f"🔄 Interval: {SCAN_INTERVAL}s\n"
        f"⏰ ID Expiry: {SEEN_EXPIRY_HOURS}h",
        parse_mode="Markdown"
    )


# ─── /stats COMMAND ───
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Count recent seen IDs by source
    cl_count = sum(1 for lid in seen if lid.startswith("cl_"))
    ou_count = sum(1 for lid in seen if lid.startswith("ou_"))
    
    await update.message.reply_text(
        f"📈 *STATISTICS*\n\n"
        f"📂 Total tracked: {len(seen)}\n"
        f"🔵 Craigslist: {cl_count}\n"
        f"🟠 OfferUp: {ou_count}\n"
        f"⏰ Expiry: {SEEN_EXPIRY_HOURS}h",
        parse_mode="Markdown"
    )


# ─── /clear COMMAND (reset seen IDs) ───
async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global seen
    old_count = len(seen)
    seen = {}
    save_seen()
    await update.message.reply_text(
        f"🧹 Cleared {old_count} seen IDs.\n"
        "Next scan will treat everything as new.",
        parse_mode="Markdown"
    )


# ─── AUTO SCANNER ───
async def auto_scanner(bot):
    log.info(f"Auto-scanner started: every {SCAN_INTERVAL}s, IDs expire after {SEEN_EXPIRY_HOURS}h")

    while not shutdown_event.is_set():
        if not scan_running:
            start = datetime.now(timezone.utc)
            log.info(f"Auto-scan triggered at {start.strftime('%H:%M:%S')} UTC")

            try:
                total = await do_scan(bot)
                elapsed = int((datetime.now(timezone.utc) - start).total_seconds())
                log.info(f"Auto-scan complete: {total} alerts in {elapsed}s")
            except Exception as e:
                log.error(f"Auto-scan failed: {e}", exc_info=True)

            cleanup_seen()

        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=SCAN_INTERVAL)
            break
        except asyncio.TimeoutError:
            pass


# ─── SHUTDOWN EVENT ───
shutdown_event = asyncio.Event()

# ─── HEALTH ───
async def health(request):
    if shutdown_event.is_set():
        return web.Response(text="SHUTTING DOWN", status=503)
    return web.Response(text=json.dumps({
        "status": "OK",
        "seen_ids": len(seen),
        "scan_running": scan_running
    }), content_type="application/json")

# ─── GRACEFUL SHUTDOWN ───
def handle_signal(sig):
    log.info(f"Received {sig.name} — shutting down gracefully")
    shutdown_event.set()

# ─── MAIN ───
async def main():
    import signal as signal_mod

    loop = asyncio.get_running_loop()

    for sig in (signal_mod.SIGTERM, signal_mod.SIGINT):
        loop.add_signal_handler(sig, handle_signal, sig)

    app_web = web.Application()
    app_web.router.add_get("/", health)
    runner = web.AppRunner(app_web)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    await web.TCPSite(runner, "0.0.0.0", port).start()
    log.info(f"Health server on port {port}")

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

    log.info("Bot ready")

    await app.bot.send_message(
        CHAT_ID,
        f"🚀 *BOT STARTED*\n\n"
        f"🔄 Scanning every {SCAN_INTERVAL}s\n"
        f"📦 FREE • CARS • BOATS\n"
        f"⏰ IDs expire after {SEEN_EXPIRY_HOURS}h\n"
        f"📂 Tracking {len(seen)} IDs",
        parse_mode="Markdown"
    )

    scanner_task = asyncio.create_task(auto_scanner(app.bot))

    await shutdown_event.wait()

    log.info("Stopping auto-scanner...")
    scanner_task.cancel()
    try:
        await scanner_task
    except asyncio.CancelledError:
        pass

    log.info("Stopping Telegram polling...")
    try:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
    except Exception as e:
        log.warning(f"Bot shutdown error (non-fatal): {e}")

    log.info("Stopping health server...")
    await runner.cleanup()

    # Final save
    save_seen()
    log.info("Clean exit.")

if __name__ == "__main__":
    asyncio.run(main())
