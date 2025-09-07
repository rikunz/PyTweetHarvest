import io
import json
import re
import time
from pathlib import Path
import pandas as pd
from typing import Optional
from logging_setup import logger
from seleniumbase import SB
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from constants import (
    TWITTER_SEARCH_ADVANCED_URL,
    NOW,
    FOLDER_DESTINATION,
    FILTERED_FIELDS,
)
from env import HEADLESS_MODE
from features.input_keywords import input_keywords
from helpers.page_helper import scroll_down, scroll_up_step
from features.exponential_backoff import calculate_for_rate_limit

# Global variables for tracking
response_data = []
blocked_requests = 0

def wait_for_response_url(driver, keywords, timeout=6000):
    """
    Modified for SeleniumBase: Wait for tweet elements to load on the page
    instead of waiting for network responses.
    """
    start_time = time.time()
    
    while time.time() - start_time < timeout/1000:
        try:
            # Check if tweet elements are present
            tweets = driver.find_elements(By.CSS_SELECTOR, '[data-testid="tweet"]')
            if tweets and len(tweets) > 0:
                # Return a mock response indicating success
                return {"success": True, "tweet_count": len(tweets)}
        except:
            pass
        time.sleep(0.5)
    
    return None

def set_twitter_auth(driver, access_token):
    """Set Twitter authentication cookie"""
    driver.execute_script(f"""
        document.cookie = 'auth_token={access_token}; domain=.x.com; path=/; secure; samesite=strict';
    """)
    logger.info("Twitter auth token set")

def extract_tweets_from_dom(driver, existing_tweets):
    """Extract tweet data from DOM elements"""
    new_tweets = []
    
    try:
        # Find all tweet elements on the page
        tweet_elements = driver.find_elements(By.CSS_SELECTOR, '[data-testid="tweet"]')
        
        for tweet_elem in tweet_elements:
            try:
                # Extract tweet text
                text_elements = tweet_elem.find_elements(By.CSS_SELECTOR, '[data-testid="tweetText"]')
                full_text = text_elements[0].text if text_elements else ""
                
                # Skip if we already have this tweet
                if any(t.get("full_text") == full_text for t in existing_tweets if full_text):
                    continue
                
                # Extract username
                username_elements = tweet_elem.find_elements(By.CSS_SELECTOR, '[data-testid="User-Name"] a')
                username = ""
                if username_elements:
                    href = username_elements[0].get_attribute("href")
                    if href and "x.com/" in href:
                        username = href.split("x.com/")[-1]
                
                # Extract timestamp
                time_elements = tweet_elem.find_elements(By.CSS_SELECTOR, 'time')
                created_at = time_elements[0].get_attribute("datetime") if time_elements else ""
                
                # Extract tweet ID from URL if available
                tweet_id = ""
                id_elements = tweet_elem.find_elements(By.CSS_SELECTOR, 'a[href*="/status/"]')
                if id_elements:
                    href = id_elements[0].get_attribute("href")
                    if "/status/" in href:
                        tweet_id = href.split("/status/")[-1].split("?")[0]
                
                # Create simplified tweet row
                row = {
                    "full_text": full_text,
                    "username": username,
                    "created_at": created_at,
                    "id_str": tweet_id,
                    "tweet_url": f"https://x.com/{username}/status/{tweet_id}" if username and tweet_id else "",
                    "image_url": "",  # Will extract later if needed
                    "location": "",
                    "in_reply_to_screen_name": "",
                    "retweet_count": 0,
                    "favorite_count": 0,
                    "reply_count": 0,
                }
                
                # Only add if we have meaningful content
                if full_text.strip():
                    new_tweets.append(row)
                    
            except Exception as e:
                logger.debug(f"Error extracting tweet data: {e}")
                continue
                
    except Exception as e:
        logger.error(f"Error finding tweet elements: {e}")
    
    return new_tweets

