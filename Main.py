import asyncio
import os
import re
import random
import json
import logging
from datetime import datetime, timezone
from bs4 import BeautifulSoup
import aiohttp
from aiohttp import web
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ─── LOGGING ───
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger("scanner")

# ─── CONFIG ───
TOKEN = os.environ.get("TELEGRAM_TOKEN", "8712723612:AAFMSfy8dOyEpOoE-vQXAaMM2oIKVs7zsNA")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "6549307194")
DB_FILE = "seen_ids.txt"

# ─── TIMING ───
MAX_AGE_MINUTES = 40   # Only alert listings within 40 minutes (when timestamp available)
SCAN_INTERVAL = 30     # Scan every 30 seconds

# ─── PROXY ───
PROXY_PASSWORD = "tde8ndie2iu8"
PROXY_USERS = ["oyexvpgk-us-1", "oyexvpgk-us-5", "oyexvpgk-us-10", "oyexvpgk-us-15", "oyexvpgk-us-20"]

def get_proxy():
    return f"http://{random.choice(PROXY_USERS)}:{PROXY_PASSWORD}@p.webshare.io:80"

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

# ─── SEEN IDs ───
seen = set()
if os.path.exists(DB_FILE):
    with open(DB_FILE) as f:
        seen = set(line.strip() for line in f if line.strip())
log.info(f"Loaded {len(seen)} seen IDs")

def mark_seen(lid):
    seen.add(lid)
    with open(DB_FILE, "a") as f:
        f.write(f"{lid}\n")

def cleanup_seen():
    global seen
    if len(seen) > 20000:
        seen = set(list(seen)[-10000:])
        with open(DB_FILE, "w") as f:
            f.write("\n".join(seen))

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
    except Exception:
        pass
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
        parts.append(f"\U0001f4b0 {listing['price']}")
    if listing.get("mileage"):
        parts.append(f"\U0001f6e3\ufe0f {listing['mileage']}")
    parts.append(f"\U0001f3d9\ufe0f {listing['location']}")

    # Category emoji
    cat = listing.get("category", "")
    if cat == "free":
        parts.append("\U0001f193 FREE")
    elif cat == "cars":
        parts.append("\U0001f697 CARS")
    elif cat == "boats":
        parts.append("\U0001f6a4 BOATS")

    # Time since posted
    if listing.get("time"):
        age_seconds = (datetime.now(timezone.utc) - listing["time"]).total_seconds()
        mins = max(0, int(age_seconds / 60))
        if mins < 1:
            parts.append("\u23f0 Just now")
        else:
            parts.append(f"\u23f0 {mins}m ago")
    else:
        parts.append("\u23f0 NEW")

    safe_title = re.sub(r'[*_`\[\]]', '', str(listing.get("title", "")))[:80].upper()
    caption = f"\U0001f514 *{listing['source']}* | {safe_title}\n{' \u2022 '.join(parts)}"
    kb = [[InlineKeyboardButton(text="\U0001f517 VIEW LISTING", url=listing["link"])]]

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
                        return True
            else:
                await bot.send_photo(
                    chat_id=CHAT_ID, photo=img,
                    caption=caption, parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(kb)
                )
                return True
        except Exception as e:
            log.debug(f"Image send failed, falling back to text: {e}")

    try:
        await bot.send_message(
            chat_id=CHAT_ID, text=caption, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb),
            disable_web_page_preview=True
        )
        return True
    except Exception as e:
        log.error(f"Alert send FAILED: {e}")
        return False


# ─── ALERT QUEUE (real-time sending) ───
alert_queue = asyncio.Queue()

async def alert_sender(bot, session, counter):
    """Drains the alert queue and sends each listing. Robust error handling."""
    while True:
        listing = None
        try:
            listing = await alert_queue.get()
            if listing is None:  # poison pill = scan done
                break
            if listing["id"] in seen:
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
                    pass  # already done


