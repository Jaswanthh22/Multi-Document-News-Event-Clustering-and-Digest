"""Serve the news dashboard and expose the pipeline outputs as one API payload.

Run with:

    python server.py

Then open http://127.0.0.1:8000 locally. On Render, the host and port are
provided through the `NEWS_DASHBOARD_HOST` and `PORT` environment variables.
"""

# Postpones evaluation of type annotations so modern annotations work cleanly.
from __future__ import annotations

import json  # Encodes the API response.
import mimetypes  # Chooses a browser content type for static files.
import os  # Reads the optional port environment variable.
from datetime import datetime, timezone  # Creates portable UTC timestamps.
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer  # HTTP server.
from pathlib import Path  # Safe, platform-independent filesystem paths.
from urllib.parse import urlparse  # Removes query strings from request paths.

from pipeline_runner import get_status, start_pipeline


# Resolve paths from this file rather than from the caller's current directory.
# This means `python /path/to/server.py` still serves the correct project.
ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"


def load_json(filename: str, fallback):
    """Read one pipeline artifact without taking down the dashboard.

    The fallback makes the UI usable while a pipeline stage is incomplete or
    when an output file has not been generated yet.
    """

    try:
        with (ROOT / filename).open(encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return fallback


def file_timestamp(*filenames: str) -> str:
    """Return the newest artifact modification time as an ISO timestamp."""

    # Several artifacts contribute to the dashboard, so show the latest one.
    timestamps = []
    for filename in filenames:
        try:
            timestamps.append((ROOT / filename).stat().st_mtime)
        except OSError:
            pass

    if not timestamps:
        # Keep the API shape valid even before the first pipeline run.
        return datetime.now(timezone.utc).isoformat()

    return datetime.fromtimestamp(max(timestamps), timezone.utc).isoformat()


def build_payload() -> dict:
    """Combine raw articles, clusters, and summaries for the frontend.

    The browser receives one stable payload instead of having to understand
    three separate intermediate JSON files.
    """

    articles = load_json("articles.json", [])
    clustered_events = load_json("clustered_events.json", [])
    digests = load_json("news_digest.json", [])

    # This lookup supports the partial-data fallback below when a digest is
    # available before its corresponding cluster artifact has been refreshed.
    articles_by_key = {
        (article.get("source", "unknown"), article.get("title", "")): article
        for article in articles
    }

    # The digest is the presentation layer, while clustered_events retains
    # URLs and publication dates. Merge both artifacts by event_id.
    cluster_by_id = {
        event.get("event_id"): event for event in clustered_events
    }
    events = []
    for digest in digests:
        cluster = cluster_by_id.get(digest.get("event_id"), {})
        # Prefer the richer article records from the clustering artifact.
        enriched_articles = []
        for article in cluster.get("articles", []):
            enriched_articles.append(article)

        # If only the digest is present, reconstruct minimal article records
        # from its source summaries instead of returning a broken event.
        if not enriched_articles:
            for item in digest.get("source_summaries", []):
                article = articles_by_key.get(
                    (item.get("source", "unknown"), item.get("headline", "")),
                    {
                        "source": item.get("source", "unknown"),
                        "title": item.get("headline", ""),
                    },
                )
                enriched_articles.append(article)

        events.append({
            **digest,
            "articles": enriched_articles,
            "headlines": digest.get("headlines", cluster.get("headlines", [])),
            "sources": digest.get("sources", cluster.get("sources", [])),
        })

    # Publisher counts power the source-mix chart in the frontend.
    source_counts = {}
    for article in articles:
        source = article.get("source", "unknown")
        source_counts[source] = source_counts.get(source, 0) + 1

    sources = [
        {"name": source, "article_count": count}
        for source, count in sorted(
            source_counts.items(), key=lambda item: (-item[1], item[0])
        )
    ]

    # Keep the response contract small and explicit: metadata, metrics,
    # source counts, enriched event cards, and the raw article feed.
    return {
        "generated_at": file_timestamp(
            "articles.json", "clustered_events.json", "news_digest.json"
        ),
        "metrics": {
            "article_count": len(articles),
            "event_count": len(clustered_events),
            "summary_count": len(digests),
            "source_count": len(source_counts),
            "clustered_article_count": sum(
                event.get("article_count", 0) for event in clustered_events
            ),
        },
        "sources": sources,
        "events": events,
        "articles": articles,
    }


class DashboardHandler(SimpleHTTPRequestHandler):
    """Serve frontend files and the data endpoint from the project root."""

    def _send_json(self, payload, status=200):
        """Send a JSON response with explicit no-cache headers."""

        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self):  # noqa: N802 - method name required by BaseHTTPRequestHandler
        """Start an interactive pipeline when the dashboard button is clicked."""

        path = urlparse(self.path).path
        if path == "/api/pipeline/run":
            started, status = start_pipeline()
            self._send_json(status, status=202 if started else 409)
            return

        self.send_error(404)

    def do_GET(self):  # noqa: N802 - method name required by BaseHTTPRequestHandler
        # Ignore query parameters such as the frontend cache-busting timestamp.
        path = urlparse(self.path).path
        if path == "/api/data":
            # Return a fresh, uncached snapshot of all pipeline artifacts.
            payload = json.dumps(build_payload(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if path == "/api/health":
            # Lightweight endpoint useful for checking whether the server is up.
            payload = b'{"status":"ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if path == "/api/pipeline/status":
            # The browser polls this small state machine while the background
            # extraction, clustering, and digestion thread is running.
            self._send_json(get_status())
            return

        # Serve frontend assets without changing the process working directory.
        requested = "index.html" if path in ("", "/") else path.lstrip("/")
        file_path = (FRONTEND / requested).resolve()
        # Prevent path traversal (for example, ../../secrets) outside frontend/.
        if FRONTEND not in file_path.parents and file_path != FRONTEND:
            self.send_error(404)
            return
        if file_path.is_file():
            content = file_path.read_bytes()
            content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        self.send_error(404)

    def log_message(self, format, *args):
        # Keep the terminal signal-to-noise low while the dashboard polls.
        if self.path.startswith("/api/"):
            return
        super().log_message(format, *args)


def main():
    # Render requires a public web service to bind to 0.0.0.0 and supplies the
    # listening port through PORT. The local NEWS_DASHBOARD_PORT fallback keeps
    # the original developer workflow convenient.
    host = os.environ.get("NEWS_DASHBOARD_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", os.environ.get("NEWS_DASHBOARD_PORT", "8000")))
    # ThreadingHTTPServer lets independent browser requests be handled without
    # blocking one another during local dashboard use.
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    display_host = "127.0.0.1" if host == "0.0.0.0" else host
    print(f"News dashboard running at http://{display_host}:{port}")
    print("Data refreshes automatically when the pipeline JSON files change.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
