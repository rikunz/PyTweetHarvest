from playwright.async_api import Page
import asyncio

async def scroll_up(page: Page):
    await page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")

async def scroll_up_step(page, times=5, percent=0.9, sleep_time=0.25):
    """
    Scroll ke atas sedikit demi sedikit:
    - times: berapa kali step (default 2x, biasanya cukup buat naik 1-2 tweet)
    - percent: seberapa besar scroll per step (0.8 = 80% layar)
    - sleep_time: delay antar step (detik)
    """
    last_height = await page.evaluate("window.scrollY")
    for _ in range(times):
        await page.evaluate(f"window.scrollBy(0, -window.innerHeight*{percent})")
        await asyncio.sleep(sleep_time)
        new_height = await page.evaluate("window.scrollY")
        if new_height == 0 or new_height == last_height:
            break
        last_height = new_height

async def scroll_down(page):
    """
    Scroll smooth langsung ke paling bawah (mentok) dalam 1 langkah.
    """
    await page.evaluate("""
        window.scrollTo({
            top: document.body.scrollHeight,
            left: 0,
            behavior: 'smooth'
        });
    """)
    await asyncio.sleep(0.7)  
    await page.evaluate("document.querySelectorAll('div[data-testid=\\'tweetPhoto\\']').forEach(el=>el.remove())")
    await page.evaluate("document.querySelectorAll('a div[aria-label=\\'Image\\']').forEach(el=>el.remove())")