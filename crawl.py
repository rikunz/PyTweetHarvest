import asyncio
import csv
import json
import os
from pathlib import Path

from playwright.async_api import async_playwright

from .constants import (
    TWITTER_SEARCH_ADVANCED_URL,
    NOW,
    FOLDER_DESTINATION,
    FILTERED_FIELDS,
)
from .env import HEADLESS_MODE
from .features.input_keywords import input_keywords
from .features.listen_network_requests import listen_network_requests
from .helpers.page_helper import scroll_down, scroll_up
from .features.exponential_backoff import calculate_for_rate_limit


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
    switched_search_tab = "LATEST" if search_tab == "TOP" else "TOP"

    is_detail_mode = crawl_mode == "DETAIL"
    is_search_mode = crawl_mode == "SEARCH"

    filename = (output_filename or f"{search_keywords} {NOW}").strip().replace(
        ".csv", ""
    )
    file_path = Path(FOLDER_DESTINATION) / f"{filename}.csv"
    file_path = Path(str(file_path).replace(" ", "_").replace(":", "-"))

    file_path.parent.mkdir(parents=True, exist_ok=True)

    tweets = []
    header_written = False

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

            if is_detail_mode:
                await page.goto(tweet_thread_url)
            else:
                await page.goto(twitter_search_url)

            if page.url.find("/login") != -1:
                print("Invalid twitter auth token")
                return

            if is_search_mode:
                await input_keywords(
                    page,
                    search_keywords=search_keywords,
                    from_date=search_from_date,
                    to_date=search_to_date,
                )

            timeout_count = 0
            additional_tweets = 0
            rate_limit_count = 0

            async def write_csv(rows):
                nonlocal header_written
                with open(file_path, "a", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                    if not header_written:
                        writer.writeheader()
                        header_written = True
                    writer.writerows(rows)

            async def scroll_and_save():
                nonlocal timeout_count, additional_tweets, rate_limit_count
                while len(tweets) < target_tweet_count and timeout_count < 20:
                    done, _ = await asyncio.wait(
                        [
                            page.wait_for_response(
                                lambda resp: "SearchTimeline" in resp.url
                                or "TweetDetail" in resp.url
                            ),
                            asyncio.sleep(1.5),
                        ],
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    if done:
                        timeout_count = 0
                        resp = done.pop().result()
                        try:
                            data = await resp.json()
                        except Exception:
                            text = await resp.text()
                            if "rate limit" in text.lower():
                                await page.wait_for_timeout(
                                    calculate_for_rate_limit(rate_limit_count)
                                )
                                rate_limit_count += 1
                                await page.click("text=Retry")
                                continue
                            break

                        rate_limit_count = 0
                        entries = []
                        if data.get("data", {}).get("threaded_conversation_with_injections_v2"):
                            entries = (
                                data["data"]["threaded_conversation_with_injections_v2"][
                                    "instructions"
                                ][0]["entries"]
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

                            await write_csv([row])
                            additional_tweets += 1

                            if len(tweets) >= target_tweet_count:
                                break

                        await scroll_down(page)
                        if additional_tweets > 20:
                            await page.wait_for_timeout(delay_each_tweet_seconds * 1000)
                            additional_tweets = 0
                    else:
                        timeout_count += 1
                        await scroll_down(page)
                        if timeout_count >= 20:
                            break

            await scroll_and_save()

        await start_crawl()

        await browser.close()

    return file_path
