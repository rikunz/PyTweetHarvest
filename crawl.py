import asyncio
import io
from pathlib import Path
import pandas as pd
from logging_setup import logger

from playwright.async_api import async_playwright

from constants import (
    TWITTER_SEARCH_ADVANCED_URL,
    NOW,
    FOLDER_DESTINATION,
    FILTERED_FIELDS,
)
from env import HEADLESS_MODE
from features.input_keywords import input_keywords
from features.listen_network_requests import listen_network_requests
from helpers.page_helper import scroll_down, scroll_up_step
from features.exponential_backoff import calculate_for_rate_limit
import re

# --- PATCH: Helper tunggu response via event ---
async def wait_for_response_url(page, keywords, timeout=6000):
    """
    Wait for a response whose URL contains any of the keywords (as regex substr).
    Timeout in ms (default 3 seconds).
    """
    future = asyncio.get_event_loop().create_future()
    def on_response(response):
        for key in keywords:
            if re.search(key, response.url):
                page.remove_listener("response", on_response)
                if not future.done():
                    future.set_result(response)
    page.on("response", on_response)
    try:
        return await asyncio.wait_for(future, timeout=timeout/1000)
    except asyncio.TimeoutError:
        page.remove_listener("response", on_response)
        return None

async def crawl(
    *,
    access_token: str,
    search_keywords: str = None,
    tweet_thread_url: str = None,
    search_from_date: str = None,
    search_to_date: str = None,
    target_tweet_count: int = 10,
    delay_each_tweet_seconds: int = 3,
    delay_every_100_tweets_seconds: int = 10,
    debug_mode: bool = False,
    output_filename: str = None,
    search_tab: str = "LATEST",
    csv_insert_mode: str = "REPLACE",
):
    crawl_mode = "DETAIL" if tweet_thread_url else "SEARCH"
    is_detail_mode = crawl_mode == "DETAIL"
    is_search_mode = crawl_mode == "SEARCH"

    filename = (output_filename or f"{search_keywords} {NOW}").strip().replace(".csv", "")
    file_path = Path(FOLDER_DESTINATION) / f"{filename}.csv"
    file_path = Path(str(file_path).replace(" ", "_").replace(":", "-"))
    file_path.parent.mkdir(parents=True, exist_ok=True)

    tweets = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            screen={"width": 1240, "height": 1080},
            storage_state={
                "cookies": [
                    {
                        "name": "auth_token",
                        "value": access_token,
                        "domain": "x.com",
                        "path": "/",
                        "expires": -1,
                        "httpOnly": True,
                        "secure": True,
                        "sameSite": "Strict",
                    }
                ],
                "origins": [],
            },
        )
        page = await context.new_page()
        page.set_default_timeout(60 * 1000)
        timeline_data = []

        async def on_timeline(data):
            timeline_data.append(data)
        await listen_network_requests(page, on_timeline)

        async def start_crawl(twitter_search_url=None):
            if twitter_search_url is None:
                twitter_search_url = TWITTER_SEARCH_ADVANCED_URL[search_tab]
            logger.info("Starting crawl, mode: %s, tab: %s", crawl_mode, search_tab)

            if is_detail_mode:
                await page.goto(tweet_thread_url)
                logger.info("Goto thread URL: %s", tweet_thread_url)
            else:
                await page.goto(twitter_search_url)
                logger.info("Goto search URL: %s", twitter_search_url)

            if "/login" in page.url:
                logger.error("Invalid twitter auth token, redirected to login.")
                return

            if is_search_mode:
                logger.info("Inputting keywords & filters.")
                await input_keywords(
                    page,
                    search_keywords=search_keywords,
                    from_date=search_from_date,
                    to_date=search_to_date,
                )

            timeout_count = 0
            additional_tweets = 0
            rate_limit_count = 0
            last_len = 0

            async def scroll_and_save():
                nonlocal timeout_count, additional_tweets, rate_limit_count, last_len
                logger.info("Start crawling and scrolling.")
                while len(tweets) < target_tweet_count and timeout_count < 20:
                    if page.is_closed():
                        logger.warning("Page closed unexpectedly, breaking loop.")
                        break
                    try:
                        logger.debug("Waiting for timeline response...")
                        response = await wait_for_response_url(
                            page, [r"SearchTimeline", r"TweetDetail"], timeout=6000
                        )
                        if response is None:
                            timeout_count += 1
                            logger.info("Timeout waiting for response (%d/10), scrolling down.", timeout_count)
                            await scroll_up_step(page)
                            await scroll_down(page)
                            await asyncio.sleep(0.7)
                            if timeout_count >= 10:
                                logger.error("Too many timeouts, aborting scroll_and_save.")
                                break
                            continue
                        timeout_count = 0
                        try:
                            data = await response.json()
                        except Exception:
                            try:
                                text = await response.text()
                            except Exception:
                                text = ""
                            if "rate limit" in text.lower():
                                logger.warning("Rate limited. Backing off %d ms, count %d.",
                                               calculate_for_rate_limit(rate_limit_count), rate_limit_count)
                                await page.wait_for_timeout(
                                    calculate_for_rate_limit(rate_limit_count)
                                )
                                rate_limit_count += 1
                                try:
                                    await page.click("text=Retry")
                                    logger.info("Clicked retry after rate limit.")
                                except Exception:
                                    logger.warning("Failed to click retry after rate limit.")
                                continue
                            logger.error("Unknown response exception, breaking.")
                            break

                        rate_limit_count = 0
                        entries = []
                        if data.get("data", {}).get("threaded_conversation_with_injections_v2"):
                            entries = (
                                data["data"]["threaded_conversation_with_injections_v2"]["instructions"][0]["entries"]
                            )
                        else:
                            entries = (
                                data.get("data", {})
                                .get("search_by_raw_query", {})
                                .get("search_timeline", {})
                                .get("timeline", {})
                                .get("instructions", [{}])[0]
                                .get("entries", [])
                            )
                        for entry in entries:
                            content = entry.get("content", {})
                            if is_search_mode:
                                item = (
                                    content.get("itemContent", {})
                                    or content.get("item", {}).get("itemContent", {})
                                )
                            else:
                                items = content.get("items", [])
                                if not items:
                                    continue
                                item = items[0].get("item", {}).get("itemContent", {})
                            result = (
                                item.get("tweet_results", {})
                                .get("result")
                            )
                            if not result:
                                continue
                            legacy = result.get("legacy") or result.get("tweet", {}).get("legacy")
                            user_legacy = (
                                result.get("core", {})
                                .get("user_results", {})
                                .get("result", {})
                                .get("legacy")
                            )
                            user_core = result.get("core").get("user_results", {}).get("result", {}).get("core", {})
                            if not legacy or not user_legacy:
                                continue
                            row = {
                                **{k: legacy.get(k, "") for k in FILTERED_FIELDS if k in legacy},
                                "username": user_core.get("screen_name", None),
                                "tweet_url": f"https://x.com/{user_legacy.get('screen_name')}/status/{legacy.get('id_str')}",
                                "image_url": legacy.get("entities", {}).get("media", [{}])[0].get("media_url_https", ""),
                                "location": user_legacy.get("location", ""),
                                "in_reply_to_screen_name": legacy.get("in_reply_to_screen_name", ""),
                            }
                            tweets.append(row)
                            additional_tweets += 1
                            # Logging progress every 10 tweets
                            if len(tweets) % 10 == 0 and len(tweets) != last_len:
                                logger.info("Crawled %d tweets...", len(tweets))
                                last_len = len(tweets)
                            if len(tweets) >= target_tweet_count:
                                logger.info("Target tweet count reached (%d)", len(tweets))
                                break
                        await scroll_up_step(page)
                        await scroll_down(page)
                        await asyncio.sleep(0.7)
                        logger.debug("Scrolled down for more tweets. Now at %d tweets.", len(tweets))
                        if additional_tweets > 20:
                            logger.info("Waiting %d seconds after crawling %d tweets.", delay_each_tweet_seconds, additional_tweets)
                            await page.wait_for_timeout(delay_each_tweet_seconds * 1000)
                            additional_tweets = 0
                    except Exception as e:
                        logger.error(f"Exception in scroll_and_save: {e}")
                        break
            await scroll_and_save()

            if tweets:
                df = pd.DataFrame(tweets)
                df.to_csv(file_path, index=False, encoding="utf-8")
                logger.info("Saved %d tweets to %s", len(tweets), file_path)
            else:
                logger.warning("No tweets crawled.")

        try:
            await start_crawl()
        except Exception as e:
            logger.error(f"Error in start_crawl: {e}")
        finally:
            try:
                await browser.close()
            except Exception:
                logger.warning("Browser already closed or failed to close.")

    logger.info("Crawl finished, result file: %s", file_path)
    return file_path

