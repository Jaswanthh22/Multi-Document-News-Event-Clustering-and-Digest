"""Collect news articles from RSS feeds and save them as JSON.

This module is stage 1 of the pipeline. The collection logic is exposed as a
function so the web dashboard can run a small interactive collection as well
as the original full batch collection from the command line.
"""

import json  # Serialises collected article records to JSON.
import time  # Adds a small delay between publisher requests.

import feedparser  # Parses RSS/Atom feeds into Python objects.
import trafilatura  # Downloads pages and extracts their main article text.


# Each key becomes the stable source label stored in every article record.
FEEDS = {
    "bbc": "http://feeds.bbci.co.uk/news/world/rss.xml",
    "guardian": "https://www.theguardian.com/world/rss",
    "aljazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "nyt": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "toi": "https://timesofindia.indiatimes.com/rssfeeds/296589292.cms",
}

# The ordinary batch output remains the same JSON artifact used by the
# clustering stage and the dashboard's stored-data view.
OUT = "articles.json"
MIN_TEXT_LENGTH = 300


def load_articles():
    """Load previously collected articles, or return an empty list."""

    try:
        with open(OUT, encoding="utf-8") as file:
            data = json.load(file)
            return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def _notify(callback, payload):
    """Send progress data to a caller when a callback was provided."""

    if callback:
        callback(payload)


def collect_articles(
    max_articles=None,
    append_existing=True,
    max_per_source=None,
    progress_callback=None,
):
    """Collect valid article records from the configured RSS feeds.

    ``max_articles`` and ``max_per_source`` are used by the interactive
    dashboard to keep one run small and reasonably balanced across publishers.
    """

    previous = load_articles() if append_existing else []
    articles = list(previous)
    seen = {article.get("url") for article in articles if article.get("url")}
    accepted = 0
    source_counts = {}

    for source, feed_url in FEEDS.items():
        if max_articles is not None and accepted >= max_articles:
            break

        feed = feedparser.parse(feed_url)
        entries = getattr(feed, "entries", [])
        _notify(progress_callback, {
            "type": "feed",
            "source": source,
            "entry_count": len(entries),
        })

        for entry in entries:
            if max_articles is not None and accepted >= max_articles:
                break
            if max_per_source is not None and source_counts.get(source, 0) >= max_per_source:
                break

            # RSS libraries expose entries as mapping-like objects, but some
            # feeds omit a link; such records cannot be fetched safely.
            link = entry.get("link", "")
            if not link or link in seen:
                continue

            try:
                # RSS usually provides metadata and a URL, not the full body.
                # Trafilatura removes navigation, ads, and page boilerplate.
                html = trafilatura.fetch_url(link)
                text = trafilatura.extract(html) if html else None
            except Exception as error:
                _notify(progress_callback, {
                    "type": "skipped",
                    "source": source,
                    "url": link,
                    "reason": str(error),
                })
                continue

            # Short or empty extraction is usually an error/paywall page and
            # would be poor input for semantic clustering and summarization.
            if not text or len(text) <= MIN_TEXT_LENGTH:
                _notify(progress_callback, {
                    "type": "skipped",
                    "source": source,
                    "url": link,
                    "reason": "article text was missing or too short",
                })
                time.sleep(1)
                continue

            article = {
                "source": source,
                "title": entry.get("title", "").strip(),
                "url": link,
                "published": entry.get("published", ""),
                "text": text,
            }
            if not article["title"]:
                time.sleep(1)
                continue

            articles.append(article)
            seen.add(link)
            source_counts[source] = source_counts.get(source, 0) + 1
            accepted += 1
            _notify(progress_callback, {"type": "article", "article": article})

            # Avoid sending requests too quickly to publishers.
            time.sleep(1)

    return articles, accepted


def main():
    """Run full collection and write the accumulated dataset to JSON."""

    articles, new_count = collect_articles()
    with open(OUT, "w", encoding="utf-8") as file:
        json.dump(articles, file, indent=2, ensure_ascii=False)

    print(f"Added {new_count} new articles, total {len(articles)}")


if __name__ == "__main__":
    main()
