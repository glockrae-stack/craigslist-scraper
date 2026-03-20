import asyncio
import feedparser
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ============================================================
# CREDENTIALS
# ============================================================
TOKEN   = "8761442506:AAFPCQyaKuSbjuc4s8SwzKYvMAFHQ5QlgXY"
CHAT_ID = "6549307194"

# ============================================================
# 17 MARKETS
# ============================================================
CITIES = [
    "phoenix", "losangeles", "sandiego", "sfbay", "cosprings",
    "washingtondc", "atlanta", "chicago", "neworleans", "boston",
    "detroit", "minneapolis", "lasvegas", "albuquerque", "newyork",
    "portland", "dallas"
]

# ============================================================
# FILTERS
# ============================================================
ASSETS    = ["boat", "center console", "skiff", "outboard", "honda", "toyota",
             "lexus", "jet ski", "yamaha", "seadoo", "camry", "accord"]
DISTRESS  = ["must sell", "divorce", "moving", "cash only", "negotiable",
             "needs gone", "motivated", "estate sale", "title in hand", "obo",
             "relocating", "price drop", "make offer"]
FURNITURE = ["couch", "sofa", "sectional", "dresser", "tv stand", "dining table",
             "recliner", "loveseat", "bedroom set"]
NEGATIVES = ["curb alert", "on the curb", "broken", "damaged", "junk",
             "medical", "wheelchair", "animal", "parts only"]

# ============================================================
# STATE
# ============================================================
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
seen_ids    = set()
scan_active = True
leads_found = 0
scan_count  = 0
start_time  = datetime.now()

# ============================================================
# KEYBOARD
# ============================================================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📡 Ping",         callback_data="ping"),
         InlineKeyboardButton("📊 Stats",        callback_data="stats")],
        [InlineKeyboardButton("⏸ Pause",         callback_data="pause"),
         InlineKeyboardButton("▶️ Resume",        callback_data="resume")],
        [InlineKeyboardButton("🧹 Clear Memory", callback_data="clear"),
         InlineKeyboardButton("🏙 Cities",       callback_data="cities")],
        [InlineKeyboardButton("💡 Strategy",     callback_data="strategy")],
    ])

# ============================================================
# COMMANDS
# ============================================================
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 *MONEY MAGNET ONLINE*\n\n"
        "Scanning *17 cities* every 10 minutes.\n"
        "Hunting distressed assets + free furniture flips.\n\n"
        "Pick an option 👇",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

async def status_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uptime = str(datetime.now() - start_time).split(".")[0]
    state  = "▶️ ACTIVE" if scan_active else "⏸ PAUSED"
    await update.message.reply_text(
        f"🤖 *STATUS*\n\n"
        f"Scanner: {state}\n"
        f"Uptime: `{uptime}`\n"
        f"Scans run: `{scan_count}`\n"
        f"Leads found: `{leads_found}`\n"
        f"Seen IDs in memory: `{len(seen_ids)}`",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

# ============================================================
# BUTTON HANDLER
# ============================================================
async def button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global scan_active, seen_ids
    q = update.callback_query
    await q.answer()

    if q.data == "ping":
        await q.edit_message_text(
            "✅ *PONG!* Bot is alive.",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )

    elif q.data == "stats":
        uptime = str(datetime.now() - start_time).split(".")[0]
        state  = "▶️ ACTIVE" if scan_active else "⏸ PAUSED"
        await q.edit_message_text(
            f"📊 *LIVE STATS*\n\n"
            f"Scanner: {state}\n"
            f"Uptime: `{uptime}`\n"
            f"Scans completed: `{scan_count}`\n"
            f"Total leads sent: `{leads_found}`\n"
            f"Memory (seen IDs): `{len(seen_ids)}`\n"
            f"Cities monitored: `{len(CITIES)}`",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )

    elif q.data == "pause":
        scan_active = False
        await q.edit_message_text(
            "⏸ *Scanner paused.*",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )

    elif q.data == "resume":
        scan_active = True
        await q.edit_message_text(
            "▶️ *Scanner resumed.* Back on the hunt.",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )

    elif q.data == "clear":
        seen_ids.clear()
        await q.edit_message_text(
            "🧹 *Memory cleared.* Fresh scan next cycle.",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )

    elif q.data == "cities":
        city_list = "\n".join(f"• {c}" for c in CITIES)
        await q.edit_message_text(
            f"🏙 *MONITORED CITIES ({len(CITIES)})*\n\n{city_list}",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )

    elif q.data == "strategy":
        await q.edit_message_text(
            "💡 *MIKE STRATEGY*\n\n"
            "1️⃣ Scan distressed sellers (divorce, moving, must sell)\n"
            "2️⃣ Target high-ticket assets (boats, cars, jet skis)\n"
            "3️⃣ Lock in with DocuSign Purchase Agreement\n"
            "4️⃣ Flip the contract — never touch the asset\n\n"
            "🆓 *FREE SCALP:* Grab furniture, resell same day.\n\n"
            "_Motivation > Price. Always._",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )

# ============================================================
# SCAN ENGINE
# ============================================================
async def scan_loop(app: Application):
    global scan_active, leads_found, scan_count, seen_ids

    await asyncio.sleep(5)

    while True:
        if scan_active:
            logging.info(f"--- SCAN #{scan_count + 1} STARTING ---")
            for city in CITIES:
                try:
                    s = feedparser.parse(f"https://{city}.craigslist.org/search/sss?format=rss")
                    for e in s.entries:
                        if e.id in seen_ids:
                            continue
                        text = (e.title + " " + getattr(e, "summary", "")).lower()
                        if any(a in text for a in ASSETS) and any(d in text for d in DISTRESS):
                            msg = (
                                f"💰 *MIKE STRATEGY: HIGH-TICKET LEAD*\n"
                                f"📍 {city.upper()}\n"
                                f"📝 {e.title}\n"
                                f"🔗 {e.link}\n\n"
                                f"⚡ _Distressed seller. Send DocuSign PA now._"
                            )
                            await app.bot.send_message(CHAT_ID, msg, parse_mode="Markdown")
                            leads_found += 1
                        seen_ids.add(e.id)

                    f = feedparser.parse(f"https://{city}.craigslist.org/search/zip?format=rss")
                    for e in f.entries:
                        if e.id in seen_ids:
                            continue
                        t = e.title.lower()
                        if any(k in t for k in FURNITURE) and not any(n in t for n in NEGATIVES):
                            msg = (
                                f"🆓 *FREE SCALP: {city.upper()}*\n"
                                f"📝 {e.title}\n"
                                f"🔗 {e.link}"
                            )
                            await app.bot.send_message(CHAT_ID, msg, parse_mode="Markdown")
                            leads_found += 1
                        seen_ids.add(e.id)

                except Exception as ex:
                    logging.warning(f"Error scanning {city}: {ex}")
                    continue

            scan_count += 1

            if len(seen_ids) > 3000:
                seen_ids.clear()
                logging.info("Memory cleared — hit 3000 ID limit.")

            logging.info(f"Scan #{scan_count} done. Leads: {leads_found}. Sleeping 10m.")

        await asyncio.sleep(600)

# ============================================================
# ENTRY POINT
# ============================================================
async def post_init(app: Application):
    asyncio.create_task(scan_loop(app))
    logging.info("=== MONEY MAGNET ONLINE ===")

def main():
    app = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CallbackQueryHandler(button))

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
