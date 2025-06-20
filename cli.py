import argparse
import asyncio

from .crawl import crawl
from .env import ACCESS_TOKEN


def main():
    parser = argparse.ArgumentParser(description="Tweet Harvest (Python)")
    parser.add_argument("--token", dest="token", help="Twitter auth token")
    parser.add_argument("--search-keyword", dest="search_keyword")
    parser.add_argument("--from", dest="from_date")
    parser.add_argument("--to", dest="to_date")
    parser.add_argument("--thread", dest="thread_url")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--output", dest="output_filename")
    parser.add_argument("--tab", choices=["TOP", "LATEST"], default="TOP")
    args = parser.parse_args()

    token = args.token or ACCESS_TOKEN
    if not token:
        parser.error("Twitter token is required")

    asyncio.run(
        crawl(
            access_token=token,
            search_keywords=args.search_keyword,
            tweet_thread_url=args.thread_url,
            search_from_date=args.from_date,
            search_to_date=args.to_date,
            target_tweet_count=args.limit,
            output_filename=args.output_filename,
            search_tab=args.tab,
        )
    )


if __name__ == "__main__":
    main()
