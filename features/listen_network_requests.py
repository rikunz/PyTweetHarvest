from playwright.async_api import Page

async def block_media(route):
    url = route.request.url
    if any(ext in url for ext in [".jpg", ".png", ".mp4", "format=jpg"]):
        await route.abort()
    else:
        await route.continue_()

async def listen_network_requests(page: Page, on_timeline):
    async def handle_route(route):
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
