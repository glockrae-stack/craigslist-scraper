import asyncio
import feedparser
import aiohttp
from datetime import datetime
from aiohttp import web
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- CONFIG ---
TOKEN = "8761442506:AAFRij1t2Wkm1MWD27Yoys4Gm-q4ZCjpT9M"
CHAT_ID = "6549307194"

# Using 'cta' to catch EVERYTHING (Dealers + Owners)
CITIES = ["phoenix", "miami", "atlanta", "chicago", "houston", "losangeles"]
CATEGORIES = ["cta", "boo", "zip"] 

seen_ids = set()
start_time = datetime.now()
last_scan_time = "Waiting..."

# --- 1. ENHANCED STATUS WITH PULSE LINKS ---
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uptime = datetime.now() - start_time
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, _ = divmod(remainder, 60)
    
    # Generate a live link for the first city to manually verify
    sample_url = f"https://{CITIES[0]}.craigslist.org/search/cta?format=rss"
    
    status_msg = (
        f"📊 **SYSTEM PULSE: LIVE**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🌐 **CL Index:** {len(seen_ids)} cached\n"
        f"🕒 **Last Scan:** {last_scan_time}\n"
        f"⏱ **Uptime:** {hours}h {minutes}m\n"
        f"🔗 **Live RSS Feed:** [Click to Verify]({sample_url})\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💡 *If Index is > 0 and no alerts, wait for a NEW post.*"
    )
    await update.message.reply_text(status_msg, parse_mode="Markdown", disable_web_page_preview=True)

# --- 2. FORCED ALERT ENGINE ---
async def run_scanner(app: Application):
    global last_scan_time
    while True:
        async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
            for city in CITIES:
                for cat in CATEGORIES:
                    url = f"https://{city}.craigslist.org/search/{cat}?format=rss"
                    try:
                        async with session.get(url, timeout=15) as resp:
                            if resp.status == 200:
                                content = await resp.text()
                                feed = feedparser.parse(content)
                                
                                for entry in feed.entries:
                                    if entry.id not in seen_ids:
                                        # FORCE ALERT: Alert if we've seen fewer than 5 items 
                                        # (This proves the notification engine works immediately)
                                        should_alert = len(seen_ids) > 5 or len(seen_ids) < 3
                                        
                                        seen_ids.add(entry.id)
                                        
                                        if should_alert:
                                            msg = f"🚨 **NEW DEAL**\n\n📍 {city.upper()}\n📝 {entry.title}\n🔗 {entry.link}"
                                            await app.bot.send_message(CHAT_ID, msg, parse_mode="Markdown")
                                            await asyncio.sleep(1) 
                    except Exception as e:
                        print(f"⚠️ CL Error ({city}): {e}")
        
        last_scan_time = datetime.now().strftime('%H:%M:%S')
        await asyncio.sleep(300) # 5-minute cycle

# --- 3. INFRASTRUCTURE ---
async def handle_health(request):
    return web.Response(text="PULSE_OK")

async def start_health_server():
    server = web.Application()
    server.router.add_get("/", handle_health)
    runner = web.AppRunner(server)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", 8080).start()

async def main():
    await start_health_server()
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("ping", status_command))
    
    # Startup Message
    await app.bot.send_message(CHAT_ID, "🚀 **BOT REBOOTED: FORCE ALERTS ON**\nWaiting for first few hits...")
    
    asyncio.create_task(run_scanner(app))
    
    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        while True:
            await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
