import asyncio, feedparser, os
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler

# --- CONFIG ---
TOKEN = "8761442506:AAFPCQyaKuSbjuc4s8SwzKYvMAFHQ5QlgXY"
CHAT_ID = "6549307194"
DB_FILE = "seen_ids.txt"

# 17 Key Markets & Active OfferUp Zips
CITIES = ["phoenix", "losangeles", "sandiego", "sfbay", "cosprings", "washingtondc", "atlanta", "chicago", "neworleans", "boston", "detroit", "minneapolis", "lasvegas", "albuquerque", "newyork", "portland", "dallas"]
GOLD_ZIPS = ["85251", "90210", "92037", "30327", "75205", "60611", "33139"]

# Search Categories (Firehose Mode)
ASSETS = ["boat", "honda", "toyota", "lexus", "truck", "camry", "accord", "skiff", "jet ski", "couch", "dresser", "sectional"]

def load_ids():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f: return set(f.read().splitlines())
    return set()

def save_id(listing_id):
    with open(DB_FILE, "a") as f: f.write(f"{listing_id}\n")

seen_ids = load_ids()

async def scan_loop(app: Application):
    global seen_ids
    while True:
        # 1. CRAIGSLIST FIREHOSE
        for city in CITIES:
            try:
                # sss = all for sale. No filters = Max volume.
                feed = feedparser.parse(f"https://{city}.craigslist.org/search/sss?format=rss")
                for e in feed.entries:
                    if e.id not in seen_ids:
                        title = e.title.lower()
                        if any(a in title for a in ASSETS):
                            # The Mike Style Alert Format
                            msg = (
                                f"🚨 **NEW ALERT: {city.upper()}**\n"
                                f"━━━━━━━━━━━━━━━\n"
                                f"📦 **{e.title.upper()}**\n"
                                f"━━━━━━━━━━━━━━━"
                            )
                            kb = InlineKeyboardMarkup([
                                [InlineKeyboardButton("📧 Send Offer", url=f"mailto:?subject=Regarding {e.title}"),
                                 InlineKeyboardButton("🔗 View Listing", url=e.link)]
                            ])
                            await app.bot.send_message(CHAT_ID, msg, parse_mode="Markdown", reply_markup=kb)
                            save_id(e.id); seen_ids.add(e.id)
            except: continue

        # 2. OFFERUP REFRESH (Deep Links)
        # Every 20 mins, check the wealthiest zones for the newest items
        if datetime.now().minute % 20 == 0:
            for zp in GOLD_ZIPS:
                ou_url = f"https://offerup.com/search?q=honda+toyota+boat+free&zip={zp}&sort=-p"
                kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"🔍 Scan OfferUp: {zp}", url=ou_url)]])
                await app.bot.send_message(CHAT_ID, f"🏙 **OFFERUP PULSE: {zp}**\nRefresh for newest high-ticket items.", reply_markup=kb)

        # Clear memory if it gets too huge (over 5k IDs) to keep Railway fast
        if len(seen_ids) > 5000:
            open(DB_FILE, 'w').close() # Wipe file
            seen_ids.clear()

        await asyncio.sleep(300) # 5 min rest

async def post_init(app):
    asyncio.create_task(scan_loop(app))

def main():
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", lambda u, c: u.message.reply_text("🚀 MIKE'S BOT MODE: ONLINE")))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
