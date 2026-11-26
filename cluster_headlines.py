"""Group related news headlines into multi-article events.

This is stage 2 of the pipeline.  It compares headline meaning rather than
requiring the same words to appear in two headlines.
"""

import json  # Reads the collector output and writes event objects.
import os  # Checks whether the input artifact exists.
from sentence_transformers import SentenceTransformer  # Creates semantic vectors.
from sklearn.cluster import AgglomerativeClustering  # Groups nearby vectors.

# The stage boundary is a JSON file, so the stages can be run independently.
INPUT_FILE = "articles.json"
OUTPUT_FILE = "clustered_events.json"

# This is a cosine-distance cutoff.  Lower values demand more similar
# headlines; higher values allow broader event groups.
DISTANCE_THRESHOLD = 0.38


def load_articles():
    """Load the collector's article records from JSON."""

    if not os.path.exists(INPUT_FILE):
        print(f"{INPUT_FILE} not found.")
        return []

    with open(INPUT_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def cluster_headlines(
    articles,
    min_articles=2,
    keep_singletons=False,
    progress_callback=None,
):
    """Embed headlines, cluster them, and optionally discard singletons.

    The returned event objects retain the original article records so later
    stages still have URLs, dates, sources, and full article text available.
    """

    # Articles without a title have no representation for this stage.
    articles = [
        article for article in articles
        if article.get("title", "").strip()
    ]

    if not articles:
        return []

    # A sentence embedding maps each headline to a dense vector.  Similar
    # meanings should occupy nearby positions even when wording differs.
    headlines = [article["title"].strip() for article in articles]

    print("Loading sentence embedding model...")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    if progress_callback:
        progress_callback({
            "type": "model",
            "message": "Headline embedding model loaded",
        })

    print("Creating headline embeddings...")
    embeddings = model.encode(
        headlines,
        normalize_embeddings=True,
        show_progress_bar=True
    )
    if progress_callback:
        progress_callback({"type": "embedded", "count": len(headlines)})

    # There is no pair to compare when only one valid article is present.
    if len(articles) == 1:
        labels = [0]
    else:
        try:
            # scikit-learn renamed the cosine-distance argument to `metric`.
            clustering_model = AgglomerativeClustering(
                n_clusters=None,
                distance_threshold=DISTANCE_THRESHOLD,
                metric="cosine",
                linkage="average"
            )
        except TypeError:
            # Compatibility fallback for older scikit-learn releases.
            clustering_model = AgglomerativeClustering(
                n_clusters=None,
                distance_threshold=DISTANCE_THRESHOLD,
                affinity="cosine",
                linkage="average"
            )

        labels = clustering_model.fit_predict(embeddings)

    # Convert numeric labels into a JSON-friendly, human-readable schema.
    grouped_events = {}

    for article, label in zip(articles, labels):
        label = int(label)

        if label not in grouped_events:
            grouped_events[label] = {
                "event_id": label + 1,
                "article_count": 0,
                "headlines": [],
                "sources": [],
                "articles": []
            }

        event = grouped_events[label]
        event["article_count"] += 1
        event["headlines"].append(article["title"])

        source = article.get("source", "unknown")
        if source not in event["sources"]:
            event["sources"].append(source)

        event["articles"].append(article)

    # Put the most reported events first in the output and dashboard.
    events = sorted(
        grouped_events.values(),
        key=lambda event: event["article_count"],
        reverse=True
    )

    # Batch mode keeps the original multi-article contract. Interactive mode
    # can retain singleton topics so a six-headline run always has digestable
    # output, while the UI still labels those as single-source topics.
    if not keep_singletons:
        events = [
            event for event in events
            if event["article_count"] >= min_articles
        ]

    if progress_callback:
        progress_callback({"type": "clusters", "events": events})

    # Clustering labels are arbitrary, so renumber the retained events for a
    # stable compact presentation in the generated artifact.
    for index, event in enumerate(events, start=1):
        event["event_id"] = index

    return events


def main():
    """Run headline clustering and write grouped events to JSON."""

    articles = load_articles()

    if not articles:
        print("No articles found.")
        return

    events = cluster_headlines(articles)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        json.dump(events, file, indent=2, ensure_ascii=False)

    print(f"\nTotal articles: {len(articles)}")
    print(f"Total event clusters: {len(events)}")
    print(f"Saved clustered data to: {OUTPUT_FILE}")

    print("\nClusters:")
    for event in events:
        print(f"\nEvent {event['event_id']} ({event['article_count']} articles)")
        for headline in event["headlines"]:
            print(f"  - {headline}")


if __name__ == "__main__":
    main()
