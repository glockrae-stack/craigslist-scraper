import feedparser
import requests
import time
import ssl

ssl._create_default_https_context = ssl._create_unverified_context

TOKEN = "8761442506:AAFPCQyaKuSbjuc4s8SwzKYvMAFHQ5QlgXY"
MY_PERSONAL_ID = "6549307194" 

SEARCHES = {
    "🪑 LOW TICKET": "https://newyork.craigslist.org/search/sss?format=rss&query=furniture",
    "🛳 HIGH TICKET": "https://newyork.craigslist.org/search/boo?format=rss&query=boat|honda|toyota|must+sell"
}

def send_msg(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": MY_PERSONAL_ID, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, data=payload, timeout=10)
        print(f"Telegram Sent Status: {r.status_code}") 
    except Exception as e:
        print(f"Error: {e}")

def monitor():
    seen = set()
    send_msg("✅ <b>CONNECTION ESTABLISHED!</b>\n\nI am now watching for Mike-style deals. If I find furniture or boats/cars, I'll ping you here.")
    
    while True:
        for label, url in SEARCHES.items():
            try:
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
        time.sleep(300) 

if __name__ == "__main__":
    monitor()
    