async def crawl_buffer(
    *,
    access_token: str,
    search_keywords: str = None,
    tweet_thread_url: str = None,
    search_from_date: str = None,
    search_to_date: str = None,
    target_tweet_count: int = 10,
    delay_each_tweet_seconds: int = 3,
    delay_every_100_tweets_seconds: int = 10,
    debug_mode: bool = False,
    search_tab: str = "LATEST",
    csv_insert_mode: str = "REPLACE",
) -> io.StringIO:
    """Crawl tweets but return the CSV data as an in-memory buffer."""
    crawl_mode = "DETAIL" if tweet_thread_url else "SEARCH"
    is_detail_mode = crawl_mode == "DETAIL"
    is_search_mode = crawl_mode == "SEARCH"

    buffer = io.StringIO()
    tweets = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS_MODE)
        context = await browser.new_context(
            screen={"width": 1240, "height": 1080},
            storage_state={
                "cookies": [
                    {
                        "name": "auth_token",
                        "value": access_token,
                        "domain": "x.com",
                        "path": "/",
                        "expires": -1,
                        "httpOnly": True,
                        "secure": True,
                        "sameSite": "Strict",
                    }
                ],
                "origins": [],
            },
        )
        page = await context.new_page()
        page.set_default_timeout(60 * 1000)
        timeline_data = []

        async def on_timeline(data):
            timeline_data.append(data)
        await listen_network_requests(page, on_timeline)

        async def start_crawl(twitter_search_url=None):
            if twitter_search_url is None:
                twitter_search_url = TWITTER_SEARCH_ADVANCED_URL[search_tab]
            logger.info("Starting crawl, mode: %s, tab: %s", crawl_mode, search_tab)

            if is_detail_mode:
                await page.goto(tweet_thread_url)
                logger.info("Goto thread URL: %s", tweet_thread_url)
            else:
                await page.goto(twitter_search_url)
                logger.info("Goto search URL: %s", twitter_search_url)

            # Early exit jika token invalid
            if "/login" in page.url:
                logger.error("Invalid twitter auth token, redirected to login.")
                return

            if is_search_mode:
                logger.info("Inputting keywords & filters.")
                await input_keywords(
                    page,
                    search_keywords=search_keywords,
                    from_date=search_from_date,
                    to_date=search_to_date,
                )

            timeout_count = 0
            additional_tweets = 0
            rate_limit_count = 0
            last_len = 0

            async def scroll_and_save():
                nonlocal timeout_count, additional_tweets, rate_limit_count, last_len
                logger.info("Start crawling and scrolling.")
                while len(tweets) < target_tweet_count and timeout_count < 20:
                    if page.is_closed():
                        logger.warning("Page closed unexpectedly, breaking loop.")
                        break
                    try:
                        logger.debug("Waiting for timeline response...")
                        response = await wait_for_response_url(
                            page, [r"SearchTimeline", r"TweetDetail"], timeout=6000
                        )
                        if response is None:
                            timeout_count += 1
                            logger.info("Timeout waiting for response (%d/10), scrolling down.", timeout_count)
                            await scroll_up_step(page)
                            await scroll_down(page)
                            await asyncio.sleep(0.7)
                            if timeout_count >= 10:
                                logger.error("Too many timeouts, aborting scroll_and_save.")
                                break
                            continue
                        timeout_count = 0
                        try:
                            data = await response.json()
                        except Exception:
                            try:
                                text = await response.text()
                            except Exception:
                                text = ""
                            if "rate limit" in text.lower():
                                logger.warning("Rate limited. Backing off %d ms, count %d.",
                                               calculate_for_rate_limit(rate_limit_count), rate_limit_count)
                                await page.wait_for_timeout(
                                    calculate_for_rate_limit(rate_limit_count)
                                )
                                rate_limit_count += 1
                                try:
                                    await page.click("text=Retry")
                                    logger.info("Clicked retry after rate limit.")
                                except Exception:
                                    logger.warning("Failed to click retry after rate limit.")
                                continue
                            logger.error("Unknown response exception, breaking.")
                            break

                        rate_limit_count = 0
                        entries = []
                        if data.get("data", {}).get("threaded_conversation_with_injections_v2"):
                            entries = (
                                data["data"]["threaded_conversation_with_injections_v2"]["instructions"][0]["entries"]
                            )
                        else:
                            entries = (
                                data.get("data", {})
                                .get("search_by_raw_query", {})
                                .get("search_timeline", {})
                                .get("timeline", {})
                                .get("instructions", [{}])[0]
                                .get("entries", [])
                            )
                        for entry in entries:
                            content = entry.get("content", {})
                            if is_search_mode:
                                item = (
                                    content.get("itemContent", {})
                                    or content.get("item", {}).get("itemContent", {})
                                )
                            else:
                                items = content.get("items", [])
                                if not items:
                                    continue
                                item = items[0].get("item", {}).get("itemContent", {})
                            result = (
                                item.get("tweet_results", {})
                                .get("result")
                            )
                            if not result:
                                continue
                            legacy = result.get("legacy") or result.get("tweet", {}).get("legacy")
                            user_legacy = (
                                result.get("core", {})
                                .get("user_results", {})
                                .get("result", {})
                                .get("legacy")
                            )
                            if not legacy or not user_legacy:
                                continue
                            row = {
                                **{k: legacy.get(k, "") for k in FILTERED_FIELDS if k in legacy},
                                "username": user_legacy.get("screen_name", ""),
                                "tweet_url": f"https://x.com/{user_legacy.get('screen_name')}/status/{legacy.get('id_str')}",
                                "image_url": legacy.get("entities", {}).get("media", [{}])[0].get("media_url_https", ""),
                                "location": user_legacy.get("location", ""),
                                "in_reply_to_screen_name": legacy.get("in_reply_to_screen_name", ""),
                            }
                            tweets.append(row)
                            additional_tweets += 1
                            # Logging progress every 10 tweets
                            if len(tweets) % 10 == 0 and len(tweets) != last_len:
                                logger.info("Crawled %d tweets...", len(tweets))
                                last_len = len(tweets)
                            if len(tweets) >= target_tweet_count:
                                logger.info("Target tweet count reached (%d)", len(tweets))
                                break
                        await scroll_up_step(page)
                        await scroll_down(page)
                        await asyncio.sleep(0.7)
                        logger.debug("Scrolled down for more tweets. Now at %d tweets.", len(tweets))
                        if additional_tweets > 20:
                            logger.info("Waiting %d seconds after crawling %d tweets.", delay_each_tweet_seconds, additional_tweets)
                            await page.wait_for_timeout(delay_each_tweet_seconds * 1000)
                            additional_tweets = 0
                    except Exception as e:
                        logger.error(f"Exception in scroll_and_save: {e}")
                        break
            await scroll_and_save()

            if tweets:
                df = pd.DataFrame(tweets)
                df.to_csv(buffer, index=False, encoding="utf-8")
                logger.info("Writing %d tweets to buffer.", len(tweets))
                buffer.seek(0)
            else:
                logger.warning("No tweets crawled.")

        try:
            await start_crawl()
        except Exception as e:
            logger.error(f"Error in start_crawl: {e}")
        finally:
            try:
                await browser.close()
            except Exception:
                logger.warning("Browser already closed or failed to close.")

    buffer.seek(0)
    logger.info("Crawl buffer finished.")
    return buffer

