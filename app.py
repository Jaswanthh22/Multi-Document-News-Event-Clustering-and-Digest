"""Collect news articles from RSS feeds and save them as JSON."""

import json
import os
import time

import feedparser
import trafilatura

# RSS feeds used as the input sources for the news dataset.
FEEDS = {
    "bbc": "http://feeds.bbci.co.uk/news/world/rss.xml",
    "guardian": "https://www.theguardian.com/world/rss",
    "aljazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "nyt": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "toi": "https://timesofindia.indiatimes.com/rssfeeds/296589292.cms",
}

# This is a relative path, so the file is written in the directory where
# this script is run.
OUT = "articles.json"

# Load previously collected articles so repeated runs do not create duplicates.
# An empty or invalid file is treated as an empty dataset.
try:
    with open(OUT, encoding="utf-8") as f:
        articles = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    articles = []

# Keep track of URLs already collected from earlier runs.
seen = {a["url"] for a in articles}
new = 0

# Download and extract the main text from every RSS feed.
for source, url in FEEDS.items():
    feed = feedparser.parse(url)
    print(f"{source}: {len(feed.entries)} entries")
    for entry in feed.entries:
        # Skip an article when its URL is already in articles.json.
        if entry.link in seen:
            continue

        try:
            # Fetch the webpage behind the RSS entry and remove navigation,
            # advertisements, and other non-article content.
            html = trafilatura.fetch_url(entry.link)
            text = trafilatura.extract(html) if html else None
        except Exception as e:
            print(f"  failed: {entry.link} ({e})")
            continue

        # Ignore pages for which extraction failed or produced very little text.
        if text and len(text) > 300:
            articles.append({
                "source": source,
                "title": entry.title,
                "url": entry.link,
                "published": entry.get("published", ""),
                "text": text,
            })
            seen.add(entry.link)
            new += 1

        # Avoid sending requests too quickly to the news websites.
        time.sleep(1)

# Save the complete accumulated dataset, including articles from earlier runs.
with open(OUT, "w") as f:
    json.dump(articles, f, indent=2)

print(f"Added {new} new articles, total {len(articles)}")
