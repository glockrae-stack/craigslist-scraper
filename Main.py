import asyncio, feedparser, os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler

# --- CONFIG ---
TOKEN = "8761442506:AAFPCQyaKuSbjuc4s8SwzKYvMAFHQ5QlgXY"
CHAT_ID = "6549307194"
DB_FILE = "seen_ids.txt"

# 17 High-Volume Markets
CITIES = ["phoenix", "losangeles", "sandiego", "sfbay", "cosprings", "washingtondc", "atlanta", "chicago", "neworleans", "boston", "detroit", "minneapolis", "lasvegas", "albuquerque", "newyork", "portland", "dallas"]

# Broad Asset Net
ASSETS = ["boat", "honda", "toyota", "lexus", "truck", "camry", "accord", "skiff", "jet ski", "couch", "dresser", "sectional", "f150", "silverado"]

def load_ids():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: return set(f.read().splitlines())
    return set()

def save_id(listing_id):
    with open(DB_FILE, "a") as f: f.write(f"{listing_id}\n")

seen_ids = load_ids()

async def scan_loop(app: Application):
    """The Final Engine: Alert -> Link/Price -> Title"""
    while True:
        for city in CITIES:
            try:
                feed = feedparser.parse(f"https://{city}.craigslist.org/search/sss?format=rss")
                for e in feed.entries:
                    if e.id not in seen_ids:
                        title_lower = e.title.lower()
                        
                        if any(a in title_lower for a in ASSETS):
                            # PRICE LOGIC
                            price_tag = ""
                            if "$" in e.title:
                                for word in e.title.split():
                                    if "$" in word:
                                        price_tag = f" | 💰 {word}"
                                        break
                            
                            # EXACT ORDER: Alert -> Link -> Title
                            msg = (
                                f"🚨 **NEW ALERT: {city.upper()}**\n"
                                f"🔗 [CLICK TO VIEW LISTING]({e.link}){price_tag}\n"
                                f"📦 **ITEM:** {e.title.upper()}"
                            )
                            
                            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 VIEW POST", url=e.link)]])
                            
                            await app.bot.send_message(CHAT_ID, msg, parse_mode="Markdown", reply_markup=kb)
                            save_id(e.id); seen_ids.add(e.id)
                
                await asyncio.sleep(0.5) 
            except: continue
        
        # High-frequency: 90-second refresh to hit the "5-min ago" window
        await asyncio.sleep(90) 

async def post_init(app):
    asyncio.create_task(scan_loop(app))

def main():
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