# ─── CRAIGSLIST SCANNER ───
async def scan_craigslist_stream(session):
    """
    Scan all CL cities. Uses ?sort=date so newest listings come first.
    Craigslist static results do NOT include timestamps, so we only take
    the first 15 per category (newest by sort order). Dedup via seen IDs
    ensures we only alert genuinely new listings.
    """
    categories = [
        ("free", "zip"),
        ("cars", "cta"),
        ("boats", "boo"),
    ]
    for city, slug in CL_CITIES.items():
        for cat_name, cat_code in categories:
            try:
                # sort=date ensures newest listings first
                url = f"https://{slug}.craigslist.org/search/{cat_code}?sort=date"
                async with session.get(
                    url, headers={"User-Agent": UA},
                    timeout=aiohttp.ClientTimeout(total=8)
                ) as resp:
                    if resp.status != 200:
                        log.warning(f"CL {city}/{cat_name} HTTP {resp.status}")
                        continue
                    html = await resp.text()
                    soup = BeautifulSoup(html, "html.parser")

                    results = soup.select(".cl-static-search-result")[:15]

                    for r in results:
                        link_tag = r.select_one("a")
                        if not link_tag:
                            continue
                        href = link_tag.get("href", "")
                        if not href:
                            continue

                        # Extract listing ID from URL
                        id_match = re.search(r'/(\d+)\.html', href)
                        lid = f"cl_{id_match.group(1)}" if id_match else f"cl_{hash(href)}"

                        if lid in seen:
                            continue

                        title_el = r.select_one(".title")
                        title = title_el.get_text(strip=True) if title_el else "Item"

                        price_el = r.select_one(".price")
                        price = price_el.get_text(strip=True) if price_el else "FREE"

                        mileage = get_mileage(title) if cat_name in ["cars", "boats"] else ""

                        # CL static results have no <time> element — timestamp is None
                        # Dedup handles "newness"; sort=date ensures top = newest
                        await alert_queue.put({
                            "id": lid, "source": "CL", "title": title, "link": href,
                            "price": price, "location": city, "category": cat_name,
                            "mileage": mileage, "time": None, "image": ""
                        })

            except Exception as e:
                log.warning(f"CL error {city}/{cat_name}: {e}")
            await asyncio.sleep(0.15)


# ─── OFFERUP SCANNER ───
async def scan_offerup_stream(session):
    """
    Scan all OU locations via __NEXT_DATA__ JSON.
    OfferUp search tiles use 'looseTiles' with 'listing' sub-objects.
    Listing keys: listingId, title, price, image{url}, locationName.
    No createdDate in search results — dedup handles newness.
    """
    categories = [
        ("free", "price_max=0", ""),
        ("cars", "CATEGORY_ID=5", ""),
        ("boats", "CATEGORY_ID=5", "boat"),
    ]
    for loc, (lat, lon, zipcode) in OU_LOCS.items():
        for cat_name, cat_param, query in categories:
            try:
                if query:
                    url = f"https://offerup.com/search?q={query}&lat={lat}&lon={lon}&radius=50&{cat_param}"
                else:
                    url = f"https://offerup.com/search?q=&lat={lat}&lon={lon}&radius=50&{cat_param}"

                async with session.get(
                    url, headers={"User-Agent": UA},
                    proxy=get_proxy(),
                    timeout=aiohttp.ClientTimeout(total=12)
                ) as resp:
                    if resp.status != 200:
                        log.debug(f"OU {loc}/{cat_name} HTTP {resp.status}")
                        continue
                    html = await resp.text()

                    # Extract __NEXT_DATA__ JSON
                    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
                    if not match:
                        log.debug(f"OU {loc}/{cat_name}: no __NEXT_DATA__")
                        continue

                    data = json.loads(match.group(1))

                    # Navigate to tiles — path: props.pageProps.searchFeedResponse.looseTiles
                    tiles = (data.get("props", {})
                                 .get("pageProps", {})
                                 .get("searchFeedResponse", {})
                                 .get("looseTiles", []))

                    if not tiles:
                        log.debug(f"OU {loc}/{cat_name}: 0 tiles")
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
                        if lid in seen:
                            continue

                        # Image — nested dict with 'url' key
                        img = listing.get("image", {})
                        if isinstance(img, dict):
                            img_url = img.get("url", "")
                        elif isinstance(img, str):
                            img_url = img
                        else:
                            img_url = ""

                        # Price
                        raw_price = listing.get("price", 0)
                        try:
                            price_val = float(raw_price)
                            price_str = "FREE" if price_val == 0 else f"${int(price_val)}"
                        except (ValueError, TypeError):
                            price_str = "FREE"

                        mileage = ""
                        if cat_name in ["cars", "boats"]:
                            # vehicleMiles is available in some listings
                            vm = listing.get("vehicleMiles")
                            if vm:
                                mileage = f"{vm} mi"
                            else:
                                mileage = get_mileage(title)

                        loc_name = listing.get("locationName", loc)

                        await alert_queue.put({
                            "id": lid, "source": "OU", "title": title,
                            "link": f"https://offerup.com/item/detail/{lid_raw}",
                            "price": price_str, "location": f"{loc_name} ({zipcode})",
                            "category": cat_name, "mileage": mileage,
                            "time": None, "image": img_url
                        })
                        count += 1

            except json.JSONDecodeError as e:
                log.warning(f"OU JSON error {loc}/{cat_name}: {e}")
            except Exception as e:
                log.warning(f"OU error {loc}/{cat_name}: {e}")
            await asyncio.sleep(0.15)


