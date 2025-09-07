import asyncio
from playwright.async_api import async_playwright
from features.cache_system import PlaywrightCache, setup_cache_interceptor
from logging_setup import logger

async def test_twitter_cache():
    """Test cache system dengan mengunjungi Twitter (tanpa login)"""
    
    cache = PlaywrightCache(cache_dir="twitter_test_cache")
    logger.info("Starting Twitter cache system test...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        await setup_cache_interceptor(page, cache)
        
        logger.info("Visiting Twitter/X.com...")
        try:
            await page.goto("https://x.com", timeout=30000)
            
            await page.wait_for_timeout(5000)
            
            stats = cache.get_cache_stats()
            logger.info(f"Twitter cache stats: {stats}")
            
        except Exception as e:
            logger.error(f"Error accessing Twitter: {e}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_twitter_cache())
