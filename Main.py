import asyncio
import os
import random
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application
import httpx
import feedparser

# ─── NEW CONFIG ───
TOKEN   = "8601205854:AAF5lME-PScrRA__JxfRP1PRJ0bp00IkSBU" 
CHAT_ID = "8761442506"
DB_FILE = "seen_ids.txt"

# ─── HEARTBEAT SERVER (For Railway Health Checks) ───
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive")

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# ─── SCANNER SETTINGS ───
CL_CITIES = {"SF": "sfbay", "LA": "losangeles", "Chi": "chicago", "Mia": "miami", "Phx": "phoenix"}
CATEGORIES = {"cars": "cta", "boats": "boo"}

def load_seen():
    if os.path.exists(DB_FILE):
        with open(DB_FILE) as f: return set(f.read().splitlines())
    return set()

def mark_seen(lid):
    with open(DB_FILE, "a") as f: f.write(f"{lid}\n")

seen = load_seen()

async def check_cl_city(app, label, slug):
    for cat_name, cat_code in CATEGORIES.items():
        url = f"https://{slug}.craigslist.org/search/{cat_code}?format=rss"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url)
                feed = feedparser.parse(resp.text)
                for entry in feed.entries[:5]:
                    eid = getattr(entry, "id", entry.link)
                    if eid in seen: continue
                    
                    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚡ VIEW", url=entry.link)]])
                    await app.bot.send_message(CHAT_ID, f"🔔 *NEW {cat_name.upper()}* ({label})\n{entry.title}", parse_mode="Markdown", reply_markup=kb)
                    seen.add(eid)
                    mark_seen(eid)
        except: continue

async def main():
    print("🛰 Starting Heartbeat Server...")
    threading.Thread(target=run_health_server, daemon=True).start()
    
    print("🤖 Initializing NEW Bot...")
    app = Application.builder().token(TOKEN).build()
    
    # This specifically stops any "Ghost" bots from blocking this one
    await app.initialize()
    await app.bot.delete_webhook(drop_pending_updates=True)
    
    await app.start()
    print("🚀 NEW BOT IS ONLINE. Starting scans...")
    
    while True:
        try:
            for label, slug in CL_CITIES.items():
                await check_cl_city(app, label, slug)
                await asyncio.sleep(5) 
            print(f"✅ Sweep done at {datetime.now().strftime('%H:%M:%S')}")
            await asyncio.sleep(600) # Wait 10 minutes between full sweeps
        except Exception as e:
            print(f"⚠️ Loop Error: {e}")
            await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(main())
