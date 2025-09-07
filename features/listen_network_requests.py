from playwright.async_api import Page
from logging_setup import logger

async def block_media(route):
    url = route.request.url
    
    # Block common media file extensions
    media_extensions = [".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".mp4", ".webm", ".avi", "format=jpg", "format=png"]
    
    # Block Twitter/X media domains and paths
    media_domains = [
        "pbs.twimg.com",
        "video.twimg.com", 
        "abs.twimg.com"
    ]
    
    media_paths = [
        "/media/",
        "/profile_images/",
        "/emoji/",
        "/tweet_video/",
        "/amplify_video/"
        "/ext_tw_video/"
        "/ext_tw_image/"
        "/ext_tw_webp/"
        "/ext_tw_gif/"
        "/ext_tw_svg/"
        "/ext_tw_ico/"
    ]
    
    # Check if URL contains media extensions
    if any(ext in url.lower() for ext in media_extensions):
        await route.abort()
        return
    
    # Check if URL is from media domains
    if any(domain in url for domain in media_domains):
        await route.abort()
        return
        
    # Check if URL contains media paths
    if any(path in url for path in media_paths):
        await route.abort()
        return
    
    # Allow other requests to continue
    await route.continue_()

async def listen_network_requests(page: Page, on_timeline, cache=None):
    """Listen to network requests with optional cache integration"""
    
    if cache:
        logger.debug("Network requests listener with cache integration enabled")
    
    async def handle_route(route):
        url = route.request.url
        
        # Handle caching first if cache is provided
        if cache and cache.should_cache_url(url):
            logger.debug(f"[CACHE] Cacheable request: {url[:80]}...")
            
            # Get cached response if available
            cached_response = cache.get_cached_response(url)
            if cached_response:
                logger.debug(f"[CACHE] Serving from cache: {url[:80]}...")
                await route.fulfill(
                    status=cached_response['status'],
                    headers=cached_response['headers'],
                    body=cached_response['body']
                )
                return
            
            # If not cached, fetch and cache
            logger.debug(f"[CACHE] Fetching and caching: {url[:80]}...")
            try:
                response = await route.fetch()
                body = await response.body()
                headers = response.headers
                status = response.status
                
                # Cache successful responses
                if status == 200:
                    cache.cache_response(url, body, headers, status)
                    logger.debug(f"[CACHE] Cached: {url[:80]}... ({len(body)} bytes)")
                
                await route.fulfill(
                    status=status,
                    headers=headers,
                    body=body
                )
                return
            except Exception as e:
                logger.error(f"[CACHE] Cache operation failed for {url}: {e}")
                # Fall back to blocking media if cache fails
                pass
        
        # Default behavior: block media
        await block_media(route)

    async def handle_response(response):
        url = response.url
        if "SearchTimeline" in url or "TweetDetail" in url:
            try:
                data = await response.json()
            except Exception:
                return
            await on_timeline(data)

    await page.route("**/*", handle_route)
    page.on("response", handle_response)
