# Interim Project Report

## Project

**Multi-Document News Event Clustering and Digest**

**Snapshot reviewed:** 25 November 2026

## 1. Executive summary

The project implements a batch NLP pipeline that collects news articles from RSS feeds, extracts article text, groups semantically related headlines into event clusters, and produces a short cross-source digest for each retained event.

The core pipeline is implemented and has produced a working dataset. The current repository snapshot contains 124 collected articles, 12 retained event clusters, and 12 generated digests. Python source files compile successfully.

The main interim concern is evaluation and event-quality validation. The pipeline currently uses a fixed cosine-distance threshold and removes only single-article clusters. It does not yet measure clustering precision/recall, verify that an event contains multiple independent sources, or systematically detect factual conflicts between source summaries.

## 2. Current architecture

```mermaid
flowchart LR
    F[RSS feeds\nBBC · Guardian · Al Jazeera · NYT · TOI]
    C[app.py\nFeed parsing + URL de-duplication]
    E[Trafilatura\nArticle text extraction]
    A[(articles.json)]
    M[cluster_headlines.py\nHeadline preprocessing]
    S[all-MiniLM-L6-v2\nSentence embeddings]
    K[Agglomerative clustering\nCosine distance = 0.38]
    G[(clustered_events.json)]
    Z[summarize_events.py\nPer-article summaries]
    B[facebook/bart-large-cnn\nBART generation]
    D[Cross-source digest\nSource summaries combined]
    O[(news_digest.json)]

    F --> C --> E --> A
    A --> M --> S --> K --> G
    G --> Z --> B --> D --> O
```

The editable standalone diagram is available in [architecture.mmd](architecture.mmd).

## 3. Component status

| Component | File | Status | Current behavior |
|---|---|---|---|
| Collection | `app.py` | Implemented | Reads five RSS feeds, fetches linked pages, extracts text, de-duplicates by URL, and appends valid records to `articles.json`. |
| Text extraction | `app.py` via Trafilatura | Implemented | Skips missing/short extraction results; minimum extracted text length is 300 characters. |
| Headline representation | `cluster_headlines.py` | Implemented | Uses normalized `all-MiniLM-L6-v2` sentence embeddings. |
| Event clustering | `cluster_headlines.py` | Implemented | Uses average-linkage agglomerative clustering with cosine distance threshold `0.38`. |
| Event filtering | `cluster_headlines.py` | Implemented, needs clarification | Retains clusters with at least two articles, not necessarily two distinct sources. |
| Summarization | `summarize_events.py` | Implemented | Summarizes each article and then summarizes the combined source summaries with BART. |
| Output persistence | All three scripts | Implemented | Writes JSON artifacts for the next pipeline stage. |
| Quality evaluation | — | Not implemented | No labeled test set, cluster metrics, factuality checks, or human review workflow exists yet. |
| User-facing interface | — | Not implemented | The project currently runs as command-line batch scripts. |

## 4. Data snapshot

The generated artifacts inspected in this interim review contain:

| Measure | Observed value |
|---|---:|
| Collected articles | 124 |
| Article sources represented | 4 in the saved dataset |
| BBC articles | 35 |
| Guardian articles | 45 |
| Al Jazeera articles | 24 |
| Times of India articles | 20 |
| Retained event clusters | 12 |
| Generated digests | 12 |
| Cluster sizes | 2–3 articles per event |
| Articles outside retained clusters | 97 |
| Mean extracted article length | ~4,059 characters |
| Mean digest length | ~240 characters |

The source configuration includes the New York Times feed, but no NYT records appear in the current saved `articles.json` snapshot. This may reflect feed availability, access restrictions, or extraction failure and should be checked during the next data refresh.

## 5. Processing flow

1. `app.py` loads existing `articles.json`, parses configured RSS feeds, fetches article pages, extracts the main text, and skips URLs already seen.
2. `cluster_headlines.py` removes records without titles, encodes titles as normalized sentence embeddings, and applies agglomerative clustering.
3. Clusters containing fewer than two articles are discarded and the remaining events are renumbered.
4. `summarize_events.py` loads BART, creates a summary for each article, combines those summaries, and produces one event digest.
5. The resulting JSON files can be inspected or consumed by a future UI/API layer.

## 6. Strengths demonstrated so far

- The pipeline is decomposed into clear, independently runnable stages.
- URL-based de-duplication makes repeated collection runs append-friendly.
- Sentence embeddings provide a semantic similarity signal beyond exact word overlap.
- Per-source summaries are preserved alongside the combined digest, supporting comparison between outlets.
- The code includes compatibility handling for older and newer scikit-learn clustering APIs.
- BART inference uses deterministic generation and disables gradients to reduce memory usage.
- The current scripts compile successfully with Python bytecode validation.

## 7. Risks and limitations

### Event-definition mismatch

The README describes the output as events reported by multiple sources, but the implementation filters on `article_count >= 2` only. A cluster can therefore contain multiple articles from one outlet. If “multi-source” is a hard requirement, filtering should use the number of distinct sources.

### Fixed clustering threshold

`DISTANCE_THRESHOLD = 0.38` is a manually chosen value. A threshold that is too low fragments events; a threshold that is too high merges unrelated stories. There is currently no labeled validation set to justify the value.

### Headline-only clustering

Article bodies are not used when forming clusters. Headlines can be short, ambiguous, or reused across related but distinct developments, which can cause both false merges and missed matches.

### Summarization reliability

The BART input is truncated to 1,024 tokens and the source text is capped at 5,000 characters. Important information near the end of an article can therefore be omitted. Generated text is not currently checked for unsupported claims, contradictions, or duplicated information.

### Reproducibility and operations

The project does not currently pin dependency versions, record model revisions, or capture run metadata such as feed timestamp, threshold, model device, and failures. Model downloads also require network access on the first run.

### Data freshness and source access

RSS feeds and article pages can change format or become unavailable. A failed fetch is printed and skipped, but failures are not persisted in a structured run log.

## 8. Recommended next steps

### Priority 1 — Make the event contract explicit

- Decide whether an event must contain two distinct sources.
- If yes, filter with `len(event["sources"]) >= 2` and update the README wording.
- Add a small validation script that reports singleton-source clusters and duplicate URLs.

### Priority 2 — Add measurable evaluation

- Create a manually labeled set of related/unrelated headline pairs.
- Report precision, recall, F1, and cluster-level purity for candidate thresholds such as 0.30, 0.34, 0.38, 0.42, and 0.45.
- Track the fraction of collected articles that become retained events.

### Priority 3 — Improve robustness

- Pin dependencies in `requirements.txt` or `pyproject.toml`.
- Persist run metadata and fetch failures.
- Add retry/backoff and timeouts around feed and article retrieval.
- Make output paths explicit and configurable instead of relying on the current working directory.

### Priority 4 — Improve digest quality

- Include article publication dates and source diversity in each event record.
- Compare body-text or entity signals with headline embeddings for borderline clusters.
- Add a factuality/conflict review step that flags disagreements between source summaries.
- Consider a smaller summarization model or configurable device/batch settings for faster local runs.

### Priority 5 — Add a usable delivery layer

- Provide a simple CLI command that runs the complete pipeline with one configuration.
- Add a lightweight web view or API for browsing events, source summaries, and original URLs.
- Display provenance prominently so users can inspect the underlying reports.

## 9. Interim conclusion

The project has a functioning end-to-end prototype and a useful intermediate artifact structure. It is ready for focused evaluation and hardening, but should not yet be treated as a validated news-event detection system. The next milestone should establish the event definition, add a labeled evaluation set, and measure the effect of the clustering threshold before expanding the user interface.
