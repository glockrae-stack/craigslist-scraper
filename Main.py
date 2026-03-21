import asyncio
import os
import threading
import httpx
import feedparser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application

# ─── CONFIG ───
TOKEN   = "8601205854:AAF5lME-PScrRA__JxfRP1PRJ0bp00IkSBU" 
CHAT_ID = "8761442506"
DB_FILE = "seen_ids.txt"

# ─── STEP 1: THE HEARTBEAT (Keeps Railway Happy) ───
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive")

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# ─── STEP 2: THE SCANNER ───
CL_CITIES = {"SF": "sfbay", "LA": "losangeles", "Chi": "chicago", "Mia": "miami", "Phx": "phoenix"}
CATEGORIES = {"cars": "cta", "boats": "boo"}

def load_seen():
    if os.path.exists(DB_FILE):
        with open(DB_FILE) as f: return set(f.read().splitlines())
    return set()

def mark_seen(lid):
    with open(DB_FILE, "a") as f: f.write(f"{lid}\n")

seen = load_seen()

async def check_cl(app):
    for label, slug in CL_CITIES.items():
        for cat_name, cat_code in CATEGORIES.items():
            url = f"https://{slug}.craigslist.org/search/{cat_code}?format=rss"
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(url)
                    feed = feedparser.parse(resp.text)
                    for entry in feed.entries[:5]:
                        eid = getattr(entry, "id", entry.link)
                        if eid in seen: continue
                        
                        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚡ VIEW DEAL", url=entry.link)]])
                        await app.bot.send_message(CHAT_ID, f"🚗 *NEW {cat_name.upper()}* ({label})\n{entry.title}", parse_mode="Markdown", reply_markup=kb)
                        seen.add(eid)
                        mark_seen(eid)
            except: continue
        await asyncio.sleep(2) # Small gap between cities

# ─── STEP 3: THE MAIN LOOP ───
async def main():
    # Start the web server first so Railway sees a "Success"
    threading.Thread(target=run_health_server, daemon=True).start()
    print("📡 Heartbeat server active on port 8080.")

    # CRITICAL: Wait 20 seconds before starting the bot.
    # This ensures Railway has killed the "old" bot session.
    print("⏳ Waiting for old sessions to clear (20s)...")
    await asyncio.sleep(20)

    print("🤖 Initializing Bot...")
    app = Application.builder().token(TOKEN).build()
    
    # Kick any other instances off the token
    await app.initialize()
    await app.bot.delete_webhook(drop_pending_updates=True)
    await app.start()
    
    print("🚀 BOT IS LIVE. No more conflicts.")
    await app.bot.send_message(CHAT_ID, "✅ Bot Restarted! Scans are running now.")

    while True:
        try:
            await check_cl(app)
            print(f"✅ Sweep complete at {datetime.now().strftime('%H:%M:%S')}")
            await asyncio.sleep(600) # Wait 10 mins
        except Exception as e:
            print(f"⚠️ Loop Error: {e}")
            await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(main())
