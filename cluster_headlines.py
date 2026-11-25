"""Group related news headlines into multi-article events."""

import json
import os
from sentence_transformers import SentenceTransformer
from sklearn.cluster import AgglomerativeClustering

# Input articles collected by app.py and clustered output file.
INPUT_FILE = "articles.json"
OUTPUT_FILE = "clustered_events.json"

# Lower value = stricter clusters
# Higher value = broader clusters
DISTANCE_THRESHOLD = 0.38


def load_articles():
    """Load the collected article records from JSON."""

    if not os.path.exists(INPUT_FILE):
        print(f"{INPUT_FILE} not found.")
        return []

    with open(INPUT_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def cluster_headlines(articles):
    """Embed headlines, cluster them, and discard singleton clusters."""

    # Articles without headlines cannot be meaningfully clustered.
    articles = [
        article for article in articles
        if article.get("title", "").strip()
    ]

    if not articles:
        return []

    # Sentence embeddings represent headlines as numerical vectors whose
    # semantic similarity can be compared by the clustering algorithm.
    headlines = [article["title"].strip() for article in articles]

    print("Loading sentence embedding model...")
    model = SentenceTransformer("all-MiniLM-L6-v2")

    print("Creating headline embeddings...")
    embeddings = model.encode(
        headlines,
        normalize_embeddings=True,
        show_progress_bar=True
    )

    # Agglomerative clustering cannot be useful with only one item.
    if len(articles) == 1:
        labels = [0]
    else:
        try:
            # Newer scikit-learn versions
            clustering_model = AgglomerativeClustering(
                n_clusters=None,
                distance_threshold=DISTANCE_THRESHOLD,
                metric="cosine",
                linkage="average"
            )
        except TypeError:
            # Older scikit-learn versions
            clustering_model = AgglomerativeClustering(
                n_clusters=None,
                distance_threshold=DISTANCE_THRESHOLD,
                affinity="cosine",
                linkage="average"
            )

        labels = clustering_model.fit_predict(embeddings)

    # Build a readable event object for every cluster label.
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

    # Display the largest events first.
    events = sorted(
        grouped_events.values(),
        key=lambda event: event["article_count"],
        reverse=True
    )

    # The project focuses on events reported by multiple sources, so remove
    # clusters that contain only one article.
    events = [
        event for event in events
        if event["article_count"] >= 2
    ]

    # Renumber event IDs after filtering so IDs are consecutive.
    for index, event in enumerate(events, start=1):
        event["event_id"] = index

    return events


def main():
    """Run headline clustering and write the grouped events to JSON."""

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
