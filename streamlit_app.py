"""Streamlit entrypoint for the interactive news event pipeline.

Run locally with:

    streamlit run streamlit_app.py

The app reads the committed JSON snapshot for the initial dashboard and runs a
bounded six-headline extraction → clustering → digestion pipeline when the
user presses the Start Pipeline button.
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from app import collect_articles
from cluster_headlines import cluster_headlines
from summarize_events import create_digests


ROOT = Path(__file__).resolve().parent
MAX_HEADLINES = 6
MAX_PER_SOURCE = 2


st.set_page_config(
    page_title="Signal — News Event Intelligence",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded",
)


def load_json(filename, fallback):
    """Read a committed artifact without breaking the Streamlit page."""

    try:
        with (ROOT / filename).open(encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return fallback


def article_preview(article):
    """Keep only concise extraction metadata for the live results panel."""

    return {
        "source": article.get("source", "unknown"),
        "title": article.get("title", ""),
        "url": article.get("url", ""),
        "published": article.get("published", ""),
        "text_length": len(article.get("text", "")),
    }


def cluster_preview(event):
    """Keep cluster metadata while omitting full article bodies."""

    return {
        "event_id": event.get("event_id"),
        "article_count": event.get("article_count", 0),
        "sources": event.get("sources", []),
        "headlines": event.get("headlines", []),
    }


def digest_preview(digest):
    """Keep the final digest and source-level summaries for display/download."""

    return {
        "event_id": digest.get("event_id"),
        "article_count": digest.get("article_count", 0),
        "sources": digest.get("sources", []),
        "headlines": digest.get("headlines", []),
        "digest": digest.get("digest", ""),
        "source_summaries": digest.get("source_summaries", []),
    }


def render_live_results(results, extraction_placeholder, cluster_placeholder, digest_placeholder):
    """Render the three compact result columns during and after a run."""

    with extraction_placeholder.container():
        st.markdown("**Extracted headlines**")
        if not results["extracted"]:
            st.caption("Waiting for valid article text…")
        for article in results["extracted"]:
            st.markdown(f"**{article['source']}** — {article['title']}")
            st.caption(f"{article['text_length']:,} characters extracted")

    with cluster_placeholder.container():
        st.markdown("**Semantic clusters**")
        if not results["clusters"]:
            st.caption("Waiting for headline embeddings…")
        for cluster in results["clusters"]:
            st.markdown(
                f"**Topic {cluster['event_id']}** · "
                f"{cluster['article_count']} headline(s) · "
                f"{', '.join(cluster['sources'])}"
            )
            for headline in cluster["headlines"]:
                st.caption(f"• {headline}")

    with digest_placeholder.container():
        st.markdown("**Digests and source summaries**")
        if not results["digests"]:
            st.caption("Waiting for BART summaries…")
        for digest in results["digests"]:
            st.markdown(f"**Topic {digest['event_id']}** — {digest['digest']}")
            with st.expander("Source perspectives", expanded=False):
                for item in digest["source_summaries"]:
                    st.markdown(f"**{item['source']}** — {item['summary']}")


def run_interactive_pipeline():
    """Run the six-headline pipeline synchronously with visible progress."""

    results = {"extracted": [], "clusters": [], "digests": []}
    progress = st.progress(0)
    stage_placeholder = st.empty()
    extraction_placeholder, cluster_placeholder, digest_placeholder = st.columns(3)

    def extraction_callback(event):
        if event.get("type") == "article":
            results["extracted"].append(article_preview(event["article"]))
            progress.progress(min(10 + len(results["extracted"]) * 4, 30))
            with stage_placeholder.container():
                st.info(f"Extracted headline {len(results['extracted'])} of {MAX_HEADLINES}.")
        elif event.get("type") == "feed":
            with stage_placeholder.container():
                st.info(f"Checking {event['source']} RSS feed…")
        render_live_results(results, extraction_placeholder, cluster_placeholder, digest_placeholder)

    def clustering_callback(event):
        if event.get("type") == "model":
            progress.progress(38)
            with stage_placeholder.container():
                st.info("Headline embedding model loaded.")
        elif event.get("type") == "embedded":
            progress.progress(48)
            with stage_placeholder.container():
                st.info(f"Embedded {event['count']} headlines by meaning.")
        elif event.get("type") == "clusters":
            results["clusters"] = [cluster_preview(item) for item in event["events"]]
            progress.progress(55)
            with stage_placeholder.container():
                st.info(f"Formed {len(results['clusters'])} semantic topic cluster(s).")
        render_live_results(results, extraction_placeholder, cluster_placeholder, digest_placeholder)

    def digest_callback(event):
        if event.get("type") == "event_started":
            progress.progress(60 + round((event["index"] - 1) / max(event["total"], 1) * 35))
            with stage_placeholder.container():
                st.info(f"Digesting topic {event['index']} of {event['total']}…")
        elif event.get("type") == "digest":
            results["digests"].append(digest_preview(event["digest"]))
        render_live_results(results, extraction_placeholder, cluster_placeholder, digest_placeholder)

    try:
        with st.spinner("Collecting recent headlines…"):
            articles, accepted = collect_articles(
                max_articles=MAX_HEADLINES,
                append_existing=False,
                max_per_source=MAX_PER_SOURCE,
                progress_callback=extraction_callback,
            )
        if not articles:
            raise RuntimeError("No valid articles could be extracted from the feeds.")

        with stage_placeholder.container():
            st.info(f"Extraction complete: {accepted} valid headline(s). Clustering now…")
        events = cluster_headlines(
            articles,
            keep_singletons=True,
            progress_callback=clustering_callback,
        )
        if not events:
            raise RuntimeError("The extracted headlines could not be clustered.")

        with stage_placeholder.container():
            st.info(f"Clustering complete: {len(events)} topic(s). Digesting now…")
        digests = create_digests(events, progress_callback=digest_callback)
        results["digests"] = [digest_preview(digest) for digest in digests]
        progress.progress(100)
        with stage_placeholder.container():
            st.success(
                f"Complete — {len(articles)} headline(s), {len(events)} cluster(s), "
                f"{len(digests)} digest(s)."
            )
        render_live_results(results, extraction_placeholder, cluster_placeholder, digest_placeholder)
        st.download_button(
            "Download this run as JSON",
            data=json.dumps(results, indent=2, ensure_ascii=False),
            file_name="interactive_news_run.json",
            mime="application/json",
        )
        st.session_state["last_run"] = results
    except Exception as error:
        st.error(f"Pipeline failed: {error}")
        st.exception(error)


def render_stored_snapshot():
    """Display the committed JSON snapshot without loading article bodies."""

    articles = load_json("articles.json", [])
    clusters = load_json("clustered_events.json", [])
    digests = load_json("news_digest.json", [])
    sources = sorted({article.get("source", "unknown") for article in articles})

    st.subheader("Stored snapshot")
    metrics = st.columns(4)
    metrics[0].metric("Articles", len(articles))
    metrics[1].metric("Clusters", len(clusters))
    metrics[2].metric("Digests", len(digests))
    metrics[3].metric("Sources", len(sources))
    st.caption("These are the JSON artifacts committed with the deployment.")

    for digest in digests:
        with st.expander(f"Event {digest.get('event_id')} · {digest.get('headlines', ['Untitled'])[0]}"):
            st.write(digest.get("digest", "No digest available."))
            for item in digest.get("source_summaries", []):
                st.caption(f"{item.get('source', 'unknown')}: {item.get('summary', '')}")


def main():
    """Build the Streamlit page."""

    st.title("✦ Signal")
    st.subheader("Multi-Document News Event Clustering and Digest")
    st.write(
        "Press the button to collect up to six recent valid headlines, group "
        "related stories by semantic meaning, and generate concise digests."
    )

    with st.sidebar:
        st.header("How it works")
        st.markdown("1. **Extract** RSS-linked article text\n2. **Cluster** headline embeddings\n3. **Digest** each topic with BART")
        st.caption("The interactive run uses at most six headlines and no more than two per publisher.")
        start = st.button("▶ Start Pipeline", type="primary", use_container_width=True)

    if start:
        run_interactive_pipeline()
    elif "last_run" in st.session_state:
        st.success("Last interactive run")
        extraction, clustering, digestion = st.columns(3)
        render_live_results(
            st.session_state["last_run"],
            extraction,
            clustering,
            digestion,
        )

    st.divider()
    render_stored_snapshot()


if __name__ == "__main__":
    main()
