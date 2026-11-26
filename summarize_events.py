"""Create a cross-source digest for every multi-article news event.

This is stage 3.  It performs hierarchical summarization: one summary per
article first, followed by one summary of the combined source summaries.
"""

import json  # Reads clustered events and writes digest records.
import os  # Checks whether the clustering artifact exists.

import torch  # Provides tensor inference and device selection.
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer  # Loads BART.


# The clustering script produces the input for this summarization stage.
INPUT_FILE = "clustered_events.json"
OUTPUT_FILE = "news_digest.json"
MODEL_NAME = "facebook/bart-large-cnn"
_MODEL_CACHE = None


def clean_text(text):
    """Collapse newlines and repeated whitespace before tokenization."""

    return " ".join(text.split())


def summarize(text, tokenizer, model, device, max_length, min_length):
    """Generate one deterministic summary using the BART model.

    `max_length` and `min_length` constrain the generated output in tokens.
    `do_sample=False` makes the same inputs produce repeatable beam-search
    output under the same model/runtime.
    """

    text = clean_text(text)

    if not text:
        return ""

    # This is a character-level guard before the tokenizer's token-level cap.
    text = text[:5000]

    try:
        # Tokenization converts text into model IDs and truncates long inputs.
        inputs = tokenizer(
            text,
            max_length=1024,
            truncation=True,
            return_tensors="pt",
        )

        inputs = {key: value.to(device) for key, value in inputs.items()}

        # Evaluation does not train the model, so gradient tracking is wasteful.
        with torch.no_grad():
            output_ids = model.generate(
                **inputs,
                max_length=max_length,
                min_length=min_length,
                num_beams=4,
                do_sample=False,
                no_repeat_ngram_size=3,
                early_stopping=True,
            )

        return tokenizer.decode(output_ids[0], skip_special_tokens=True)
    except Exception as error:
        # One failure should not erase the whole digest.  Keep a readable
        # excerpt so the event still has content for the dashboard.
        print(f"Could not summarize one article: {error}")
        return text[:500]


def load_summarizer():
    """Load BART once per server process and reuse it across button runs."""

    global _MODEL_CACHE
    if _MODEL_CACHE is not None:
        return _MODEL_CACHE

    # Load BART directly because newer Transformers versions removed the old
    # summarization pipeline task used by earlier versions of this project.
    print("Loading BART summarization model...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)
    # Use Apple's GPU backend on supported Macs; otherwise fall back to CPU.
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    model.to(device)
    model.eval()
    _MODEL_CACHE = tokenizer, model, device
    return _MODEL_CACHE


def create_digests(events, progress_callback=None):
    """Summarize each source and then combine the summaries into digests."""

    if not events:
        return []

    tokenizer, model, device = load_summarizer()

    digests = []

    for event_index, event in enumerate(events, start=1):
        print(f"Summarizing event {event['event_id']}...")
        if progress_callback:
            progress_callback({
                "type": "event_started",
                "event_id": event["event_id"],
                "index": event_index,
                "total": len(events),
            })
        source_summaries = []

        # First summarize each article independently.  Keeping these records
        # preserves source-level provenance and differing perspectives.
        for article in event["articles"]:
            article_summary = summarize(
                article.get("text", ""),
                tokenizer,
                model,
                device,
                max_length=90,
                min_length=25,
            )

            source_summaries.append({
                "source": article.get("source", "unknown"),
                "headline": article.get("title", ""),
                "summary": article_summary,
            })

        # The second pass compares the compact source summaries and produces
        # one event-level brief for the dashboard.
        comparison_text = " ".join(
            f"{item['source']} reported: {item['summary']}"
            for item in source_summaries
        )

        digest = summarize(
            comparison_text,
            tokenizer,
            model,
            device,
            max_length=120,
            min_length=40,
        )

        digests.append({
            "event_id": event["event_id"],
            "article_count": event["article_count"],
            "sources": event["sources"],
            "headlines": event["headlines"],
            "digest": digest,
            "source_summaries": source_summaries,
        })

        if progress_callback:
            progress_callback({"type": "digest", "digest": digests[-1]})

    return digests


def main():
    """Load clustered events, create digests, and write them to JSON."""

    if not os.path.exists(INPUT_FILE):
        print(f"{INPUT_FILE} not found. Run cluster_headlines.py first.")
        return

    with open(INPUT_FILE, "r", encoding="utf-8") as file:
        events = json.load(file)

    if not events:
        print("No multi-article events found.")
        return

    digests = create_digests(events)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        json.dump(digests, file, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(digests)} news digests to {OUTPUT_FILE}")

    for event in digests:
        print(f"\nEvent {event['event_id']}: {event['digest']}")


if __name__ == "__main__":
    main()
