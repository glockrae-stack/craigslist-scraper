import feedparser
import requests
import time
import ssl

# Bypasses security blocks
ssl._create_default_https_context = ssl._create_unverified_context

# --- CREDENTIALS ---
TOKEN = "8761442506:AAFPCQyaKuSbjuc4s8SwzKYvMAFHQ5QlgXY"
MY_PERSONAL_ID = "6549307194" # <--- UPDATED TO YOUR REAL ID

# --- HUNTING GROUNDS ---
# Low Ticket = Furniture | High Ticket = Boats/Cars with motivated keywords
SEARCHES = {
    "🪑 LOW TICKET": "https://newyork.craigslist.org/search/sss?format=rss&query=furniture",
    "🛳 HIGH TICKET": "https://newyork.craigslist.org/search/boo?format=rss&query=boat|honda|toyota|must+sell|moving|estate"
}

def send_msg(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": MY_PERSONAL_ID, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, data=payload, timeout=10)
        print(f"Telegram Sent: {r.status_code}")
    except Exception as e:
        print(f"Telegram Error: {e}")

def monitor():
    seen = set()
    # Confirming the bot can finally see YOU
    send_msg("🚀 <b>MIKE STRAT SYSTEM: ONLINE</b>\nScanning for High & Low Ticket Deals...")
    
    while True:
        for label, url in SEARCHES.items():
            try:
                # Bypass Craigslist bot detection
                response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
                feed = feedparser.parse(response.content)
                
                for entry in feed.entries[:5]:
                    if entry.link not in seen:
                        msg = f"{label}\n\n<b>{entry.title}</b>\n\n🔗 <a href='{entry.link}'>View Listing</a>"
                        send_msg(msg)
                        seen.add(entry.link)
            except Exception as e:
                print(f"Scraper Error: {e}")
        
        print("Waiting 5 minutes for next scan...")
        time.sleep(300) 

if __name__ == "__main__":
    monitor()
