import os
import time
import random
import urllib.parse
import requests
import sqlite3
import feedparser
import threading
from datetime import datetime
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==========================================
# CONFIGURATION & CREDENTIALS
# ==========================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8761442506:AAFPCQyaKuSbjuc4s8SwzKYvMAFHQ5QlgXY")
CHAT_ID = os.getenv("CHAT_ID", "6549307194")

# Initialize the TeleBot instance
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Railway Persistent Volume Mapping
DB_PATH = "/app/data/deals.db" if os.path.exists("/app/data") else "deals.db"

# ==========================================
# CITIES & SEARCH CONFIGURATION
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
# TELEGRAM BOT COMMANDS (THREAD 1 - FOREGROUND)
# ==========================================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    """Handles the /start command."""
    welcome_text = (
        "🦅 <b>Mike Strategy Arbitrage System Initialized.</b>\n\n"
        "Welcome to your High-Ticket Lead Generation hub. I am currently operating in the background, "
        "scanning 28 cities across the US for undervalued assets (30%+ below market value).\n\n"
        "<i>Ready to secure the bag.</i> 💰"
    )
    
    # Create the inline button
    markup = InlineKeyboardMarkup()
    btn = InlineKeyboardButton("📡 Check Connection", callback_data="ping_server")
    markup.add(btn)

    bot.send_message(message.chat.id, welcome_text, parse_mode="HTML", reply_markup=markup)

@bot.message_handler(commands=['ping'])
def send_ping(message):
    """Handles the /ping command."""
    server_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bot.reply_to(message, f"🏓 <b>Pong! System is Live.</b>\n🕒 Server Time: {server_time}", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "ping_server")
def handle_ping_callback(call):
    """Handles the button press from the /start menu."""
    server_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bot.answer_callback_query(call.id, "Connection solid. 🟢")
    bot.send_message(call.message.chat.id, f"🏓 <b>Pong! System is Live.</b>\n🕒 Server Time: {server_time}", parse_mode="HTML")

# ==========================================
# DATABASE & SCRAPING LOGIC (THREAD 2 - BACKGROUND)
# ==========================================
def setup_database():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
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

def send_deal_alert(item):
    """Pushes a scraped deal to Telegram using the TeleBot instance."""
    caption = (
        f"<b>{item['grade']} ALERT</b>\n\n"
        f"<b>Item:</b> {item['title']}\n"
        f"<b>Listed Price:</b> ${item['price']}\n"
        f"<b>Est. Market Value:</b> ${item['market_value']}\n"
        f"<b>Location:</b> {item['city_name']} (Zip: {item['zip']})\n"
        f"<b>Search Match:</b> <i>'{item['query'].title()}'</i>"
    )

    markup = InlineKeyboardMarkup()
    btn = InlineKeyboardButton("👀 View Deal", url=item['link'])
    markup.add(btn)

    try:
        if item['image_url']:
            bot.send_photo(CHAT_ID, item['image_url'], caption=caption, parse_mode="HTML", reply_markup=markup)
        else:
            bot.send_message(CHAT_ID, caption, parse_mode="HTML", reply_markup=markup)
    except Exception as e:
        print(f"Failed to send deal to Telegram: {e}")

def background_scraper_loop():
    """This function runs indefinitely in a separate thread."""
    conn = setup_database()
    c = conn.cursor()
    
    print("[Thread-2] Background Scraper Initialized.")
    
    while True:
        print("\n[Thread-2] Starting new sweep of 28 cities...")
        for city in CITIES:
            for config in SEARCH_CONFIG:
                query_encoded = urllib.parse.quote(config['query'])
                rss_url = f"https://{city['subdomain']}.craigslist.org/search/{config['category']}?query={query_encoded}&format=rss"
                headers = {"User-Agent": random.choice(USER_AGENTS)}
                
                try:
                    response = requests.get(rss_url, headers=headers, timeout=15)
                    feed = feedparser.parse(response.content)

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
                                print(f"[Thread-2] Found {grade} deal in {city['name']}!")
                                send_deal_alert(item)

                            c.execute("INSERT INTO seen_deals (link) VALUES (?)", (link,))
                            conn.commit()

                except Exception as e:
                    print(f"[Thread-2] Network error on {city['name']} for '{config['query']}': {e}")

                # Human Jitter Delay
                time.sleep(random.uniform(15.0, 45.0))
        
        print("[Thread-2] Full sweep complete. Sleeping for 45 minutes to reset IP reputation...")
        time.sleep(2700)

# ==========================================
# SYSTEM BOOT (TYING THE THREADS TOGETHER)
# ==========================================
if __name__ == "__main__":
    print("System booting up...")
    
    # 1. Start the Scraper in a daemon thread (runs independently in the background)
    scraper_thread = threading.Thread(target=background_scraper_loop, daemon=True)
    scraper_thread.start()
    
    # 2. Start the Telegram Bot poller on the main thread
    print("[Thread-1] Telegram Bot Listener Online. Waiting for commands...")
    
    # Send an initial boot message to your phone
    try:
        bot.send_message(CHAT_ID, "🔄 <b>Server Rebooted.</b>\nBot is online and background scraper has started.", parse_mode="HTML")
    except:
        pass

    # infinity_polling keeps the script running and listening to Telegram without freezing
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