def crawl(
    *,
    access_token: str,
    search_keywords: Optional[str] = None,
    tweet_thread_url: Optional[str] = None,
    search_from_date: Optional[str] = None,
    search_to_date: Optional[str] = None,
    target_tweet_count: int = 10,
    delay_each_tweet_seconds: int = 3,
    delay_every_100_tweets_seconds: int = 10,
    debug_mode: bool = False,
    output_filename: Optional[str] = None,
    search_tab: str = "TOP",
    csv_insert_mode: str = "REPLACE",
):
    global response_data, blocked_requests
    response_data = []  # Reset global response data
    blocked_requests = 0  # Reset blocked requests counter
    
    crawl_mode = "DETAIL" if tweet_thread_url else "SEARCH"
    is_detail_mode = crawl_mode == "DETAIL"
    is_search_mode = crawl_mode == "SEARCH"

    filename = (output_filename or f"{search_keywords} {NOW}").strip().replace(".csv", "")
    file_path = Path(FOLDER_DESTINATION) / f"{filename}.csv"
    file_path = Path(str(file_path).replace(" ", "_").replace(":", "-"))
    file_path.parent.mkdir(parents=True, exist_ok=True)

    tweets = []

    # Use SeleniumBase with UC mode
    with SB(uc=True, headless=HEADLESS_MODE) as driver:
        try:
            logger.info("SeleniumBase driver started with UC mode")
            
            # Set authentication
            set_twitter_auth(driver, access_token)
            
            # Navigate to target URL
            if is_detail_mode and tweet_thread_url:
                driver.open(tweet_thread_url)
                logger.info("Goto thread URL: %s", tweet_thread_url)
            else:
                twitter_search_url = TWITTER_SEARCH_ADVANCED_URL[search_tab]
                driver.open(twitter_search_url)
                logger.info("Goto search URL: %s", twitter_search_url)

            # Check if redirected to login
            if "/login" in driver.get_current_url():
                logger.error("Invalid twitter auth token, redirected to login.")
                return file_path

            # Input search keywords and filters
            if is_search_mode and search_keywords:
                logger.info("Inputting keywords & filters.")
                input_keywords(
                    driver,
                    search_keywords=search_keywords,
                    from_date=search_from_date,
                    to_date=search_to_date,
                )

            timeout_count = 0
            additional_tweets = 0
            last_len = 0

            def scroll_and_save():
                nonlocal timeout_count, additional_tweets, last_len
                logger.info("Start crawling and scrolling.")
                
                while len(tweets) < target_tweet_count and timeout_count < 20:
                    try:
                        logger.debug("Waiting for timeline response...")
                        response = wait_for_response_url(
                            driver, [r"SearchTimeline", r"TweetDetail"], timeout=6000
                        )
                        
                        if response is None:
                            timeout_count += 1
                            logger.info("Timeout waiting for response (%d/10), scrolling down.", timeout_count)
                            scroll_up_step(driver)
                            scroll_down(driver)
                            time.sleep(0.7)
                            if timeout_count >= 10:
                                logger.error("Too many timeouts, aborting scroll_and_save.")
                                break
                            continue
                            
                        timeout_count = 0
                        
                        # Extract tweets using DOM scraping
                        new_tweets = extract_tweets_from_dom(driver, tweets)
                        
                        for tweet in new_tweets:
                            tweets.append(tweet)
                            additional_tweets += 1
                            
                            # Logging progress every 10 tweets
                            if len(tweets) % 10 == 0 and len(tweets) != last_len:
                                logger.info("Crawled %d tweets...", len(tweets))
                                last_len = len(tweets)
                            if len(tweets) >= target_tweet_count:
                                logger.info("Target tweet count reached (%d)", len(tweets))
                                break
                                
                        if len(tweets) >= target_tweet_count:
                            break
                            
                        scroll_up_step(driver)
                        scroll_down(driver)
                        time.sleep(0.7)
                        logger.debug("Scrolled down for more tweets. Now at %d tweets.", len(tweets))
                        
                        if additional_tweets > 20:
                            logger.info("Waiting %d seconds after crawling %d tweets.", delay_each_tweet_seconds, additional_tweets)
                            time.sleep(delay_each_tweet_seconds)
                            additional_tweets = 0
                            
                    except Exception as e:
                        logger.error(f"Exception in scroll_and_save: {e}")
                        break
                        
            scroll_and_save()

            if tweets:
                df = pd.DataFrame(tweets)
                df.to_csv(file_path, index=False, encoding="utf-8")
                logger.info("Saved %d tweets to %s", len(tweets), file_path)
            else:
                logger.warning("No tweets crawled.")

        except Exception as e:
            logger.error(f"Error in crawl: {e}")

    logger.info("Crawl finished, result file: %s", file_path)
    return file_path

