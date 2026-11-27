"""Run a small interactive NLP pipeline for the dashboard.

The regular command-line scripts still support the full batch pipeline. This
module adds a bounded, background run for the website so a button click does
not block the HTTP server and the browser can observe each stage.
"""

from __future__ import annotations

import copy
import threading
import traceback
from datetime import datetime, timezone


MAX_HEADLINES = 12
MAX_ARTICLES_PER_SOURCE = 3

_LOCK = threading.Lock()
_STATE = {
    "status": "idle",
    "stage": "idle",
    "progress": 0,
    "message": "Ready to start a twelve-headline pipeline run.",
    "started_at": None,
    "finished_at": None,
    "error": None,
    "extracted": [],
    "clusters": [],
    "digests": [],
}


def _now():
    """Return a timezone-aware timestamp for the status payload."""

    return datetime.now(timezone.utc).isoformat()


def _article_preview(article):
    """Remove long article text before sending extraction results to a browser."""

    return {
        "source": article.get("source", "unknown"),
        "title": article.get("title", ""),
        "url": article.get("url", ""),
        "published": article.get("published", ""),
        "text_length": len(article.get("text", "")),
    }


def _cluster_preview(event):
    """Create a compact cluster result for the progress panel."""

    return {
        "event_id": event.get("event_id"),
        "article_count": event.get("article_count", 0),
        "sources": event.get("sources", []),
        "headlines": event.get("headlines", []),
    }


def _digest_preview(digest):
    """Create a compact digest result while retaining source perspectives."""

    return {
        "event_id": digest.get("event_id"),
        "article_count": digest.get("article_count", 0),
        "sources": digest.get("sources", []),
        "headlines": digest.get("headlines", []),
        "digest": digest.get("digest", ""),
        "source_summaries": digest.get("source_summaries", []),
    }


def _set_state(**changes):
    """Update shared status atomically so polling never sees half a result."""

    with _LOCK:
        _STATE.update(changes)


def get_status():
    """Return a safe copy of the current interactive-run status."""

    with _LOCK:
        return copy.deepcopy(_STATE)


def _handle_extraction_event(event):
    """Translate collector callbacks into user-facing progress updates."""

    if event.get("type") == "feed":
        _set_state(message=f"Checking {event['source']} RSS feed...")
    elif event.get("type") == "article":
        articles = get_status()["extracted"]
        articles.append(_article_preview(event["article"]))
        progress = min(30, 8 + round(len(articles) / MAX_HEADLINES * 22))
        _set_state(
            progress=progress,
            message=f"Extracted headline {len(articles)} of {MAX_HEADLINES}.",
            extracted=articles,
        )


def _handle_clustering_event(event):
    """Translate embedding/clustering callbacks into status updates."""

    if event.get("type") == "model":
        _set_state(progress=38, message="Headline embedding model loaded.")
    elif event.get("type") == "embedded":
        _set_state(
            progress=48,
            message=f"Embedded {event['count']} headlines by meaning.",
        )
    elif event.get("type") == "clusters":
        _set_state(
            progress=55,
            message=f"Formed {len(event['events'])} semantic topic cluster(s).",
            clusters=[_cluster_preview(item) for item in event["events"]],
        )


def _handle_digest_event(event):
    """Translate summarizer callbacks into status updates."""

    if event.get("type") == "event_started":
        completed = event["index"] - 1
        progress = 60 + round(completed / max(event["total"], 1) * 35)
        _set_state(
            progress=progress,
            message=f"Digesting topic {event['index']} of {event['total']}...",
        )
    elif event.get("type") == "digest":
        digests = get_status()["digests"]
        digests.append(_digest_preview(event["digest"]))
        _set_state(digests=digests)


def _worker():
    """Execute the bounded pipeline away from the HTTP request thread."""

    try:
        # Imports are deliberately lazy. The dashboard can start quickly, and
        # the large NLP dependencies are loaded only when the user clicks run.
        from app import collect_articles
        from cluster_headlines import cluster_headlines
        from summarize_events import create_digests

        _set_state(
            stage="extracting",
            progress=2,
            message="Starting extraction from multiple RSS feeds...",
        )
        articles, accepted = collect_articles(
            max_articles=MAX_HEADLINES,
            append_existing=False,
            max_per_source=MAX_ARTICLES_PER_SOURCE,
            progress_callback=_handle_extraction_event,
        )
        if not articles:
            raise RuntimeError("No valid articles could be extracted from the feeds.")

        # A feed can fail or return short pages, so report the actual count.
        _set_state(
            progress=32,
            message=f"Extraction complete: {accepted} valid headline(s).",
            extracted=[_article_preview(article) for article in articles],
            stage="clustering",
        )

        events = cluster_headlines(
            articles,
            # Interactive mode keeps single-topic groups visible. A group with
            # two or more articles is still shown as a stronger cross-source
            # event through its article_count and sources fields.
            keep_singletons=True,
            progress_callback=_handle_clustering_event,
        )
        if not events:
            raise RuntimeError("The extracted headlines could not be clustered.")

        _set_state(
            stage="digesting",
            progress=58,
            message=f"Preparing {len(events)} topic digest(s)...",
            clusters=[_cluster_preview(event) for event in events],
        )
        digests = create_digests(events, progress_callback=_handle_digest_event)

        _set_state(
            status="completed",
            stage="complete",
            progress=100,
            message=f"Complete: {len(articles)} headline(s), {len(events)} cluster(s), {len(digests)} digest(s).",
            digests=[_digest_preview(digest) for digest in digests],
            finished_at=_now(),
        )
    except Exception as error:
        traceback.print_exc()
        _set_state(
            status="error",
            stage="error",
            message="The pipeline stopped before completion.",
            error=str(error),
            finished_at=_now(),
        )


def start_pipeline():
    """Start one background run, returning False if one is already active."""

    with _LOCK:
        if _STATE["status"] == "running":
            return False, copy.deepcopy(_STATE)

        _STATE.update({
            "status": "running",
            "stage": "extracting",
            "progress": 0,
            "message": "Starting a new pipeline run...",
            "started_at": _now(),
            "finished_at": None,
            "error": None,
            "extracted": [],
            "clusters": [],
            "digests": [],
        })

    thread = threading.Thread(target=_worker, name="news-pipeline", daemon=True)
    thread.start()
    return True, get_status()
