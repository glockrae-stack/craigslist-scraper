async def main():
    # ... your bot initialization ...
    
    # Start the health server in the background
    runner = await setup_health_server() 
    
    while True:
        print(f"🔍 Scanning Craigslist at {datetime.now()}...")
        try:
            # Your scraping and sending logic here
            await scrape_and_notify() 
        except Exception as e:
            print(f"⚠️ Scan error: {e}")
            
        # Wait 10 minutes before scanning again
        await asyncio.sleep(600)
