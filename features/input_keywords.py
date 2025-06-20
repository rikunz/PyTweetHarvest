from playwright.async_api import Page

async def input_keywords(page: Page, *, search_keywords: str = "", from_date: str = None, to_date: str = None):
    await page.wait_for_selector('input[name="allOfTheseWords"]', state='visible')
    await page.click('input[name="allOfTheseWords"]')

    modified_keywords = search_keywords or ""

    if from_date:
        day, month, year = from_date.split(" ")[0].split("-")
        modified_keywords += f" since:{year}-{month}-{day}"
    if to_date:
        day, month, year = to_date.split(" ")[0].split("-")
        modified_keywords += f" until:{year}-{month}-{day}"

    await page.fill('input[name="allOfTheseWords"]', modified_keywords)
    await page.press('input[name="allOfTheseWords"]', "Enter")

    return modified_keywords
