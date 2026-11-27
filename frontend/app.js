// All mutable UI state lives here so rendering stays predictable.
const state = {
  data: null,
  pipeline: null,
  source: "all",
  query: "",
};

// Only one status poller is needed while the background pipeline is running.
let pipelinePoller = null;

// Short helper for selecting the first matching DOM element.
const $ = (selector) => document.querySelector(selector);

function escapeHTML(value = "") {
  // API data is inserted through template strings. Escaping prevents article
  // text or headlines from being interpreted as HTML/JavaScript.
  return String(value).replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#039;",
    '"': "&quot;",
  })[character]);
}

function formatDate(value) {
  // Convert publisher timestamps into compact relative dates for the feed.
  if (!value) return "date unknown";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value.split(",").slice(0, 2).join(",");
  const delta = Date.now() - parsed.getTime();
  const minutes = Math.floor(delta / 60000);
  if (minutes >= 0 && minutes < 60) return `${Math.max(minutes, 1)}m ago`;
  if (minutes >= 60 && minutes < 1440) return `${Math.floor(minutes / 60)}h ago`;
  return parsed.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function formatUpdated(value) {
  // Format the artifact timestamp shown in the top-right status area.
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "data ready";
  return `synced ${parsed.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
}

function normalize(value) {
  // Case-insensitive matching is enough for the local search feature.
  return String(value || "").toLowerCase();
}

function renderStats() {
  // Fill metric cards from the server payload and calculate coverage locally.
  const { metrics } = state.data;
  document.querySelectorAll("[data-stat]").forEach((node) => {
    node.textContent = metrics[node.dataset.stat] ?? "—";
  });
  const coverage = metrics.article_count
    ? Math.round((metrics.clustered_article_count / metrics.article_count) * 100)
    : 0;
  $("#coverage-stat").textContent = `${coverage}%`;
  $("#event-count-label").textContent = `${metrics.event_count} events`;
  $("#last-updated").textContent = formatUpdated(state.data.generated_at);
  $("#footer-status").textContent = `${metrics.summary_count} summaries / auto-refresh 60s`;
}

function renderSourceFilters() {
  // Rebuild buttons from the publishers actually present in the dataset.
  const sources = state.data.sources.map((source) => source.name);
  $("#source-filters").innerHTML = ["all", ...sources].map((source) => `
    <button class="filter-button ${state.source === source ? "selected" : ""}" data-source="${escapeHTML(source)}" type="button">
      ${source === "all" ? "all sources" : escapeHTML(source)}
    </button>
  `).join("");
  // Attach a listener to each newly generated button after replacing innerHTML.
  document.querySelectorAll(".filter-button").forEach((button) => {
    button.addEventListener("click", () => {
      state.source = button.dataset.source;
      renderSourceFilters();
      renderEvents();
    });
  });
}

function eventMatches(event) {
  // Search digest text, headlines, and source names, then apply source filter.
  const searchText = [event.digest, ...(event.headlines || []), ...(event.sources || [])].join(" ");
  return (state.source === "all" || event.sources.includes(state.source))
    && normalize(searchText).includes(normalize(state.query));
}

function sourceBadges(sources = []) {
  // Render one safe visual label per publisher.
  return sources.map((source) => `<span class="source-badge">${escapeHTML(source)}</span>`).join("");
}

function renderEvent(event, index) {
  // Build an expandable event card with headline and source-level evidence.
  const headlines = (event.headlines || []).map((headline) => `<li>${escapeHTML(headline)}</li>`).join("");
  const summaries = (event.source_summaries || []).map((item) => `
    <li class="summary-item">
      <span class="summary-source">${escapeHTML(item.source)}</span>
      <p>${escapeHTML(item.summary)}</p>
    </li>
  `).join("");
  const firstArticle = (event.articles || []).find((article) => article.url);
  const title = event.headlines?.[0] || `Event ${event.event_id}`;
  return `
    <details class="event-card" ${index === 0 ? "open" : ""}>
      <summary>
        <span class="event-number">${String(index + 1).padStart(2, "0")}</span>
        <span class="event-main">
          <span class="event-meta">${sourceBadges(event.sources)} <span>${event.article_count} voices</span></span>
          <span class="event-title">${escapeHTML(title)}</span>
          <span class="event-digest">${escapeHTML(event.digest || "Summary is being prepared.")}</span>
        </span>
        <span class="event-arrow" aria-hidden="true">›</span>
      </summary>
      <div class="event-detail">
        <div>
          <p class="detail-label">Related headlines</p>
          <ul class="headline-list">${headlines || "<li>Headlines are being indexed.</li>"}</ul>
          ${firstArticle ? `<a class="article-link" href="${escapeHTML(firstArticle.url)}" target="_blank" rel="noreferrer">open source ↗</a>` : ""}
        </div>
        <div>
          <p class="detail-label">Source perspectives</p>
          <ul class="summary-list">${summaries || "<li class=\"summary-item\"><p>No source summaries yet.</p></li>"}</ul>
        </div>
      </div>
    </details>
  `;
}

function renderEvents() {
  // Filter the event list in memory; no additional network request is needed.
  const events = state.data.events.filter(eventMatches);
  $("#events-list").innerHTML = events.length
    ? events.map(renderEvent).join("")
    : `<div class="empty-state">No event clusters match “${escapeHTML(state.query || state.source)}”.</div>`;
}

function renderFeed() {
  // Sort articles by publication date and show the eight newest records.
  const articles = [...state.data.articles]
    .sort((a, b) => new Date(b.published || 0) - new Date(a.published || 0))
    .slice(0, 8);
  $("#live-feed").innerHTML = articles.length ? articles.map((article) => `
    <article class="feed-item">
      <span class="feed-bar" aria-hidden="true"></span>
      <div>
        <div class="feed-source"><span>${escapeHTML(article.source || "unknown")}</span><span>${formatDate(article.published)}</span></div>
        <a class="feed-title" href="${escapeHTML(article.url || "#")}" target="_blank" rel="noreferrer">${escapeHTML(article.title)}</a>
      </div>
    </article>
  `).join("") : `<div class="empty-state">No articles collected yet.</div>`;
}

function renderSourceChart() {
  // Use the largest publisher count as 100% for proportional bar widths.
  const max = Math.max(...state.data.sources.map((source) => source.article_count), 1);
  $("#source-chart").innerHTML = state.data.sources.map((source) => `
    <div class="source-row">
      <span>${escapeHTML(source.name)}</span>
      <span class="source-track"><span class="source-fill" style="width:${(source.article_count / max) * 100}%"></span></span>
      <span class="source-count">${source.article_count}</span>
    </div>
  `).join("");
}

function renderPipelineRun() {
  // Render the live extraction → clustering → digestion state machine.
  const pipeline = state.pipeline || {
    status: "idle",
    stage: "idle",
    progress: 0,
    message: "Press “start a twelve-headline run” to begin extraction.",
    extracted: [],
    clusters: [],
    digests: [],
  };
  const button = $("#run-pipeline-button");
  const pill = $("#run-status-pill");
  const fill = $("#run-progress-fill");
  const stageOrder = ["extracting", "clustering", "digesting", "complete"];
  const currentIndex = stageOrder.indexOf(pipeline.stage);
  const running = pipeline.status === "running";

  button.disabled = running;
  button.innerHTML = running
    ? "<span aria-hidden=\"true\">◌</span> pipeline running..."
    : "<span aria-hidden=\"true\">▶</span> start a twelve-headline run";
  pill.textContent = pipeline.status === "completed" ? "complete" : pipeline.status;
  pill.className = `run-status-pill ${pipeline.status}`;
  fill.style.width = `${pipeline.progress || 0}%`;
  $("#run-message").textContent = pipeline.message || "Ready.";

  document.querySelectorAll("[data-run-stage]").forEach((node) => {
    const stageIndex = stageOrder.indexOf(node.dataset.runStage);
    node.classList.toggle(
      "active",
      running && node.dataset.runStage === pipeline.stage,
    );
    node.classList.toggle(
      "complete",
      pipeline.status === "completed"
        ? node.dataset.runStage === "complete" || stageIndex < 3
        : currentIndex > stageIndex && currentIndex >= 0,
    );
  });

  const error = $("#run-error");
  error.hidden = !pipeline.error;
  error.textContent = pipeline.error ? `Error: ${pipeline.error}` : "";

  const hasResults = pipeline.extracted?.length || pipeline.clusters?.length || pipeline.digests?.length;
  $("#run-results").hidden = !hasResults;
  if (!hasResults) return;

  $("#run-extracted").innerHTML = (pipeline.extracted || []).map((article) => `
    <div class="run-result-item">
      <span class="run-result-source">${escapeHTML(article.source)}</span>
      <p class="run-result-title">${escapeHTML(article.title)}</p>
      <div class="run-result-meta">${article.text_length || 0} characters extracted</div>
    </div>
  `).join("");

  $("#run-clusters").innerHTML = (pipeline.clusters || []).map((cluster) => `
    <div class="run-cluster">
      <p class="run-cluster-title">Topic ${cluster.event_id} · ${cluster.article_count} headline(s)</p>
      <ul>${(cluster.headlines || []).map((headline) => `<li>${escapeHTML(headline)}</li>`).join("")}</ul>
      <div class="run-result-meta">${(cluster.sources || []).map(escapeHTML).join(" · ")}</div>
    </div>
  `).join("");

  $("#run-digests").innerHTML = (pipeline.digests || []).map((digest) => `
    <div class="run-digest">
      <p class="run-result-meta">Topic ${digest.event_id} · ${(digest.sources || []).map(escapeHTML).join(" · ")}</p>
      <p class="run-digest-text">${escapeHTML(digest.digest || "Digest is being prepared.")}</p>
      ${(digest.source_summaries || []).map((item) => `
        <p class="run-source-summary"><strong>${escapeHTML(item.source)}:</strong> ${escapeHTML(item.summary)}</p>
      `).join("")}
    </div>
  `).join("");
}

function render() {
  // One render pass keeps all dashboard regions synchronized with state.data.
  renderStats();
  renderSourceFilters();
  renderEvents();
  renderFeed();
  renderSourceChart();
  renderPipelineRun();
}

async function loadPipelineStatus() {
  // Poll only the small status payload; the main dashboard data remains cached
  // separately from the interactive run results.
  try {
    const response = await fetch(`/api/pipeline/status?ts=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.pipeline = await response.json();
    renderPipelineRun();
    if (state.pipeline.status === "running" && !pipelinePoller) {
      pipelinePoller = setInterval(loadPipelineStatus, 1000);
    }
    if (state.pipeline.status !== "running" && pipelinePoller) {
      clearInterval(pipelinePoller);
      pipelinePoller = null;
    }
  } catch (error) {
    console.error(error);
  }
}

