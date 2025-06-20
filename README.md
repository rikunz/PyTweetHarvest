# PyTweetHarvest

A simple tool to crawl tweets from X (Twitter) using Playwright.

## Installation

```bash
pip install -r requirements.txt
playwright install
```

## Usage

### CLI

Run the command line interface similar to the original project:

```bash
python -m PyTweetHarvest.cli --token YOUR_TOKEN --search-keyword "open ai" --limit 20
```

### Library

```python
from PyTweetHarvest import PyTweetHarvest

harvester = PyTweetHarvest(access_token="YOUR_TOKEN")
df = harvester.crawl(keyword="open ai", limit=20)
print(df.head())
```

The `crawl` method returns a `pandas.DataFrame` with the fetched tweets.
Data is processed entirely in memory so no intermediate CSV files are written.

Environment variables can be defined in a `.env` file. The most important is
`DEV_ACCESS_TOKEN` which stores your Twitter access token.