# ─── DO SCAN ───
async def do_scan(bot):
    """
    Main scan — runs CL and OU in PARALLEL, sends alerts in REAL TIME.
    MAX_AGE_MINUTES filter applies when timestamps are available.
    For listings without timestamps (most), dedup via seen IDs prevents repeats.
    """
    log.info(f"Scan start — now(UTC)={datetime.now(timezone.utc).strftime('%H:%M:%S')}")

    counter = {"sent": 0}
    connector = aiohttp.TCPConnector(force_close=True, limit=20)
    async with aiohttp.ClientSession(connector=connector) as session:

        consumer_task = asyncio.create_task(alert_sender(bot, session, counter))

        await asyncio.gather(
            scan_craigslist_stream(session),
            scan_offerup_stream(session),
        )

        await alert_queue.join()
        await alert_queue.put(None)  # poison pill
        await consumer_task

        log.info(f"Scan complete — sent {counter['sent']} new alerts")
        return counter["sent"]


# ─── /scan COMMAND ───
async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global scan_running

    if scan_running:
        await update.message.reply_text("\u23f3 Scan already running...")
        return

    scan_running = True

    msg = await update.message.reply_text(
        "\U0001f50d *SCANNING...*\n\n"
        f"\U0001f4cb {len(CL_CITIES)} CL cities\n"
        f"\U0001f7e0 {len(OU_LOCS)} OU locations\n"
        "\U0001f4e6 FREE \u2022 CARS \u2022 BOATS",
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
        f"\u2705 *SCAN COMPLETE*\n\n"
        f"\U0001f4e4 Sent: {total} alerts\n"
        f"\u23f1\ufe0f Time: {elapsed}s",
        parse_mode="Markdown"
    )


# ─── /start COMMAND ───
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "\U0001f916 *LISTING SCANNER*\n\n"
        "/scan - Scan now\n"
        "/status - Status\n"
        "/clear - Clear seen IDs (fresh start)\n\n"
        f"\U0001f504 Auto-scan: every {SCAN_INTERVAL}s\n"
        "\U0001f501 Dedup via seen IDs",
        parse_mode="Markdown"
    )


# ─── /status COMMAND ───
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"\U0001f4ca *STATUS*\n\n"
        f"\u2705 Running\n"
        f"\U0001f4c2 Seen: {len(seen)}\n"
        f"\U0001f504 Interval: {SCAN_INTERVAL}s",
        parse_mode="Markdown"
    )


# ─── /clear COMMAND (reset seen IDs) ───
async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global seen
    old_count = len(seen)
    seen = set()
    with open(DB_FILE, "w") as f:
        f.write("")
    await update.message.reply_text(
        f"\U0001f9f9 Cleared {old_count} seen IDs.\n"
        "Next scan will treat everything as new.",
        parse_mode="Markdown"
    )


# ─── AUTO SCANNER ───
async def auto_scanner(bot):
    log.info(f"Auto-scanner: every {SCAN_INTERVAL}s, dedup via seen_ids")

    while not shutdown_event.is_set():
        if not scan_running:
            start = datetime.now(timezone.utc)
            log.info(f"Auto-scan at {start.strftime('%H:%M:%S')} UTC")

            try:
                total = await do_scan(bot)
                elapsed = int((datetime.now(timezone.utc) - start).total_seconds())
                log.info(f"Sent {total} alerts in {elapsed}s")
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
    return web.Response(text="OK")

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
    app.add_handler(CommandHandler("clear", clear_command))

    await app.initialize()
    await app.bot.delete_webhook(drop_pending_updates=True)
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)

    log.info("Bot ready")

    await app.bot.send_message(
        CHAT_ID,
        f"\U0001f680 *BOT STARTED*\n\n"
        f"\U0001f504 Scanning every {SCAN_INTERVAL}s\n"
        f"\U0001f4e6 FREE \u2022 CARS \u2022 BOATS\n"
        f"\U0001f501 Dedup via seen IDs ({len(seen)} tracked)",
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

    log.info("Clean exit.")

if __name__ == "__main__":
    asyncio.run(main())
