import asyncio
import os
import random
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application
import httpx
import feedparser
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

# ─── CONFIG ───
TOKEN   = "8761442506:AAFRij1t2Wkm1MWD27Yoys4Gm-q4ZCjpT9M"
CHAT_ID = "8761442506"
DB_FILE = "seen_ids.txt"

# ─── HEARTBEAT SERVER (Tricks Railway into staying online) ───
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive")

def run_health_server():
    # Railway provides a PORT variable, usually 8080
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    print(f"📡 Heartbeat server started on port {port}")
    server.serve_forever()

# ─── SCANNER LOGIC ───
CL_CITIES = {
    "San Francisco": "sfbay", "Los Angeles": "losangeles", "San Diego": "sandiego",
    "Chicago": "chicago", "Miami": "miami", "Phoenix": "phoenix"
}
CATEGORIES = {"cars": "cta", "boats": "boo", "free": "zip"}

def load_seen():
    if os.path.exists(DB_FILE):
        with open(DB_FILE) as f: return set(f.read().splitlines())
    return set()

def mark_seen(lid):
    with open(DB_FILE, "a") as f: f.write(f"{lid}\n")

seen = load_seen()

async def check_cl_city(app, label, slug):
    now = datetime.utcnow()
    for cat_name, cat_code in CATEGORIES.items():
        url = f"https://{slug}.craigslist.org/search/{cat_code}?format=rss"
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(url)
                feed = feedparser.parse(resp.text)
                for entry in feed.entries[:5]:
                    eid = getattr(entry, "id", entry.link)
                    if eid in seen: continue
                    
                    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚡ OPEN", url=entry.link)]])
                    await app.bot.send_message(CHAT_ID, f"*{cat_name.upper()} | {label}*\n{entry.title}", parse_mode="Markdown", reply_markup=kb)
                    seen.add(eid)
                    mark_seen(eid)
        except: continue

async def main():
    print("⏳ Starting up...")
    
    # 1. Start the Heartbeat server in the background
    threading.Thread(target=run_health_server, daemon=True).start()
    
    # 2. Start the Telegram Bot
    app = Application.builder().token(TOKEN).build()
    await app.initialize()
    await app.start()
    
    # Drop old messages to avoid a flood of "Conflict" errors
    await app.updater.start_polling(drop_pending_updates=True)
    print("🚀 Taking control of the token... Bot is LIVE.")
    
    while True:
        for label, slug in CL_CITIES.items():
            await check_cl_city(app, label, slug)
            await asyncio.sleep(10) # Slow down to avoid proxy blocks
        print("✅ Round finished. Sleeping 10m.")
        await asyncio.sleep(600)

if __name__ == "__main__":
    asyncio.run(main())
