"""Streamlit entrypoint for the interactive news event pipeline."""

from __future__ import annotations

import html
import json
from pathlib import Path

import streamlit as st

from app import collect_articles
from cluster_headlines import cluster_headlines
from summarize_events import create_digests


ROOT = Path(__file__).resolve().parent
MAX_HEADLINES = 12
MAX_PER_SOURCE = 3

st.set_page_config(
    page_title="Signal — News Event Intelligence",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded",
)


# The CSS makes the three pipeline stages visually distinct while leaving
# Streamlit's native controls, tabs, expanders, and download buttons usable.
st.markdown(
    """
    <style>
      .stApp { background: #f5f6f2; }
      [data-testid="stHeader"] { background: rgba(245,246,242,.86); }
      /* Streamlit theme defaults can override individual selectors. Force
         every normal element in the main page to readable true black first. */
      [data-testid="stAppViewContainer"] .main * { color: #000000 !important; }
      /* Current Streamlit versions expose the content container as stMain;
         this is the selector used by the deployed Community Cloud app. */
      [data-testid="stMain"] * { color: #000000 !important; }
      /* Restore contrast for controls that intentionally have dark/coral
         backgrounds after the global text rule above. */
      [data-testid="stMain"] button:not([role="tab"]) {
        color: #ffffff !important; background: #18201e !important; border-color: #18201e !important;
      }
      [data-testid="stMain"] button:not([role="tab"]) * { color: #ffffff !important; }
      [data-testid="stMain"] button[kind="primary"] {
        color: #ffffff !important; background: #ff765f !important; border-color: #ff765f !important;
      }
      [data-testid="stMain"] button[role="tab"],
      [data-testid="stMain"] button[role="tab"] * { color: #000000 !important; background: transparent !important; }
      [data-testid="stMain"] [data-testid="stAlert"] {
        color: #18201e !important; background: #fff0ec !important; border-left-color: #ff765f !important;
      }
      [data-testid="stMain"] [data-testid="stAlert"] * { color: #18201e !important; }
      [data-testid="stAppViewContainer"] .main [data-testid="stMarkdownContainer"] p,
      [data-testid="stAppViewContainer"] .main [data-testid="stMarkdownContainer"] li,
      [data-testid="stAppViewContainer"] .main [data-testid="stMarkdownContainer"] strong,
      [data-testid="stAppViewContainer"] .main label,
      [data-testid="stAppViewContainer"] .main [data-testid="stCaptionContainer"] p,
      [data-testid="stAppViewContainer"] .main [data-testid="stAlert"] p,
      [data-testid="stAppViewContainer"] .main button[role="tab"] {
        color: #18201e !important;
      }
      [data-testid="stAppViewContainer"] .main [data-testid="stCaptionContainer"] p,
      [data-testid="stAppViewContainer"] .main [data-testid="stAlert"] p {
        color: #18201e !important;
      }
      [data-testid="stAppViewContainer"] .main .block-container {
        max-width: 1280px; padding: 2.6rem 3rem 5rem;
      }
      [data-testid="stSidebar"] { background: #18201e; }
      [data-testid="stSidebar"] * { color: #f5f6f2; }
      .hero { padding: 2.2rem 2.4rem; border-radius: 18px; color: white;
        background: linear-gradient(125deg,#18201e 0%,#34453c 62%,#91b51b 100%);
        box-shadow: 0 18px 50px rgba(24,32,30,.16); }
      .hero, .hero h1, .hero p, .hero .hero-kicker { color: #ffffff !important; }
      .hero .hero-kicker { color: #d4f34a !important; }
      .hero * { color: #ffffff !important; }
      .hero .hero-kicker { color: #d4f34a !important; }
      .hero-kicker { margin: 0 0 .8rem; color: #d4f34a; font: 700 .72rem ui-monospace,monospace;
        letter-spacing: .14em; text-transform: uppercase; }
      .hero h1 { margin: 0; font-size: clamp(2.2rem,5vw,4.7rem); line-height: 1.02;
        letter-spacing: -.06em; }
      .hero p { max-width: 750px; margin: 1rem 0 0; color: #eef3d3; font-size: 1.04rem; }
      .section-kicker { margin: 0 0 .45rem; color: #65706a; font: 700 .7rem ui-monospace,monospace;
        letter-spacing: .13em; text-transform: uppercase; }
      .section-title { margin: 0 0 .45rem; color: #18201e; font-size: 1.65rem; letter-spacing: -.04em; }
      .section-copy { margin: 0; color: #65706a; }
      .stage-strip { display: grid; grid-template-columns: repeat(3,1fr); gap: .85rem; margin: 1.55rem 0 2rem; }
      .stage-card { min-height: 112px; padding: 1.1rem 1.2rem; border: 1px solid #dfe2db;
        border-radius: 12px; background: #fff; }
      .stage-card.active { border-color: #91b51b; box-shadow: 0 0 0 3px rgba(212,243,74,.34); }
      .stage-card.done { border-color: #b8c873; background: #f1f7cf; }
      .stage-number { color: #ff765f; font: 700 .72rem ui-monospace,monospace; }
      .stage-number, .source-label { color: #ff765f !important; }
      .stage-name { display: block; margin-top: .65rem; color: #18201e; font-weight: 700; }
      .stage-detail { display: block; margin-top: .22rem; color: #65706a; font-size: .82rem; }
      .result-box { margin: .5rem 0 1rem; padding: 1rem 1.15rem; border: 1px solid #dfe2db;
        border-radius: 10px; background: #fff; }
      .source-label { color: #ff765f; font: 700 .68rem ui-monospace,monospace;
        letter-spacing: .08em; text-transform: uppercase; }
      .source-label { color: #ff765f !important; }
      .topic-label { color: #91b51b !important; }
      .headline { margin: .28rem 0 .15rem; color: #18201e; font-size: .98rem; font-weight: 650; line-height: 1.35; }
      .muted-line { color: #65706a; font-size: .78rem; }
      .digest-box { margin: .7rem 0; padding: 1.2rem; border-left: 4px solid #ff765f;
        border-radius: 8px; background: #fff0ec; }
      .digest-box p { margin: 0; color: #18201e; line-height: 1.55; }
      .topic-label { color: #91b51b; font: 700 .72rem ui-monospace,monospace; letter-spacing: .07em; text-transform: uppercase; }
      .small-note { color: #65706a; font-size: .82rem; }
      div[data-testid="stMetric"] { padding: .75rem .9rem; border: 1px solid #dfe2db;
        border-radius: 10px; background: #fff; }
      button[kind="primary"] { background: #ff765f !important; border-color: #ff765f !important; }
      button[kind="primary"] * { color: #ffffff !important; }
      button[kind="primary"]:hover { background: #18201e !important; border-color: #18201e !important; }
      button[role="tab"][aria-selected="true"] { color: #18201e !important; border-bottom-color: #ff765f !important; }
      @media (max-width: 760px) {
        [data-testid="stAppViewContainer"] .main .block-container { padding: 1.4rem 1rem 3rem; }
        .stage-strip { grid-template-columns: 1fr; }
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def load_json(filename, fallback):
    """Read a committed JSON artifact without breaking the page."""

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


def render_stage_strip(current_stage="idle", progress=0):
    """Render one stable three-stage strip instead of creating moving sections."""

    stages = [
        ("extracting", "01", "Extract", "RSS + article text"),
        ("clustering", "02", "Cluster", "semantic similarity"),
        ("digesting", "03", "Digest", "BART summaries"),
    ]
    current_index = next((index for index, item in enumerate(stages) if item[0] == current_stage), -1)
    cards = []
    for index, (stage, number, name, detail) in enumerate(stages):
        state_class = "active" if stage == current_stage else "done" if current_index > index or current_stage == "complete" else ""
        cards.append(
            f'<div class="stage-card {state_class}">'
            f'<span class="stage-number">{number} / {"RUNNING" if state_class == "active" else "DONE" if state_class == "done" else "WAITING"}</span>'
            f'<span class="stage-name">{name}</span><span class="stage-detail">{detail}</span></div>'
        )
    st.markdown(f'<div class="stage-strip">{"".join(cards)}</div>', unsafe_allow_html=True)
    st.progress(min(max(progress, 0), 100))


def render_extraction(results):
    """Show the exact headlines and text lengths accepted by extraction."""

    if not results:
        st.info("No headlines extracted yet.")
        return
    for article in results:
        with st.container(border=True):
            left, right = st.columns([5, 1])
            with left:
                st.markdown(f'<span class="source-label">{html.escape(article["source"])}</span>', unsafe_allow_html=True)
                st.markdown(f'<div class="headline">{html.escape(article["title"])}</div>', unsafe_allow_html=True)
                st.caption(f"{article['text_length']:,} characters extracted")
            with right:
                if article.get("url"):
                    st.link_button("Open source", article["url"], use_container_width=True)


def render_clusters(results):
    """Show each topic as an isolated, readable cluster segment."""

    if not results:
        st.info("No clusters created yet.")
        return
    for cluster in results:
        source_text = " · ".join(cluster.get("sources", [])) or "source unknown"
        with st.expander(
            f"Topic {cluster['event_id']} · {cluster['article_count']} headline(s) · {source_text}",
            expanded=True,
        ):
            for headline in cluster.get("headlines", []):
                st.markdown(f"• {headline}")


def render_digests(results):
    """Show one digest card followed by collapsible source perspectives."""

    if not results:
        st.info("No digests created yet.")
        return
    for digest in results:
        st.markdown(
            f'<div class="digest-box"><span class="topic-label">Topic {digest["event_id"]} · '
            f'{html.escape(", ".join(digest.get("sources", [])))}</span>'
            f'<p>{html.escape(digest.get("digest", "Digest is not available."))}</p></div>',
            unsafe_allow_html=True,
        )
        with st.expander("Source perspectives", expanded=False):
            for item in digest.get("source_summaries", []):
                st.markdown(f"**{item.get('source', 'unknown')}** — {item.get('summary', '')}")


def render_run_results(results):
    """Place the three output segments into stable tabs."""

    st.markdown('<p class="section-kicker">RUN OUTPUT</p><h2 class="section-title">What the pipeline produced</h2>', unsafe_allow_html=True)
    extracted_count = len(results.get("extracted", []))
    cluster_count = len(results.get("clusters", []))
    digest_count = len(results.get("digests", []))
    metrics = st.columns(3)
    metrics[0].metric("Extracted", extracted_count)
    metrics[1].metric("Clusters", cluster_count)
    metrics[2].metric("Digests", digest_count)

    extraction_tab, cluster_tab, digest_tab = st.tabs([
        "01 · Extraction",
        "02 · Clustering",
        "03 · Digestion",
    ])
    with extraction_tab:
        render_extraction(results.get("extracted", []))
    with cluster_tab:
        render_clusters(results.get("clusters", []))
    with digest_tab:
        render_digests(results.get("digests", []))

    st.download_button(
        "Download this run as JSON",
        data=json.dumps(results, indent=2, ensure_ascii=False),
        file_name="interactive_news_run.json",
        mime="application/json",
    )


def run_interactive_pipeline():
    """Run the bounded pipeline while updating one stable progress area."""

    results = {"extracted": [], "clusters": [], "digests": []}
    progress_area = st.empty()
    stage_area = st.empty()

    def extraction_callback(event):
        if event.get("type") == "article":
            results["extracted"].append(article_preview(event["article"]))
            with stage_area.container():
                st.info(f"Extracted headline {len(results['extracted'])} of {MAX_HEADLINES}.")
            with progress_area.container():
                render_stage_strip("extracting", 10 + len(results["extracted"]) * 4)
        elif event.get("type") == "feed":
            with stage_area.container():
                st.info(f"Checking {event['source']} RSS feed…")

    def clustering_callback(event):
        if event.get("type") == "model":
            with stage_area.container():
                st.info("Headline embedding model loaded.")
            with progress_area.container():
                render_stage_strip("clustering", 38)
        elif event.get("type") == "embedded":
            with stage_area.container():
                st.info(f"Embedded {event['count']} headlines by meaning.")
            with progress_area.container():
                render_stage_strip("clustering", 48)
        elif event.get("type") == "clusters":
            results["clusters"] = [cluster_preview(item) for item in event["events"]]
            with stage_area.container():
                st.info(f"Formed {len(results['clusters'])} semantic topic cluster(s).")
            with progress_area.container():
                render_stage_strip("clustering", 55)

    def digest_callback(event):
        if event.get("type") == "event_started":
            progress_value = 60 + round((event["index"] - 1) / max(event["total"], 1) * 35)
            with stage_area.container():
                st.info(f"Digesting topic {event['index']} of {event['total']}…")
            with progress_area.container():
                render_stage_strip("digesting", progress_value)
        elif event.get("type") == "digest":
            results["digests"].append(digest_preview(event["digest"]))

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

        with stage_area.container():
            st.info(f"Extraction complete: {accepted} valid headline(s). Clustering now…")
        events = cluster_headlines(articles, keep_singletons=True, progress_callback=clustering_callback)
        if not events:
            raise RuntimeError("The extracted headlines could not be clustered.")

        with stage_area.container():
            st.info(f"Clustering complete: {len(events)} topic(s). Digesting now…")
        digests = create_digests(events, progress_callback=digest_callback)
        results["digests"] = [digest_preview(digest) for digest in digests]
        with progress_area.container():
            render_stage_strip("complete", 100)
        with stage_area.container():
            st.success(f"Complete — {len(articles)} headline(s), {len(events)} cluster(s), {len(digests)} digest(s).")
        return results
    except Exception as error:
        st.error(f"Pipeline failed: {error}")
        st.exception(error)
        return None


def render_stored_snapshot():
    """Display the committed JSON snapshot in a separate section."""

    articles = load_json("articles.json", [])
    clusters = load_json("clustered_events.json", [])
    digests = load_json("news_digest.json", [])
    sources = sorted({article.get("source", "unknown") for article in articles})

    st.markdown('<p class="section-kicker">COMMITTED DATA</p><h2 class="section-title">Stored snapshot</h2>', unsafe_allow_html=True)
    metrics = st.columns(4)
    metrics[0].metric("Articles", len(articles))
    metrics[1].metric("Clusters", len(clusters))
    metrics[2].metric("Digests", len(digests))
    metrics[3].metric("Sources", len(sources))
    st.caption("This section comes from articles.json, clustered_events.json, and news_digest.json in the repository.")
    for digest in digests:
        title = digest.get("headlines", ["Untitled event"])[0]
        with st.expander(f"Event {digest.get('event_id')} · {title}"):
            st.write(digest.get("digest", "No digest available."))
            for item in digest.get("source_summaries", []):
                st.caption(f"{item.get('source', 'unknown')}: {item.get('summary', '')}")


def main():
    """Build the Streamlit page."""

    st.markdown(
        '<div class="hero"><p class="hero-kicker">GLOBAL NEWS / EVENT INTELLIGENCE</p>'
        '<h1>From headlines<br>to signal.</h1>'
        '<p>Collect a small, relevant sample, see the semantic groups form, and read a concise digest for every topic.</p></div>',
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.markdown("## Signal")
        st.caption("Multi-document news event clustering and digest")
        st.markdown("### Pipeline")
        st.markdown("**01 · Extract**\n\n**02 · Cluster**\n\n**03 · Digest**")
        st.caption("Each run uses at most twelve valid headlines and no more than three per publisher.")
        start = st.button("▶  Start Pipeline", type="primary", use_container_width=True)
        st.divider()
        st.caption("Initial data is read from the committed JSON snapshot. Interactive results are available to download after each run.")

    st.markdown('<p class="section-kicker">LIVE PIPELINE</p><h2 class="section-title">Watch the signal form</h2><p class="section-copy">Press Start Pipeline to run extraction, semantic clustering, and digestion as three separate stages.</p>', unsafe_allow_html=True)

    if start:
        results = run_interactive_pipeline()
        if results:
            st.session_state["last_run"] = results

    if "last_run" in st.session_state:
        render_run_results(st.session_state["last_run"])
    else:
        render_stage_strip()
        st.info("No interactive run yet. Use the Start Pipeline button in the sidebar.")

    st.divider()
    render_stored_snapshot()


if __name__ == "__main__":
    main()