async function startPipeline() {
  // Start the server-side background job and immediately begin polling it.
  try {
    const response = await fetch("/api/pipeline/run", { method: "POST" });
    state.pipeline = await response.json();
    renderPipelineRun();
    if ((response.ok || response.status === 409) && !pipelinePoller) {
      pipelinePoller = setInterval(loadPipelineStatus, 1000);
    }
  } catch (error) {
    state.pipeline = {
      status: "error",
      stage: "error",
      progress: 0,
      message: "Could not contact the pipeline server.",
      error: error.message,
      extracted: [],
      clusters: [],
      digests: [],
    };
    renderPipelineRun();
  }
}

async function loadData(showLoading = false) {
  // Fetch a fresh payload. The timestamp query and no-store request prevent
  // stale browser/proxy caching when the JSON artifacts change on disk.
  if (showLoading) $("#footer-status").textContent = "refreshing pipeline data";
  try {
    const response = await fetch(`/api/data?ts=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.data = await response.json();
    render();
  } catch (error) {
    $("#footer-status").textContent = "could not connect to data server";
    if (!state.data) {
      // Give a first-load user an actionable error message; keep old data if a
      // later refresh fails so the dashboard remains useful.
      $("#events-list").innerHTML = `<div class="empty-state">The dashboard server is not reachable. Run <code>python server.py</code> from the project folder.</div>`;
      $("#live-feed").innerHTML = "";
    }
    console.error(error);
  }
}

// Search updates only the event list, so the other dashboard regions do not
// need to be rebuilt on every keystroke.
$("#search-input").addEventListener("input", (event) => {
  state.query = event.target.value;
  if (state.data) renderEvents();
});
// Manual refresh is useful after running a pipeline stage from the terminal.
$("#refresh-button").addEventListener("click", () => loadData(true));
$("#run-pipeline-button").addEventListener("click", startPipeline);

// Initial load followed by one-minute polling for new pipeline artifacts.
loadData();
loadPipelineStatus();
setInterval(() => loadData(), 60000);
