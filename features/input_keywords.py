from seleniumbase import BaseCase
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from typing import Optional
import time

def input_keywords(driver, *, search_keywords: str = "", from_date: Optional[str] = None, to_date: Optional[str] = None):
    """Input search keywords and date filters for SeleniumBase"""
    # Wait for the search input to be visible
    WebDriverWait(driver.driver, 10).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, 'input[name="allOfTheseWords"]'))
    )
    
    # Click on the search input
    driver.click('input[name="allOfTheseWords"]')
    
    modified_keywords = search_keywords or ""

    # Add date filters to keywords
    if from_date:
        day, month, year = from_date.split(" ")[0].split("-")
        modified_keywords += f" since:{year}-{month}-{day}"
    if to_date:
        day, month, year = to_date.split(" ")[0].split("-")
        modified_keywords += f" until:{year}-{month}-{day}"

    # Clear and type the modified keywords
    driver.clear('input[name="allOfTheseWords"]')
    driver.type('input[name="allOfTheseWords"]', modified_keywords)
    
    # Press Enter to submit
    search_input = driver.find_element(By.CSS_SELECTOR, 'input[name="allOfTheseWords"]')
    search_input.send_keys(Keys.ENTER)
    
    time.sleep(2)  # Wait for search to process
    
    return modified_keywords
