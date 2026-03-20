import feedparser
import requests
import time
import ssl

# Fix for server connection
ssl._create_default_https_context = ssl._create_unverified_context

# --- YOUR REAL INFO ---
TOKEN = "8761442506:AAFPCQyaKuSbjuc4s8SwzKYvMAFHQ5QlgXY"
MY_PERSONAL_ID = "6549307194" 

# --- MIKE'S HUNTING LIST ---
SEARCHES = {
    "🪑 LOW TICKET": "https://newyork.craigslist.org/search/sss?format=rss&query=furniture",
    "🛳 HIGH TICKET": "https://newyork.craigslist.org/search/boo?format=rss&query=boat|honda|toyota|must+sell"
}

def send_msg(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": MY_PERSONAL_ID, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, data=payload, timeout=10)
        print(f"Server says: {r.status_code}") 
    except Exception as e:
        print(f"Error: {e}")

def monitor():
    seen = set()
    # THIS IS THE HANDSHAKE
    send_msg("✅ <b>CONNECTION ESTABLISHED!</b>\n\nI am now watching Craigslist for Furniture and High-Ticket Boats/Cars. I will alert you the second a deal hits.")
    
    while True:
        for label, url in SEARCHES.items():
            try:
                # Use a fake browser header to prevent blocks
                headers = {'User-Agent': 'Mozilla/5.0'}
                response = requests.get(url, headers=headers, timeout=15)
                feed = feedparser.parse(response.content)
                
                for entry in feed.entries[:5]:
                    if entry.link not in seen:
                        msg = f"{label} ALERT!\n\n<b>{entry.title}</b>\n\n🔗 <a href='{entry.link}'>CLICK FOR DEAL</a>"
                        send_msg(msg)
                        seen.add(entry.link)
            except Exception as e:
                print(f"Scraper Error: {e}")
        
        time.sleep(300) # Check every 5 mins

if __name__ == "__main__":
    monitor()
