from seleniumbase import BaseCase
import time

def scroll_up(driver):
    """Scroll to top of page"""
    driver.execute_script("window.scrollTo({top: 0, behavior: 'smooth'})")

def scroll_up_step(driver, times=5, percent=0.9, sleep_time=0.25):
    """
    Scroll ke atas sedikit demi sedikit:
    - times: berapa kali step (default 5x)
    - percent: seberapa besar scroll per step (0.9 = 90% layar)
    - sleep_time: delay antar step (detik)
    """
    last_height = driver.execute_script("return window.scrollY")
    for _ in range(times):
        driver.execute_script(f"window.scrollBy(0, -window.innerHeight*{percent})")
        time.sleep(sleep_time)
        new_height = driver.execute_script("return window.scrollY")
        if new_height == 0 or new_height == last_height:
            break
        last_height = new_height

def scroll_down(driver):
    """
    Scroll smooth langsung ke paling bawah (mentok) dalam 1 langkah.
    """
    driver.execute_script("""
        window.scrollTo({
            top: document.body.scrollHeight,
            left: 0,
            behavior: 'smooth'
        });
    """)
    time.sleep(0.7)
    
    # Remove media elements to reduce memory usage
    driver.execute_script("document.querySelectorAll('div[data-testid=\"tweetPhoto\"]').forEach(el=>el.remove())")
    driver.execute_script("document.querySelectorAll('a div[aria-label=\"Image\"]').forEach(el=>el.remove())")