"""Milestone 3 — Document ingestion and chunking pipeline.

Pipeline:
    documents/*.pdf  ->  load (pdfplumber)  ->  save raw  ->  clean  ->  chunk  ->  chunks.jsonl
"""

import json
import re
import pdfplumber
from pathlib import Path

## configuration

DOCS_DIR = Path("documents")
SOURCES_FILE = DOCS_DIR / "sources.json"   # maps each PDF filename -> real URL
RAW_DIR = Path("data/raw")
CLEAN_DIR = Path("data/clean")
CHUNKS_FILE = Path("data/chunks.jsonl")

MAX_CHARS = 600          # chunk size cap
OVERLAP_RATIO = 0.20     # 20% overlap

## Lines containing any of these are removed.

# Boilerplate that appears on the GSMArena / PhoneArena / Tom's Guide pages.
NAV_SNIPPETS = [
    "phone finder", "all brands", "rumor mill", "daily deals", "become a fan",
    "post your opinion", "search opinions", "share follow us", "follow us",
    "newsletter", "read more", "advertisement", "sponsored", "cookie",
    "sort by:", "pages:", "hits", "specifications", "compare", "pictures",
    "show all deals", "related devices", "popular from", "more from",
    "more related", "gb ram", "show more",
    "tip us", "merch", "mobile version", "android app", "contact us",
    "terms of use", "popular reviews", "show all prices", "electric vehicles",
    "to top", "to footer", "gsmarena.com tests", "total of", "rss ev",
]

# Exact lines that are pure nav and never content.
EXACT_DROP = {"search", "introduction", "pricing"}
# Brand-list nav rows (e.g. advertisements). If a line is mostly these tokens, it's not related content.
BRAND_TOKENS = {
    "samsung", "xiaomi", "ulefone", "infinix", "apple", "google", "alcatel",
    "asus", "huawei", "honor", "zte", "tecno", "nokia", "oppo", "rugone",
    "doogee", "sony", "realme", "umidigi", "blackview", "lg", "oneplus",
    "coolpad", "cubot", "htc", "nothing", "oscal", "oukitel", "motorola",
    "vivo", "sharp", "itel", "lenovo", "meizu", "micromax", "tcl",
}
# Footer pagination 
FOOTER_RE = re.compile(r"^\d+\s+of\s+\d+\s+\d+/\d+/\d+")
# Bold text in GSMArena PDFs renders every character doubled ("AAnnddrrooiidd"),
DOUBLED_RE = re.compile(r"(?:([A-Za-z0-9])\1){3,}")
# Deal-box sidebar rows carrying a currency price ("£999.00", "$749").
PRICE_RE = re.compile(r"[£$€]\s*[\d,]+")
# Broken or unrendable ASCII glyphs
GLYPH_RE = re.compile(r"[-☀-➿☆★▼▲◄►●○■□]")
URL_RE = re.compile(r"https?://\S+")

## Helper functions

#  Extract text from every PDF.
def load_pdf(path: Path) -> str:
    parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)

# The print-to-PDF header truncates long URLs with an ellipsis, so the URL
# can't be reliably harvested from the page text. Instead read each document's
# real, canonical URL from documents/sources.json (filename -> URL).
def load_source_urls() -> dict:
    if not SOURCES_FILE.exists():
        raise SystemExit(f"{SOURCES_FILE} not found — needed for source attribution.")
    return json.loads(SOURCES_FILE.read_text(encoding="utf-8"))

def _is_brand_nav(line: str) -> bool:
    words = [w for w in re.split(r"\s+", line.lower()) if w.isalpha()]
    if len(words) < 2:
        return False
    hits = sum(1 for w in words if w in BRAND_TOKENS)
    return hits / len(words) >= 0.6

