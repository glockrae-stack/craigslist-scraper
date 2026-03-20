import os
import random
import urllib.parse
import sqlite3
import feedparser
import asyncio
import aiohttp
from datetime import datetime

# python-telegram-bot components
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ==========================================
# CONFIGURATION & CREDENTIALS
# ==========================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8761442506:AAFPCQyaKuSbjuc4s8SwzKYvMAFHQ5QlgXY")
CHAT_ID = os.getenv("CHAT_ID", "6549307194")

# Railway Persistent Volume Mapping
DB_PATH = "/app/data/deals.db" if os.path.exists("/app/data") else "deals.db"

# Global state for the /status command
LAST_SCAN_TIME = "Initializing..."

# ==========================================
# CITIES & SEARCH CONFIGURATION (Mike Strategy)
# ==========================================
CITIES =[
    {"zip": "33101", "subdomain": "miami", "name": "Miami, FL"},
    {"zip": "90001", "subdomain": "losangeles", "name": "Los Angeles, CA"},
    {"zip": "10001", "subdomain": "newyork", "name": "New York, NY"},
    {"zip": "60601", "subdomain": "chicago", "name": "Chicago, IL"},
    {"zip": "77001", "subdomain": "houston", "name": "Houston, TX"},
    {"zip": "85001", "subdomain": "phoenix", "name": "Phoenix, AZ"},
    {"zip": "19101", "subdomain": "philadelphia", "name": "Philadelphia, PA"},
    {"zip": "78201", "subdomain": "sanantonio", "name": "San Antonio, TX"},
    {"zip": "92101", "subdomain": "sandiego", "name": "San Diego, CA"},
    {"zip": "75201", "subdomain": "dallas", "name": "Dallas, TX"},
    {"zip": "95101", "subdomain": "sfbay", "name": "San Jose, CA"},
    {"zip": "73301", "subdomain": "austin", "name": "Austin, TX"},
    {"zip": "32201", "subdomain": "jacksonville", "name": "Jacksonville, FL"},
    {"zip": "76101", "subdomain": "dallas", "name": "Fort Worth, TX"},
    {"zip": "43201", "subdomain": "columbus", "name": "Columbus, OH"},
    {"zip": "46201", "subdomain": "indianapolis", "name": "Indianapolis, IN"},
    {"zip": "28201", "subdomain": "charlotte", "name": "Charlotte, NC"},
    {"zip": "94101", "subdomain": "sfbay", "name": "San Francisco, CA"},
    {"zip": "98101", "subdomain": "seattle", "name": "Seattle, WA"},
    {"zip": "80201", "subdomain": "denver", "name": "Denver, CO"},
    {"zip": "20001", "subdomain": "washingtondc", "name": "Washington, DC"},
    {"zip": "02101", "subdomain": "boston", "name": "Boston, MA"},
    {"zip": "79901", "subdomain": "elpaso", "name": "El Paso, TX"},
    {"zip": "37201", "subdomain": "nashville", "name": "Nashville, TN"},
    {"zip": "48201", "subdomain": "detroit", "name": "Detroit, MI"},
    {"zip": "73101", "subdomain": "okc", "name": "Oklahoma City, OK"},
    {"zip": "97201", "subdomain": "portland", "name": "Portland, OR"},
    {"zip": "89101", "subdomain": "lasvegas", "name": "Las Vegas, NV"}
]

SEARCH_CONFIG =[
    {"query": "west elm", "category": "fua", "est_market_price": 800},
    {"query": "pottery barn", "category": "fua", "est_market_price": 1000},
    {"query": "cb2", "category": "fua", "est_market_price": 700},
    {"query": "restoration hardware", "category": "fua", "est_market_price": 2000},
    {"query": "cloud sofa", "category": "fua", "est_market_price": 3000},
    {"query": "center console boat", "category": "boo", "est_market_price": 25000},
    {"query": "honda civic", "category": "cto", "est_market_price": 8000},
    {"query": "toyota camry", "category": "cto", "est_market_price": 9000},
    {"query": "must sell", "category": "cto", "est_market_price": 15000},
    {"query": "divorce", "category": "cto", "est_market_price": 15000},
    {"query": "moving", "category": "fua", "est_market_price": 600}
]

USER_AGENTS =[
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
]

