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

## Streamlit dashboard

The main deployable app is [`streamlit_app.py`](streamlit_app.py). It provides
the frontend and backend workflow in one Streamlit page: the **Start Pipeline**
button extracts at most twelve valid headlines, clusters them, and generates
compact digests while showing each stage's results.

Run it locally:

```bash
streamlit run streamlit_app.py
```

### Deploy to Streamlit Community Cloud

1. Push the repository to GitHub, including `streamlit_app.py`,
   `requirements.txt`, and the three JSON artifacts.
2. Open <https://share.streamlit.io> and sign in with GitHub.
3. Click **Create app** → **Yup, I have an app**.
4. Select repository `Jaswanthh22/Multi-Document-News-Event-Clustering-and-Digest`.
5. Select branch `main`.
6. Set the main file path to `streamlit_app.py`.
7. Choose an app URL and click **Deploy**.

Streamlit Community Cloud reads the dependencies from `requirements.txt` and
deploys the selected Python entrypoint from GitHub. The first run can take a
while because the embedding and BART models need to download. [Streamlit deployment guide](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)

## Legacy HTTP dashboard

The project also includes a dependency-free HTTP dashboard at `frontend/`. It reads
the three JSON artifacts above through `server.py`, so the UI updates when a
new pipeline run replaces the files.

For interview preparation, open [`viva_guide.html`](viva_guide.html) directly
in a browser. It explains the architecture, file-by-file behavior, NLP terms,
parameters, limitations, and likely viva questions with model answers.

Start the dashboard from the project directory:

```bash
python server.py
```

Open <http://127.0.0.1:8000>. The legacy dashboard includes:

- pipeline metrics for collected articles, clusters, publishers, and cluster coverage;
- expandable cross-source event summaries with related headlines and source perspectives;
- a live article feed with links back to the original stories;
- source-mix visualization, search, publisher filters, manual refresh, and automatic refresh every 60 seconds.
- a **Start Pipeline** button that runs a bounded twelve-headline extraction,
  semantic clustering, and BART digestion job in the background while showing
  progress and compact stage results.

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

The deployed service serves the committed JSON snapshot on initial load. The
dashboard's **Start Pipeline** button can also run a bounded live job using the
full `requirements.txt` dependencies: it collects at most twelve valid headlines
from multiple feeds, clusters them, and generates compact digests. The first
interactive run may take longer because the embedding and BART models must be
downloaded and loaded. The current interactive results live in server memory;
for durable historical storage, use a database or a scheduled worker with
persistent storage.

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
