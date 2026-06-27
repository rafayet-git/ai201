"""Pre-label raw r/youtubedrama comments with Groq (llama-3.3-70b-versatile).

This is annotation ASSISTANCE, not ground truth. It fills a `prelabel` column;
you must read every comment and correct the `label` column yourself. The script
seeds `label` = `prelabel` so you only edit the ones the model got wrong, and it
keeps both columns so you can report your override rate (see planning.md AI plan).

This is SEPARATE from the zero-shot baseline in the notebook (which runs only on
the held-out test set). Do not reuse these prelabels as the baseline.

Setup (run locally, NOT in Colab):
    pip install groq python-dotenv
    echo 'GROQ_API_KEY=gsk_...' >> .env        # same key as Projects 1-2

Usage:
    python prelabel.py                 # pre-label all rows missing a prelabel
    python prelabel.py --limit 10      # dry-run a few first
    python prelabel.py --force         # re-label every row

In:  data/raw_comments.csv   (from parse.py)
Out: data/labeled.csv        (id, thread, score, words, text, prelabel, label, notes)
"""
import argparse
import csv
import os
import sys
import time

from groq import Groq
from dotenv import load_dotenv

load_dotenv()

IN = "data/raw_comments.csv"
OUT = "data/labeled.csv"
MODEL = "llama-3.3-70b-versatile"
LABELS = {"information", "opinion", "reaction"}

# Definitions copied from planning.md so the pre-labeler applies the SAME rules
# you'll apply by hand. Keep this in sync if you revise the taxonomy.
SYSTEM_PROMPT = """You classify comments from r/youtubedrama, a subreddit about \
conflicts and controversies between online creators. Assign each comment to \
exactly ONE of these three labels.

information: relays a specific, checkable fact about the drama — who is involved, \
what happened, a direct quote, a date, a named video/tweet/stream, a link, or a \
concrete sequence of events. The value is the verifiable content.
Example: "So far Coffeezilla is starting an investigation and LegalEagle reached out to offer help."

opinion: a judgment, prediction, or piece of reasoning stated WITHOUT specific \
verifiable evidence. Covers both lazy verdicts and analysis that cites no sources.
Example: "Who would've guessed that the grifters who complain about free speech don't believe in it."

reaction: a comedic, expressive, or emotional response with no checkable fact and \
no real argument — memes, riffs, one-liners, jokes, shock.
Example: "So... the Mormons are acting like a mafia over Lego!?"

Decision order when a comment fits more than one: information > opinion > reaction. \
A concrete checkable fact makes it `information` even if it's also opinionated or \
jokey. A take with no checkable fact is `opinion`. A joke/emotional line with no \
fact and no argument is `reaction` no matter how long it is.

Respond with ONLY the label name: information, opinion, or reaction. No other text."""


def classify(client, text):
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Classify this comment:\n\n{text}"},
            ],
            temperature=0,
            max_tokens=8,
        )
        raw = resp.choices[0].message.content.strip().lower()
        for label in LABELS:
            if raw == label or label in raw:
                return label
        return ""  # unparseable — review by hand
    except Exception as e:
        print(f"  API error: {e}", file=sys.stderr)
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="only label first N missing rows")
    ap.add_argument("--force", action="store_true", help="re-label rows that already have a prelabel")
    args = ap.parse_args()

    key = os.environ.get("GROQ_API_KEY")
    if not key:
        sys.exit("GROQ_API_KEY not set — add it to .env (GROQ_API_KEY=gsk_...)")
    client = Groq(api_key=key)

    # Prefer resuming from OUT (keeps prelabels/labels/notes already done).
    src = OUT if os.path.exists(OUT) else IN
    with open(src, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r.setdefault("prelabel", "")
        r.setdefault("label", "")
        r.setdefault("notes", "")

    done = 0
    for r in rows:
        if r["prelabel"] and not args.force:
            continue
        if args.limit and done >= args.limit:
            break
        label = classify(client, r["text"])
        r["prelabel"] = label
        if not r["label"]:          # seed label for review; never clobber a hand edit
            r["label"] = label
        done += 1
        if done % 10 == 0:
            print(f"  {done} labeled...")
        time.sleep(0.15)            # respect free-tier rate limits

    fields = ["id", "thread", "score", "words", "text", "prelabel", "label", "notes"]
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    dist = {}
    for r in rows:
        dist[r["prelabel"] or "(none)"] = dist.get(r["prelabel"] or "(none)", 0) + 1
    print(f"\nPre-labeled {done} comments. Wrote {len(rows)} rows to {OUT}")
    print("prelabel distribution:", dist)
    print("\nNext: open data/labeled.csv, READ each comment, and fix the `label` column "
          "where the model is wrong. Note tricky calls in `notes`.")


if __name__ == "__main__":
    main()