# ==========================================
# 1. TELEGRAM ASYNC COMMAND HANDLERS
# ==========================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Triggered when user sends /start"""
    welcome_text = (
        "🦅 <b>Mike Strategy Arbitrage System Initialized.</b>\n\n"
        "Welcome to your High-Ticket Lead Generation hub. I am currently operating in the background, "
        "scanning 28 cities across the US for undervalued assets (30%+ below market value).\n\n"
        "<i>Ready to secure the bag.</i> 💰"
    )
    
    keyboard = [[InlineKeyboardButton("📟 Check System Status", callback_data="check_status")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(welcome_text, parse_mode="HTML", reply_markup=reply_markup)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Triggered by /status OR clicking the Check Status button"""
    global LAST_SCAN_TIME
    status_text = (
        f"✅ <b>System Online.</b>\n"
        f"📍 Scanning 28 Cities.\n"
        f"🕒 Last scan: {LAST_SCAN_TIME}"
    )

    if update.callback_query:
        # If it was a button click
        await update.callback_query.answer("Status Refreshed 🟢")
        await update.callback_query.message.reply_text(status_text, parse_mode="HTML")
    elif update.message:
        # If it was a direct /status command
        await update.message.reply_text(status_text, parse_mode="HTML")

# ==========================================
# 2. CORE SCRAPING & GRADING LOGIC
# ==========================================
def setup_database():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS seen_deals (link TEXT PRIMARY KEY)")
    conn.commit()
    return conn

def extract_price(title):
    try:
        if "&#x0024;" in title:
            title = title.replace("&#x0024;", "$")
        if "$" in title:
            price_str = title.split("$")[1].split()[0]
            return int(price_str.replace(",", ""))
        return 0
    except:
        return 0

def extract_image_url(entry):
    if hasattr(entry, 'enclosures') and len(entry.enclosures) > 0:
        return entry.enclosures[0].href
    return None

def grade_deal(price, est_market_price, title, description, image_url):
    text = f"{title} {description}".lower()
    
    is_discounted = False
    if 0 < price <= (est_market_price * 0.70):
        is_discounted = True

    good_keywords =['moving today', 'must sell', 'divorce', 'moving', 'need gone', 'asap', 'obo', 'make offer']
    has_keywords = any(kw in text for kw in good_keywords)
    has_photo = bool(image_url)

    if is_discounted and has_keywords and has_photo:
        return "Grade A 🔥", True
    elif is_discounted and has_photo:
        return "Grade B 🛋️", True
    elif has_keywords and has_photo:
        return "Grade C 📊", False 
    else:
        return "Grade D", False

async def send_deal_alert(bot, item):
    """Pushes the deal UI to Telegram"""
    caption = (
        f"<b>{item['grade']} ALERT</b>\n\n"
        f"<b>Item:</b> {item['title']}\n"
        f"<b>Listed Price:</b> ${item['price']}\n"
        f"<b>Est. Market Value:</b> ${item['market_value']}\n"
        f"<b>Location:</b> {item['city_name']} (Zip: {item['zip']})\n"
        f"<b>Search Match:</b> <i>'{item['query'].title()}'</i>"
    )

    keyboard = [[InlineKeyboardButton("👀 View Deal", url=item['link'])]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        if item['image_url']:
            await bot.send_photo(chat_id=CHAT_ID, photo=item['image_url'], caption=caption, parse_mode="HTML", reply_markup=reply_markup)
        else:
            await bot.send_message(chat_id=CHAT_ID, text=caption, parse_mode="HTML", reply_markup=reply_markup)
    except Exception as e:
        print(f"Failed to send alert: {e}")

# ==========================================
# 3. ASYNC BACKGROUND SCRAPER LOOP
# ==========================================
async def background_scraper_loop(app: Application):
    """This runs continuously in the background using asyncio"""
    global LAST_SCAN_TIME
    conn = setup_database()
    c = conn.cursor()
    
    print("Background Scraper task initialized.")
    
    # We use aiohttp for NON-BLOCKING web requests!
    async with aiohttp.ClientSession() as session:
        while True:
            LAST_SCAN_TIME = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\nStarting sweep at {LAST_SCAN_TIME}...")
            
            for city in CITIES:
                for config in SEARCH_CONFIG:
                    query_encoded = urllib.parse.quote(config['query'])
                    rss_url = f"https://{city['subdomain']}.craigslist.org/search/{config['category']}?query={query_encoded}&format=rss"
                    headers = {"User-Agent": random.choice(USER_AGENTS)}
                    
                    try:
                        # Non-blocking GET request
                        async with session.get(rss_url, headers=headers, timeout=15) as response:
                            content = await response.read()
                            feed = feedparser.parse(content)

                            for entry in feed.entries:
                                link = entry.link
                                title = entry.title
                                description = getattr(entry, 'summary', '')

                                c.execute("SELECT link FROM seen_deals WHERE link=?", (link,))
                                if c.fetchone() is None:
                                    price = extract_price(title)
                                    image_url = extract_image_url(entry)
                                    
                                    grade, is_worthy = grade_deal(price, config['est_market_price'], title, description, image_url)

                                    if is_worthy:
                                        item = {
                                            "title": title,
                                            "price": price,
                                            "market_value": config['est_market_price'],
                                            "link": link,
                                            "city_name": city['name'],
                                            "zip": city['zip'],
                                            "query": config['query'],
                                            "image_url": image_url,
                                            "grade": grade
                                        }
                                        print(f"Found {grade} deal in {city['name']}!")
                                        await send_deal_alert(app.bot, item)

                                    c.execute("INSERT INTO seen_deals (link) VALUES (?)", (link,))
                                    conn.commit()

                    except Exception as e:
                        print(f"Network error on {city['name']} for '{config['query']}': {e}")

                    # NON-BLOCKING Jitter Delay (15-45s) - The Bot still listens during this sleep!
                    await asyncio.sleep(random.uniform(15.0, 45.0))
            
            print("Full sweep complete. Sleeping for 45 minutes to reset IP reputation...")
            await asyncio.sleep(2700)

async def post_init(app: Application):
    """This hook starts the background scraper right after the bot boots up"""
    asyncio.create_task(background_scraper_loop(app))

# ==========================================
# 4. SYSTEM BOOT
# ==========================================
if __name__ == "__main__":
    print("Building Async Application...")
    
    # Build the Application
    app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    
    # Add Command Handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("status", status_command))
    
    # Add Button Click Handler
    app.add_handler(CallbackQueryHandler(status_command, pattern="^check_status$"))
    
    print("Bot Listener Online. Running Event Loop...")
    
    # Run the bot! (This handles the event loop and keeps the script alive)
    app.run_polling(drop_pending_updates=True)
