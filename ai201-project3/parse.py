"""Parse raw Reddit .json dumps into a flat CSV for TakeMeter labeling.

These are dumps from Reddit's public .json endpoints (no API key needed):
  - A thread dump is a 2-element list: [post_listing, comment_listing].
    Comments are `t1` nodes; replies nest under data["replies"] (a Listing or "").
  - top_posts.json is a single Listing of `t3` posts (no comments) — skipped here,
    it only tells us which threads exist.

Usage:
  python parse.py 1tt36b0.json 1ubb5yc.json        # explicit files
  python parse.py                                   # defaults below

Writes data/raw_comments.csv with columns:
  id, thread, score, words, text, prelabel, label
Leave `prelabel`/`label` empty; fill `label` during annotation.
"""
import csv
import json
import re
import sys
from pathlib import Path

DEFAULT_FILES = ["1tt36b0.json", "1ubb5yc.json"]
MIN_WORDS = 5
MAX_WORDS = 400
OUT = Path("data/raw_comments.csv")

SKIP_AUTHORS = {"AutoModerator", "[deleted]", None}
BAD_BODIES = {"[deleted]", "[removed]", ""}


def clean(text: str) -> str:
    text = (text or "").replace("\n", " ").strip()
    return re.sub(r"\s+", " ", text)


def walk_comments(children, thread_title, rows, seen):
    """Recursively collect t1 comment bodies from a comment-listing tree."""
    for ch in children:
        if ch.get("kind") != "t1":
            continue  # skips "more" stubs and anything non-comment
        c = ch["data"]
        author = c.get("author")
        body = (c.get("body") or "").strip()
        cid = c.get("id")
        if author not in SKIP_AUTHORS and body not in BAD_BODIES and cid not in seen:
            text = clean(body)
            n = len(text.split())
            if MIN_WORDS <= n <= MAX_WORDS:
                seen.add(cid)
                rows.append(
                    {
                        "id": cid,
                        "thread": thread_title[:120],
                        "score": c.get("score", 0),
                        "words": n,
                        "text": text,
                        "prelabel": "",
                        "label": "",
                    }
                )
        # Recurse into replies (a Listing dict, or "" when there are none).
        replies = c.get("replies")
        if isinstance(replies, dict):
            walk_comments(replies["data"]["children"], thread_title, rows, seen)


def parse_thread(path, rows, seen):
    data = json.load(open(path, encoding="utf-8"))
    if not (isinstance(data, list) and len(data) == 2):
        print(f"  skip {path}: not a [post, comments] thread dump")
        return 0
    title = clean(data[0]["data"]["children"][0]["data"].get("title", path))
    before = len(rows)
    walk_comments(data[1]["data"]["children"], title, rows, seen)
    added = len(rows) - before
    print(f"  {path}: +{added} comments  ({title[:60]})")
    return added


def main():
    files = sys.argv[1:] or DEFAULT_FILES
    rows, seen = [], set()
    print("Parsing threads:")
    for f in files:
        if Path(f).exists():
            parse_thread(f, rows, seen)
        else:
            print(f"  missing: {f}")

    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh, fieldnames=["id", "thread", "score", "words", "text", "prelabel", "label"]
        )
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {len(rows)} comments to {OUT}")
    if len(rows) < 200:
        print(
            f"NOTE: only {len(rows)} labelable comments. Dump 1-2 more threads "
            "(append .json to any thread URL) and pass them to this script to clear 200."
        )


if __name__ == "__main__":
    main()
