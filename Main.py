# ─────────────────────────────────────────────
# OFFERUP LOOP — FRESH LISTINGS ONLY
# ─────────────────────────────────────────────
import datetime
import json

async def fetch_ou_feed(client: httpx.AsyncClient, slug: str, category: str) -> list:
    """
    Fetches OfferUp listings for a city and category.
    Returns a list of dicts: {'title', 'link', 'price', 'timestamp'}
    """
    url = f"https://offerup.com/api/1/items/?location={slug}&q={category}&delivery_param=p&sort=-p"
    try:
        resp = await client.get(url, timeout=15)
        if resp.status_code != 200:
            return []

        data = resp.json()
        items = []

        for item in data.get("items", []):
            title = item.get("title", "").strip()
            if not title:
                continue

            # Only get actual listing links
            link = f"https://offerup.com/item/{item.get('id')}/"
            price = f"${item.get('price', 0)}" if item.get('price') else ""
            
            # convert timestamp to datetime
            ts = item.get("created_at")  # unix timestamp
            if ts:
                timestamp = datetime.datetime.utcfromtimestamp(ts)
            else:
                timestamp = datetime.datetime.utcnow()  # fallback

            items.append({
                "title": title,
                "link": link,
                "price": price,
                "timestamp": timestamp
            })

        return items

    except Exception as e:
        log.warning("OfferUp fetch failed [%s | %s]: %s", slug, category, e)
        return []

# ─────────────────────────────────────────────
# OFFERUP WAVE LOOP
# ─────────────────────────────────────────────
async def offerup_wave(app):
    MAX_AGE = datetime.timedelta(minutes=40)
    async with httpx.AsyncClient() as client:
        while True:
            for city_label, slug in OU_CITIES.items():
                for cat_query, cat_title in OU_CATEGORIES.items():
                    items = await fetch_ou_feed(client, slug, cat_query)

                    for item in items:
                        # skip old listings
                        if datetime.datetime.utcnow() - item["timestamp"] > MAX_AGE:
                            continue

                        # dedupe
                        title_key = re.sub(r'[^a-z0-9]', '', item["title"].lower())
                        alert_id = f"ou_{slug}_{cat_query}_{title_key}"
                        if alert_id in seen_ids:
                            continue
                        seen_ids.add(alert_id)
                        mark_seen(alert_id)

                        # send alert
                        await send_alert(
                            app,
                            f"{cat_title} — {city_label}: {item['title']}",
                            item['link'],
                            city_label,
                            item['price'],
                            priority=True  # everything recent is priority
                        )
                        await asyncio.sleep(random.uniform(2, 4))

            # After full cycle, clean old OU keys to allow reposts
            ou_keys = [k for k in seen_ids if k.startswith("ou_")]
            for k in ou_keys:
                # keep only the last 40 mins
                pass  # optional: implement expiration if needed
            log.info("📲 OU cycle done. Sleeping 300s...")
            await asyncio.sleep(300)
