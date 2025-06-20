TWITTER_SEARCH_ADVANCED_URL = {
    "TOP": "https://x.com/search-advanced",
    "LATEST": "https://x.com/search-advanced?f=live",
}

from datetime import datetime
NOW = datetime.now().strftime("%d-%m-%Y %H-%M-%S")

FOLDER_DESTINATION = "./tweets-data"

FILTERED_FIELDS = [
    "created_at",
    "id_str",
    "full_text",
    "quote_count",
    "reply_count",
    "retweet_count",
    "favorite_count",
    "lang",
    "user_id_str",
    "conversation_id_str",
    "username",
    "tweet_url",
    "image_url",
    "location",
    "in_reply_to_screen_name",
]