# Strip nav, footers, glyphs, and boilerplate
def clean_text(raw: str, url: str) -> str:
    text = GLYPH_RE.sub(" ", raw)
    text = URL_RE.sub("", text) # drop embedded URLs
    text = (text.replace("&amp;", "&").replace("&nbsp;", " ")
                .replace("&quot;", '"').replace("&#39;", "'").replace("&lt;", "<")
                .replace("&gt;", ">")) # leftover HTML entities

    kept = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if FOOTER_RE.match(line):
            continue
        low = line.lower()
        if low in EXACT_DROP:
            continue
        if any(snip in low for snip in NAV_SNIPPETS):
            continue
        if "©" in line:                    # footer copyright line
            continue
        if _is_brand_nav(line):
            continue
        if DOUBLED_RE.search(line): # bold-rendering spec gibberish
            continue
        if PRICE_RE.search(line):# deal-box sidebar prices
            continue
        # All-caps "popular reviews" sidebar links (e.g. "XIAOMI 17T PRO REVIEW").
        if line.isupper() and line.endswith("REVIEW"):
            continue
        # Drop very short all-caps menu fragments (e.g. "REPLY", "REVIEW")
        if len(line) <= 8 and line.isupper():
            continue
        kept.append(line)

    cleaned = "\n".join(kept)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)# collapse runs of spaces
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)# collapse blank lines
    return cleaned.strip()


def chunk_text(text: str, max_chars: int = MAX_CHARS,
               overlap_ratio: float = OVERLAP_RATIO) -> list[str]:
    """.
    Greedily packs lines into a chunk until adding the next one would
    exceed `max_chars`. Lines longer than max_chars are hard-split.
    Each new chunk is seeded with the trailing `overlap_ratio` of the
    previous chunk so context is not lost across boundaries.

    The PDF extractor emits one line per visual line (single newlines, never
    blank lines), so each line is the atomic unit here: a single user comment
    or a sentence of a review. Packing on line boundaries keeps a comment or
    sentence whole instead of cutting it mid-word.
    """
    paragraphs = [ln.strip() for ln in text.split("\n") if ln.strip()]
    overlap_chars = int(max_chars * overlap_ratio)

    chunks: list[str] = []
    current = ""

    def flush():
        nonlocal current
        if current.strip():
            chunks.append(current.strip())
        current = ""

    for para in paragraphs:
        # Hard-split any single paragraph that is itself too large.
        while len(para) > max_chars:
            head, para = para[:max_chars], para[max_chars:]
            flush()
            chunks.append(head)
        if not current:
            current = para
        elif len(current) + 1 + len(para) <= max_chars:
            current += "\n" + para
        else:
            tail = current[-overlap_chars:] if overlap_chars else ""
            if tail and " " in tail:           # snap overlap to a word boundary
                tail = tail[tail.index(" ") + 1:]
            flush()
            current = (tail + "\n" + para).strip() if tail else para
    flush()
    return chunks


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    CHUNKS_FILE.parent.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(DOCS_DIR.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"No PDFs found in {DOCS_DIR}/")

    source_urls = load_source_urls()
    missing = [p.name for p in pdfs if p.name not in source_urls]
    if missing:
        raise SystemExit(f"No URL in sources.json for: {missing}")

    all_records = []
    summary = []

    for pdf_path in pdfs:
        stem = pdf_path.stem
        raw = load_pdf(pdf_path)
        url = source_urls[pdf_path.name]
        (RAW_DIR / f"{stem}.txt").write_text(raw, encoding="utf-8")

        cleaned = clean_text(raw, url)
        (CLEAN_DIR / f"{stem}.txt").write_text(cleaned, encoding="utf-8")

        chunks = chunk_text(cleaned)
        for i, ch in enumerate(chunks):
            all_records.append({
                "id": f"{stem}::chunk-{i}",
                "source": stem,
                "url": url,
                "text": ch,
            })
        summary.append((stem, len(raw), len(cleaned), len(chunks)))

    with CHUNKS_FILE.open("w", encoding="utf-8") as f:
        for rec in all_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # report
    print(f"{'document':<55} {'raw':>8} {'clean':>8} {'chunks':>7}")
    print("-" * 82)
    for stem, nraw, nclean, nch in summary:
        print(f"{stem[:54]:<55} {nraw:>8} {nclean:>8} {nch:>7}")
    print("-" * 82)
    print(f"{'TOTAL':<55} {'':>8} {'':>8} {len(all_records):>7}")
    print(f"\nWrote {len(all_records)} chunks to {CHUNKS_FILE}")


if __name__ == "__main__":
    main()
