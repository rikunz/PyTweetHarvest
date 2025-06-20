import asyncio
import io
from typing import Optional

import pandas as pd

from crawl import crawl_buffer
from env import ACCESS_TOKEN


class PyTweetHarvest:
    """Wrapper class to interact with the crawl functionality.

    Parameters
    ----------
    access_token : str, optional
        Twitter access token. If not provided, ``DEV_ACCESS_TOKEN`` from
        ``.env`` will be used.
    """

    def __init__(self, access_token: Optional[str] = None) -> None:
        self.access_token = access_token or ACCESS_TOKEN
        if not self.access_token:
            raise ValueError("Twitter access token is required")

    async def _crawl_async(self, **kwargs) -> io.StringIO:
        return await crawl_buffer(access_token=self.access_token, **kwargs)

    def crawl(
        self,
        keyword: Optional[str] = None,
        *,
        thread_url: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 10,
        tab: str = "LATEST",
    ) -> pd.DataFrame:
        """Fetch tweets and return them as a :class:`pandas.DataFrame`.

        Parameters
        ----------
        keyword : str, optional
            Keyword to search for. Ignored when ``thread_url`` is given.
        thread_url : str, optional
            URL to a tweet thread to crawl instead of searching.
        from_date : str, optional
            Start date in ``dd-mm-yyyy`` format.
        to_date : str, optional
            End date in ``dd-mm-yyyy`` format.
        limit : int, default ``10``
            Maximum number of tweets to fetch.
        tab : {"LATEST", "TOP"}, default ``"LATEST"``
            Tab to crawl when searching.
        """

        buffer = asyncio.run(
            self._crawl_async(
                search_keywords=keyword,
                tweet_thread_url=thread_url,
                search_from_date=from_date,
                search_to_date=to_date,
                target_tweet_count=limit,
                search_tab=tab,
            )
        )

        return pd.read_csv(buffer)