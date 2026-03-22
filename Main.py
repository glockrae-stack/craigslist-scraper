import asyncio
import os
import re
import random
import json
import logging
from datetime import datetime, timedelta, timezone
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
MAX_AGE_MINUTES = 40  # ONLY listings within 40 minutes
SCAN_INTERVAL = 30    # Scan every 30 seconds

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
print(f"📂 Loaded {len(seen)} seen IDs")

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
    try:
        async with session.get(url, headers={"User-Agent": UA}, timeout=aiohttp.ClientTimeout(total=4)) as resp:
            if resp.status == 200:
                html = await resp.text()
                match = re.search(r'<meta property="og:image" content="([^"]+)"', html)
                if match:
                    return match.group(1)
    except:
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
    """Send single alert with image"""
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
    
    # Time since posted (UTC-based)
    if listing.get("time"):
        age_seconds = (datetime.utcnow() - listing["time"]).total_seconds()
        mins = int(age_seconds / 60)
        if mins < 0:
            mins = 0  # clock skew guard
        if mins < 1:
            parts.append("⏰ Just now")
        else:
            parts.append(f"⏰ {mins}m ago")
    
    safe_title = re.sub(r'[*_`\[\]]', '', str(listing.get("title", "")))[:80].upper()
    caption = f"🔔 *{listing['source']}* | {safe_title}\n{' • '.join(parts)}"
    kb = [[InlineKeyboardButton(text="🔗 VIEW LISTING", url=listing["link"])]]
    
    img = listing.get("image", "")
    if img:
        try:
            if "craigslist" in img:
                async with session.get(img, headers={"User-Agent": UA}, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                    if resp.status == 200:
                        await bot.send_photo(chat_id=CHAT_ID, photo=await resp.read(), caption=caption, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
                        return True
            else:
                await bot.send_photo(chat_id=CHAT_ID, photo=img, caption=caption, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
                return True
        except Exception as e:
            log.debug(f"Image send failed, falling back to text: {e}")
    
    try:
        await bot.send_message(chat_id=CHAT_ID, text=caption, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
        return True
    except Exception as e:
        log.error(f"Alert send FAILED: {e}")
        return False

# ─── SCAN CRAIGSLIST ───
async def scan_craigslist(session, now, cutoff):
    """Scan all CL cities for FREE, CARS, BOATS"""
    listings = []
    
    categories = [
        ("free", "zip"),
        ("cars", "cta"),
        ("boats", "boo"),
    ]
    
    for city, slug in CL_CITIES.items():
        for cat_name, cat_code in categories:
            try:
                url = f"https://{slug}.craigslist.org/search/{cat_code}"
                async with session.get(url, headers={"User-Agent": UA}, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status != 200:
                        continue
                    
                    html = await resp.text()
                    soup = BeautifulSoup(html, "html.parser")
                    
                    for r in soup.select(".cl-static-search-result")[:15]:
                        link = r.select_one("a")
                        if not link:
                            continue
                        href = link.get("href", "")
                        
                        # Get listing ID
                        id_match = re.search(r'/(\d+)\.html', href)
                        lid = f"cl_{id_match.group(1) if id_match else hash(href)}"
                        
                        # Skip if already seen
                        if lid in seen:
                            continue
                        
                        # Get posting time (normalize to UTC)
                        post_time = None
                        time_elem = r.select_one("time")
                        if time_elem:
                            dt_str = time_elem.get("datetime", "")
                            if dt_str:
                                try:
                                    parsed = datetime.fromisoformat(dt_str)
                                    if parsed.tzinfo is not None:
                                        post_time = parsed.astimezone(timezone.utc).replace(tzinfo=None)
                                    else:
                                        # CL times without tz — assume UTC
                                        post_time = parsed
                                except Exception as e:
                                    log.warning(f"CL time parse error: {dt_str} -> {e}")
                        
                        # SKIP if no time or older than cutoff
                        if not post_time or post_time < cutoff:
                            continue
                        
                        title_el = r.select_one(".title")
                        title = title_el.get_text(strip=True) if title_el else "Item"
                        price_el = r.select_one(".price")
                        price = price_el.get_text(strip=True) if price_el else "FREE"
                        mileage = get_mileage(title) if cat_name in ["cars", "boats"] else ""
                        
                        listings.append({
                            "id": lid, "source": "CL", "title": title, "link": href,
                            "price": price, "location": city, "category": cat_name,
                            "mileage": mileage, "time": post_time, "image": ""
                        })
            except Exception as e:
                log.warning(f"CL error {city}/{cat_name}: {e}")
            await asyncio.sleep(0.15)
    
    return listings

# ─── SCAN OFFERUP ───
async def scan_offerup(session, now, cutoff):
    """Scan all OU locations for FREE, CARS, BOATS"""
    listings = []
    
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
                
                async with session.get(url, headers={"User-Agent": UA}, proxy=get_proxy(), timeout=aiohttp.ClientTimeout(total=12)) as resp:
                    if resp.status != 200:
                        continue
                    
                    html = await resp.text()
                    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
                    if not match:
                        continue
                    
                    data = json.loads(match.group(1))
                    tiles = data.get("props", {}).get("pageProps", {}).get("searchFeedResponse", {}).get("looseTiles", [])
                    
                    for tile in tiles[:15]:
                        listing = tile.get("listing", {})
                        if not listing:
                            continue
                        
                        lid_raw = listing.get("listingId", "")
                        lid = f"ou_{lid_raw}"
                        
                        if lid in seen:
                            continue
                        
                        title = listing.get("title", "")
                        if not lid_raw or not title:
                            continue
                        
                        # Get posting time (normalize to UTC)
                        post_time = None
                        created = listing.get("createdDate", listing.get("postedDate", listing.get("listDate", "")))
                        if created:
                            try:
                                if isinstance(created, (int, float)):
                                    ts = created / 1000 if created > 1e10 else created
                                    # fromtimestamp with UTC to avoid local tz issues
                                    post_time = datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
                                else:
                                    parsed = datetime.fromisoformat(str(created))
                                    if parsed.tzinfo is not None:
                                        post_time = parsed.astimezone(timezone.utc).replace(tzinfo=None)
                                    else:
                                        post_time = parsed
                            except Exception as e:
                                log.warning(f"OU time parse error: {created} -> {e}")
                        
                        # SKIP if no time or older than cutoff
                        if not post_time or post_time < cutoff:
                            continue
                        
                        img = listing.get("image", {})
                        img_url = img.get("url", "") if isinstance(img, dict) else ""
                        price = listing.get("price", 0)
                        try:
                            price_str = f"${int(float(price))}" if price else "FREE"
                        except:
                            price_str = "FREE"
                        mileage = get_mileage(title) if cat_name in ["cars", "boats"] else ""
                        
                        listings.append({
                            "id": lid, "source": "OU", "title": title,
                            "link": f"https://offerup.com/item/detail/{lid_raw}",
                            "price": price_str, "location": f"{loc} ({zipcode})",
                            "category": cat_name, "mileage": mileage,
                            "time": post_time, "image": img_url
                        })
            except Exception as e:
                log.warning(f"OU error {loc}/{cat_name}: {e}")
            await asyncio.sleep(0.15)
    
    return listings

# ─── DO SCAN ───
async def do_scan(bot):
    """
    Main scan:
    1. Scan all CL cities (FREE, CARS, BOATS)
    2. Scan all OU locations (FREE, CARS, BOATS)
    3. Filter to only listings within 40 minutes
    4. Sort by posting time (oldest first)
    5. Send alerts in that order
    """
    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=MAX_AGE_MINUTES)
    log.info(f"Scan start — now(UTC)={now.strftime('%H:%M:%S')}, cutoff={cutoff.strftime('%H:%M:%S')}")
    
    connector = aiohttp.TCPConnector(force_close=True, limit=10)
    async with aiohttp.ClientSession(connector=connector) as session:
        
        # Collect from both sources
        cl_listings = await scan_craigslist(session, now, cutoff)
        ou_listings = await scan_offerup(session, now, cutoff)
        log.info(f"Found {len(cl_listings)} CL + {len(ou_listings)} OU listings within {MAX_AGE_MINUTES}m")
        
        # Combine all listings
        all_listings = cl_listings + ou_listings
        
        if not all_listings:
            return 0
        
        # Sort by posting time (oldest first - so alerts go in order)
        all_listings.sort(key=lambda x: x["time"])
        
        # Fetch CL images
        for listing in all_listings:
            if listing["source"] == "CL" and not listing["image"]:
                listing["image"] = await fetch_cl_image(session, listing["link"])
                await asyncio.sleep(0.05)
        
        # Send alerts in posting order
        sent = 0
        for listing in all_listings:
            if listing["id"] in seen:
                continue
            
            if await send_alert(bot, session, listing):
                sent += 1
                mark_seen(listing["id"])
            
            await asyncio.sleep(0.03)
        
        return sent

# ─── /scan COMMAND ───
async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global scan_running
    
    if scan_running:
        await update.message.reply_text("⏳ Scan already running...")
        return
    
    scan_running = True
    
    msg = await update.message.reply_text(
        "🔍 *SCANNING...*\n\n"
        f"📋 {len(CL_CITIES)} CL cities\n"
        f"🟠 {len(OU_LOCS)} OU locations\n"
        "📦 FREE • CARS • BOATS\n"
        f"⏰ Only last {MAX_AGE_MINUTES} min",
        parse_mode="Markdown"
    )
    
    start = datetime.utcnow()
    total = await do_scan(context.bot)
    elapsed = (datetime.utcnow() - start).seconds
    
    await msg.edit_text(
        f"✅ *SCAN COMPLETE*\n\n"
        f"📤 Sent: {total} alerts\n"
        f"⏱️ Time: {elapsed}s",
        parse_mode="Markdown"
    )
    
    scan_running = False

# ─── /start COMMAND ───
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *LISTING SCANNER*\n\n"
        f"/scan - Scan now\n"
        f"/status - Status\n\n"
        f"🔄 Auto-scan: every {SCAN_INTERVAL}s\n"
        f"⏰ Only listings within {MAX_AGE_MINUTES} min",
        parse_mode="Markdown"
    )

# ─── /status COMMAND ───
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📊 *STATUS*\n\n"
        f"✅ Running\n"
        f"📂 Seen: {len(seen)}\n"
        f"🔄 Interval: {SCAN_INTERVAL}s\n"
        f"⏰ Max age: {MAX_AGE_MINUTES} min",
        parse_mode="Markdown"
    )

# ─── AUTO SCANNER ───
async def auto_scanner(bot):
    log.info(f"🚀 Auto-scanner: every {SCAN_INTERVAL}s, max age {MAX_AGE_MINUTES}m")
    
    while not shutdown_event.is_set():
        if not scan_running:
            start = datetime.utcnow()
            log.info(f"🔄 Auto-scan at {start.strftime('%H:%M:%S')} UTC")
            
            try:
                total = await do_scan(bot)
                elapsed = (datetime.utcnow() - start).seconds
                log.info(f"📊 Sent {total} alerts in {elapsed}s")
            except Exception as e:
                log.error(f"Auto-scan failed: {e}", exc_info=True)
            
            cleanup_seen()
        
        # Use wait with timeout instead of sleep — exits immediately on shutdown
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=SCAN_INTERVAL)
            break  # shutdown triggered
        except asyncio.TimeoutError:
            pass  # normal — just loop again

# ─── SHUTDOWN EVENT ───
shutdown_event = asyncio.Event()

# ─── HEALTH ───
async def health(request):
    if shutdown_event.is_set():
        # Return 503 during shutdown so Railway stops routing to this container
        return web.Response(text="SHUTTING DOWN", status=503)
    return web.Response(text="OK")

# ─── GRACEFUL SHUTDOWN ───
def handle_signal(sig):
    log.info(f"⛔ Received {sig.name} — shutting down gracefully")
    shutdown_event.set()

# ─── MAIN ───
async def main():
    import signal as signal_mod
    
    loop = asyncio.get_running_loop()
    
    # Register signal handlers so SIGTERM/SIGINT trigger clean shutdown
    for sig in (signal_mod.SIGTERM, signal_mod.SIGINT):
        loop.add_signal_handler(sig, handle_signal, sig)
    
    # Health server
    app_web = web.Application()
    app_web.router.add_get("/", health)
    runner = web.AppRunner(app_web)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    await web.TCPSite(runner, "0.0.0.0", port).start()
    log.info(f"🌐 Health server on port {port}")
    
    # Bot
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("scan", scan_command))
    app.add_handler(CommandHandler("status", status_command))
    
    await app.initialize()
    await app.bot.delete_webhook(drop_pending_updates=True)
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    
    log.info("✅ Bot ready")
    
    await app.bot.send_message(
        CHAT_ID,
        f"🚀 *BOT STARTED*\n\n"
        f"🔄 Scanning every {SCAN_INTERVAL}s\n"
        f"⏰ Only listings within {MAX_AGE_MINUTES} min\n"
        f"📦 FREE • CARS • BOATS\n"
        f"📤 Sorted by post time",
        parse_mode="Markdown"
    )
    
    # Start auto-scanner as background task
    scanner_task = asyncio.create_task(auto_scanner(app.bot))
    
    # Wait until shutdown signal received
    await shutdown_event.wait()
    
    # ─── CLEANUP: kill the ghost ───
    log.info("🧹 Stopping auto-scanner...")
    scanner_task.cancel()
    try:
        await scanner_task
    except asyncio.CancelledError:
        pass
    
    log.info("🧹 Stopping Telegram polling...")
    try:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
    except Exception as e:
        log.warning(f"Bot shutdown error (non-fatal): {e}")
    
    log.info("🧹 Stopping health server...")
    await runner.cleanup()
    
    log.info("💀 Clean exit. No ghosts.")

if __name__ == "__main__":
    asyncio.run(main())
