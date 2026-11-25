"""Create a cross-source digest for every multi-article news event."""

import json
import os

import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer


# The clustering script produces the input for this summarization stage.
INPUT_FILE = "clustered_events.json"
OUTPUT_FILE = "news_digest.json"
MODEL_NAME = "facebook/bart-large-cnn"


def clean_text(text):
    """Collapse newlines and repeated whitespace before tokenization."""

    return " ".join(text.split())


def summarize(text, tokenizer, model, device, max_length, min_length):
    """Generate one deterministic summary using the BART model."""

    text = clean_text(text)

    if not text:
        return ""

    # Keep the character input reasonably small before tokenizer truncation.
    text = text[:5000]

    try:
        # BART accepts at most 1,024 input tokens in this configuration.
        inputs = tokenizer(
            text,
            max_length=1024,
            truncation=True,
            return_tensors="pt",
        )

        inputs = {key: value.to(device) for key, value in inputs.items()}

        # Inference does not need gradients, which reduces memory usage.
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
        # Preserve a short text fallback if a single article cannot be decoded.
        print(f"Could not summarize one article: {error}")
        return text[:500]


def main():
    """Summarize each source and then combine the summaries into a digest."""

    if not os.path.exists(INPUT_FILE):
        print(f"{INPUT_FILE} not found. Run cluster_headlines.py first.")
        return

    with open(INPUT_FILE, "r", encoding="utf-8") as file:
        events = json.load(file)

    if not events:
        print("No multi-article events found.")
        return

    # Transformers v5 removed the summarization pipeline, so load BART
    # directly and call model.generate() below.
    print("Loading BART summarization model...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)
    # Use Apple's GPU backend when available; otherwise use the CPU.
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    model.to(device)
    model.eval()

    digests = []

    for event in events:
        print(f"Summarizing event {event['event_id']}...")
        source_summaries = []

        # First summarize each source independently so the digest can retain
        # information that differs between reports.
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

        # Combining source summaries gives one short cross-source digest.
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

    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        json.dump(digests, file, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(digests)} news digests to {OUTPUT_FILE}")

    for event in digests:
        print(f"\nEvent {event['event_id']}: {event['digest']}")


if __name__ == "__main__":
    main()