def crawl_buffer(
    *,
    access_token: str,
    search_keywords: Optional[str] = None,
    tweet_thread_url: Optional[str] = None,
    search_from_date: Optional[str] = None,
    search_to_date: Optional[str] = None,
    target_tweet_count: int = 10,
    delay_each_tweet_seconds: int = 3,
    delay_every_100_tweets_seconds: int = 10,
    debug_mode: bool = False,
    search_tab: str = "TOP",
    csv_insert_mode: str = "REPLACE",
) -> io.StringIO:
    """Crawl tweets but return the CSV data as an in-memory buffer using SeleniumBase."""
    global response_data, blocked_requests
    response_data = []  # Reset global response data
    blocked_requests = 0  # Reset blocked requests counter
    
    crawl_mode = "DETAIL" if tweet_thread_url else "SEARCH"
    is_detail_mode = crawl_mode == "DETAIL"
    is_search_mode = crawl_mode == "SEARCH"

    buffer = io.StringIO()
    tweets = []

    # Use SeleniumBase with UC mode
    with SB(uc=True, headless=True) as driver:  # Always headless for buffer mode
        try:
            logger.info("SeleniumBase driver started with UC mode for buffer")
            
            # Set authentication
            set_twitter_auth(driver, access_token)
            
            # Navigate to target URL
            if is_detail_mode and tweet_thread_url:
                driver.open(tweet_thread_url)
                logger.info("Goto thread URL: %s", tweet_thread_url)
            else:
                twitter_search_url = TWITTER_SEARCH_ADVANCED_URL[search_tab]
                driver.open(twitter_search_url)
                logger.info("Goto search URL: %s", twitter_search_url)

            # Check if redirected to login
            if "/login" in driver.get_current_url():
                logger.error("Invalid twitter auth token, redirected to login.")
                return buffer

            # Input search keywords and filters
            if is_search_mode and search_keywords:
                logger.info("Inputting keywords & filters.")
                input_keywords(
                    driver,
                    search_keywords=search_keywords,
                    from_date=search_from_date,
                    to_date=search_to_date,
                )

            timeout_count = 0
            additional_tweets = 0
            last_len = 0

            def scroll_and_save():
                nonlocal timeout_count, additional_tweets, last_len
                logger.info("Start crawling and scrolling.")
                
                while len(tweets) < target_tweet_count and timeout_count < 20:
                    try:
                        logger.debug("Waiting for timeline response...")
                        response = wait_for_response_url(
                            driver, [r"SearchTimeline", r"TweetDetail"], timeout=6000
                        )
                        
                        if response is None:
                            timeout_count += 1
                            logger.info("Timeout waiting for response (%d/10), scrolling down.", timeout_count)
                            scroll_up_step(driver)
                            scroll_down(driver)
                            time.sleep(0.7)
                            if timeout_count >= 10:
                                logger.error("Too many timeouts, aborting scroll_and_save.")
                                break
                            continue
                            
                        timeout_count = 0
                        
                        # Extract tweets using DOM scraping
                        new_tweets = extract_tweets_from_dom(driver, tweets)
                        
                        for tweet in new_tweets:
                            tweets.append(tweet)
                            additional_tweets += 1
                            
                            # Logging progress every 10 tweets
                            if len(tweets) % 10 == 0 and len(tweets) != last_len:
                                logger.info("Crawled %d tweets...", len(tweets))
                                last_len = len(tweets)
                            if len(tweets) >= target_tweet_count:
                                logger.info("Target tweet count reached (%d)", len(tweets))
                                break
                                
                        if len(tweets) >= target_tweet_count:
                            break
                            
                        scroll_up_step(driver)
                        scroll_down(driver)
                        time.sleep(0.7)
                        logger.debug("Scrolled down for more tweets. Now at %d tweets.", len(tweets))
                        
                        if additional_tweets > 20:
                            logger.info("Waiting %d seconds after crawling %d tweets.", delay_each_tweet_seconds, additional_tweets)
                            time.sleep(delay_each_tweet_seconds)
                            additional_tweets = 0
                            
                    except Exception as e:
                        logger.error(f"Exception in scroll_and_save: {e}")
                        break
                        
            scroll_and_save()

            if tweets:
                df = pd.DataFrame(tweets)
                df.to_csv(buffer, index=False, encoding="utf-8")
                logger.info("Writing %d tweets to buffer.", len(tweets))
                buffer.seek(0)
            else:
                logger.warning("No tweets crawled.")

        except Exception as e:
            logger.error(f"Error in crawl_buffer: {e}")

    buffer.seek(0)
    logger.info("Crawl buffer finished.")
    return buffer
