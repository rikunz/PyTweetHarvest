from playwright.async_api import Page

async def scroll_up(page: Page):
    await page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")

async def scroll_down(page: Page):
    await page.evaluate(
        "window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'})"
    )
    # Remove images to speed up
    await page.evaluate("document.querySelectorAll('div[data-testid=\\'tweetPhoto\\']').forEach(el=>el.remove())")
    await page.evaluate("document.querySelectorAll('a div[aria-label=\\'Image\\']').forEach(el=>el.remove())")

