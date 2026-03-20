import asyncio
import feedparser
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# --- YOUR RECALLED DATA ---
TOKEN = "8761442506:AAFPCQyaKuSbjuc4s8SwzKYvMAFHQ5QlgXY"
CHAT_ID = "6549307194"

CITIES = ["phoenix", "losangeles", "sandiego", "sfbay", "cosprings", "washingtondc", "atlanta", "chicago", "neworleans", "boston", "detroit", "minneapolis", "lasvegas", "albuquerque", "newyork", "portland", "dallas"]
FURNITURE = ["couch", "sofa", "dresser", "tv stand", "table"]
HIGH_TICKET = ["boat", "center console", "honda", "toyota", "jet ski"]
DISTRESS = ["must sell", "divorce", "moving", "cash only", "needs gone"]
NEGATIVES = ["curb alert", "on the curb", "broken", "damaged", "junk", "medical", "wheelchair", "animal"]

logging.basicConfig(level=logging.INFO)

async def scan_loop(app):
    """The Manual 10-Minute Engine"""
    while True:
        logging.info("--- Starting Multi-Market Scan ---")
        for city in CITIES:
            # 1. Low Ticket (FREE)
            f_url = f"https://{city}.craigslist.org/search/zip?format=rss"
            f_feed = feedparser.parse(f_url)
            for e in f_feed.entries[:5]:
                title = e.title.lower()
                desc = e.summary.lower()
                if any(k in title for k in FURNITURE) and not any(n in title or n in desc for n in NEGATIVES):
                    msg = f"🆓 **FREE DEAL FOUND**\n\n**{e.title}**\n📍 {city.upper()}\n\n[🚀 VIEW LISTING]({e.link})"
                    await app.bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='Markdown')

            # 2. High Ticket (DISTRESS)
            s_url = f"https://{city}.craigslist.org/search/sss?format=rss"
            s_feed = feedparser.parse(s_url)
            for e in s_feed.entries[:5]:
                title = e.title.lower()
                desc = e.summary.lower()
                if any(h in title for h in HIGH_TICKET) and any(d in desc for d in DISTRESS):
                    msg = f"💰 **HIGH TICKET DISTRESS**\n\n**{e.title}**\n📍 {city.upper()}\n\n[🚀 VIEW LISTING]({e.link})"
                    await app.bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='Markdown')
        
        logging.info("Scan complete. Waiting 10 minutes.")
        await asyncio.sleep(600)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ **MONEY MAGNET ONLINE.**\n\nRecall check: 17 Cities, Low + High Ticket logic is active.")

async def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    
    # Manual Startup
    await app.initialize()
    await app.start()
    
    # This starts the scan in the background without needing the Job Queue library
    asyncio.create_task(scan_loop(app))
    
    print("--- BOT IS POLLING ---")
    await app.updater.start_polling()
    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())
