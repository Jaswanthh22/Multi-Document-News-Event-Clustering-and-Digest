# Multi-Document News Event Clustering and Digest

This project collects news articles from multiple RSS feeds, groups headlines
that describe the same real-world event, and creates a short digest from the
articles in each group.

## Project pipeline

```text
RSS feeds
   |
   v
app.py --------------------> articles.json
                                  |
                                  v
                         cluster_headlines.py
                                  |
                                  v
                         clustered_events.json
                                  |
                                  v
                         summarize_events.py
                                  |
                                  v
                            news_digest.json
```

The pipeline has three stages:

1. `app.py` downloads RSS entries and extracts article text.
2. `cluster_headlines.py` converts headlines into sentence embeddings and
   groups semantically similar headlines with agglomerative clustering.
3. `summarize_events.py` summarizes each article with BART and combines the
   source summaries into one event digest.

Only clusters containing at least two articles are saved. This removes topics
that were reported by only one source.

## Requirements

- Python 3.10 or newer
- Internet access for RSS feeds, article pages, and the first model download
- A virtual environment is recommended.

Create and activate the virtual environment from this project directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the dependencies:

```bash
python -m pip install feedparser trafilatura sentence-transformers scikit-learn transformers torch
```

If the virtual environment is not activated, use `.venv/bin/python` and
`.venv/bin/pip` instead of `python` and `pip`.

## How to run

Run the stages in this order:

```bash
source .venv/bin/activate
python app.py
python cluster_headlines.py
python summarize_events.py
```

## News dashboard

The project includes a dependency-free web dashboard at `frontend/`. It reads
the three JSON artifacts above through `server.py`, so the UI updates when a
new pipeline run replaces the files.

For interview preparation, open [`viva_guide.html`](viva_guide.html) directly
in a browser. It explains the architecture, file-by-file behavior, NLP terms,
parameters, limitations, and likely viva questions with model answers.

Start the dashboard from the project directory:

```bash
python server.py
```

Open <http://127.0.0.1:8000>. The dashboard includes:

- pipeline metrics for collected articles, clusters, publishers, and cluster coverage;
- expandable cross-source event summaries with related headlines and source perspectives;
- a live article feed with links back to the original stories;
- source-mix visualization, search, publisher filters, manual refresh, and automatic refresh every 60 seconds.

### Deploy to Render

The repository includes [`render.yaml`](render.yaml) for a single Render Web
Service. `server.py` serves both `frontend/` and the JSON-backed `/api/data`
endpoint, so the frontend and backend deploy together without CORS setup.

1. Commit and push the repository, including `articles.json`,
   `clustered_events.json`, `news_digest.json`, `frontend/`, `server.py`, and
   `render.yaml`.
2. In Render, choose **New → Blueprint**, select the GitHub repository, and
   apply the detected `render.yaml`.
3. Render runs `pip install -r requirements-render.txt`, starts `python
   server.py`, checks `/api/health`, and gives the service an `onrender.com`
   URL.

The deployed service serves the JSON snapshot committed to Git. To refresh the
data, run the three pipeline scripts locally with the full `requirements.txt`
dependencies, review the generated JSON, commit the artifacts, and push again.
For continuously running collection and model inference, use a separate worker
or scheduled job and persistent storage rather than relying on the web service
filesystem.

The current pipeline stores its database-like artifacts as `articles.json`,
`clustered_events.json`, and `news_digest.json`. If those outputs are later
backed by a database, only the payload builder in `server.py` needs to change;
the frontend API contract can remain the same.

The first model-based run downloads:

- `all-MiniLM-L6-v2` for headline embeddings
- `facebook/bart-large-cnn` for summarization

The models are cached locally after download.

## Output files

### `articles.json`

Created by `app.py`. Each article contains:

```json
{
  "source": "bbc",
  "title": "Article headline",
  "url": "https://example.com/article",
  "published": "Publication date",
  "text": "Extracted article text"
}
```

Articles are deduplicated by URL. Pages with no extracted text or fewer than
300 characters are skipped.

### `clustered_events.json`

Created by `cluster_headlines.py`. Each event contains its headlines, source
names, article count, and the original article records:

```json
{
  "event_id": 1,
  "article_count": 3,
  "sources": ["bbc", "guardian", "aljazeera"],
  "headlines": ["..."],
  "articles": ["..."]
}
```

### `news_digest.json`

Created by `summarize_events.py`. Each event contains a combined `digest` and
the individual `source_summaries`, which makes it possible to compare how
different outlets reported the same event.

## Clustering configuration

The clustering threshold is set in `cluster_headlines.py`:

```python
DISTANCE_THRESHOLD = 0.38
```

This is cosine distance:

- Lower values create stricter, smaller clusters.
- Higher values create broader clusters.

Try values around `0.30` to `0.45` if the grouping is too strict or too broad.

## Troubleshooting

### `No such file or directory: .venv/bin/activate`

Create the environment first:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### `python: command not found`

Activate the virtual environment or run the script directly:

```bash
.venv/bin/python app.py
```

### Invalid or empty `articles.json`

`app.py` treats an empty or invalid existing file as an empty dataset and
rebuilds it from the feeds.

### SOCKS `PySocks` warning

This warning is only relevant when a SOCKS proxy is configured. Install the
optional package if needed:

```bash
python -m pip install PySocks
```

### BART pipeline error

Transformers v5 removed the old `pipeline("summarization")` task. The current
`summarize_events.py` loads BART directly with
`AutoModelForSeq2SeqLM` and `AutoTokenizer`.

## Files

| File | Purpose |
| --- | --- |
| `app.py` | Collect and extract articles |
| `cluster_headlines.py` | Cluster related headlines |
| `summarize_events.py` | Generate cross-source summaries |
| `articles.json` | Collected article data |
| `clustered_events.json` | Multi-article event groups |
| `news_digest.json` | Final event digests |
| `README.md` | Project documentation |
