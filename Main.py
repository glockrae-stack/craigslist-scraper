import feedparser
import requests
import time
import random
import ssl

# Bypassing security blocks
ssl._create_default_https_context = ssl._create_unverified_context

# --- YOUR REAL CREDENTIALS ---
TOKEN = "8761442506:AAFPCQyaKuSbjuc4s8SwzKYvMAFHQ5QlgXY"
MY_PERSONAL_ID = "6549307194"

# --- MIKE'S COURSE KEYWORDS ---
FURN_QUERY = "west+elm|pottery+barn|cb2|restoration+hardware|cloud+sofa|moving+sale|knoll"
BOAT_QUERY = "boat|center+console|honda+civic|toyota+camry|must+sell|obo|moving"

# --- ALL CITIES FROM YOUR PDF ---
CITIES = {
    "Miami": "miami", "LA": "losangeles", "Dallas": "dallas", 
    "Atlanta": "atlanta", "Chicago": "chicago", "San Fran": "sfbay",
    "Houston": "houston", "Phoenix": "phoenix", "Nashville": "nashville"
}

def send_mike_alert(title, link, image_url, city, label):
    url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
    
    # Professional Bold Caption
    emoji = "🛳" if "HIGH" in label else "🪑"
    caption = f"{emoji} <b>{label} ALERT: {city.upper()}</b>\n\n" \
              f"🏷 <b>Item:</b> {title}\n" \
              f"📊 <b>Market:</b> High Demand Area\n\n" \
              f"<i>Scan the listing quickly before it's gone!</i>"
    
    # Inline Button (The "Mike" Look)
    payload = {
        "chat_id": MY_PERSONAL_ID,
        "photo": image_url,
        "caption": caption,
        "parse_mode": "HTML",
        "reply_markup": {"inline_keyboard": [[{"text": "🚀 VIEW DEAL", "url": link}]]}
    }
    
    try:
        requests.post(url, json=payload, timeout=10)
    except:
        # Fallback if photo fails
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                      json={"chat_id": MY_PERSONAL_ID, "text": f"New Deal: {link}", "parse_mode": "HTML"})

def monitor():
    seen = set()
    # INITIAL STARTUP SIGNAL
    start_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(start_url, json={"chat_id": MY_PERSONAL_ID, "text": "🚀 <b>SYSTEM DEPLOYED</b>\nScanning all PDF cities for High & Low Ticket deals...", "parse_mode": "HTML"})
    
    while True:
        city_items = list(CITIES.items())
        random.shuffle(city_items) # Randomized city order
        
        for city_name, sub in city_items:
            # Check both Boat and Furniture feeds
            feeds = [
                (f"🛳 {city_name} HIGH", f"https://{sub}.craigslist.org/search/boo?format=rss&query={BOAT_QUERY}"),
                (f"🪑 {city_name} LOW", f"https://{sub}.craigslist.org/search/fua?format=rss&query={FURN_QUERY}")
            ]
            
            for label, url in feeds:
                try:
                    response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
                    feed = feedparser.parse(response.content)
                    
                    for entry in feed.entries[:2]: # Top 2 most recent
                        if entry.link not in seen:
                            # Extract Image link
                            img = ""
                            if 'links' in entry:
                                for l in entry.links:
                                    if 'image' in l.get('type', ''): img = l.get('href', '')
                            if not img: img = "https://via.placeholder.com/400x300?text=No+Listing+Image"
                            
                            send_mike_alert(entry.title, entry.link, img, city_name, label)
                            seen.add(entry.link)
                            time.sleep(2) # Tiny pause between messages
                except:
                    continue
            
            # Anti-Block Jitter between cities
            time.sleep(random.randint(10, 20))
            
        time.sleep(600) # Wait 10 mins before next full cycle

if __name__ == "__main__":
    monitor()
