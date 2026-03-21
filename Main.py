# ─── CONFIG ───
TOKEN   = "8601205854:AAF5lME-PScrRA__JxfRP1PRJ0bp00IkSBU" 
CHAT_ID = "6549307194"  # <─── UPDATED ID HERE
DB_FILE = "seen_ids.txt"

# ... (keep your other functions as they are) ...

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
                        
                        # Added Try/Except here so a single failed message doesn't kill the bot
                        try:
                            await app.bot.send_message(
                                CHAT_ID, 
                                f"🚗 *NEW {cat_name.upper()}* ({label})\n{entry.title}", 
                                parse_mode="Markdown", 
                                reply_markup=kb
                            )
                        except Exception as send_err:
                            print(f"⚠️ Failed to send message: {send_err}")

                        seen.add(eid)
                        mark_seen(eid)
            except Exception: continue
        await asyncio.sleep(2)
