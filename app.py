"""Collect news articles from RSS feeds and save them as JSON.

This is stage 1 of the pipeline.  It deliberately stores the extracted
article text so later stages do not need to download every page again.
"""

import json  # Serialises the collected article records to JSON.
import os  # Kept available for future configurable paths/environment values.
import time  # Adds a small delay between requests.

import feedparser  # Parses RSS/Atom feeds into Python objects.
import trafilatura  # Downloads pages and extracts their main article text.

# Each key becomes the stable source label stored in every article record.
# Each value is the RSS endpoint that supplies article links and metadata.
FEEDS = {
    "bbc": "http://feeds.bbci.co.uk/news/world/rss.xml",
    "guardian": "https://www.theguardian.com/world/rss",
    "aljazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "nyt": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "toi": "https://timesofindia.indiatimes.com/rssfeeds/296589292.cms",
}

# The output is intentionally simple and portable: one JSON list on disk.
# Because this is a relative path, run the script from the project directory.
OUT = "articles.json"

# Load the previous dataset first.  This makes later runs append-friendly and
# lets URL de-duplication work across separate executions of the script.
try:
    with open(OUT, encoding="utf-8") as f:
        articles = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    # Missing/invalid output is treated as an empty starting dataset rather
    # than preventing a fresh collection run.
    articles = []

# A set gives average O(1) membership checks while scanning new feed entries.
# The URL is used as the article identity in this prototype.
seen = {a["url"] for a in articles}
new = 0

# Process every configured publisher independently so one failed source does
# not prevent the other feeds from contributing articles.
for source, url in FEEDS.items():
    # feedparser handles the XML parsing and exposes entries as objects with
    # both attribute-style access and a dictionary-like .get() method.
    feed = feedparser.parse(url)
    print(f"{source}: {len(feed.entries)} entries")
    for entry in feed.entries:
        # Skip URLs already stored from an earlier run or earlier feed.
        if entry.link in seen:
            continue

        try:
            # RSS normally contains a link, not the complete article body.
            # Trafilatura downloads the page and removes navigation, ads, and
            # other boilerplate to retain the main readable article text.
            html = trafilatura.fetch_url(entry.link)
            text = trafilatura.extract(html) if html else None
        except Exception as e:
            # A single broken page should not abort the whole batch.
            print(f"  failed: {entry.link} ({e})")
            continue

        # A minimum length removes empty pages, paywall/error pages, and
        # fragments that would be poor input for summarization later.
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

        # Be polite to the publishers and reduce the chance of rate limiting.
        time.sleep(1)

# Persist both old and newly collected records for the next pipeline stage.
with open(OUT, "w") as f:
    json.dump(articles, f, indent=2)

print(f"Added {new} new articles, total {len(articles)}")
