"""Milestone 5 — Grounded generation.

Pipeline:
    question -> retrieve(top-k) -> filter matches -> Groq prompt -> result
"""

import os
from dotenv import load_dotenv
from groq import Groq
from embed import retrieve

load_dotenv()

MODEL = "llama-3.3-70b-versatile"
TOP_K = 4
# Cosine distance above this are dropped, as they are too weak.
RELEVANCE_THRESHOLD = 0.65
REFUSAL = "I don't have enough information on that. Can you ask something else?"

SYSTEM_PROMPT = f"""\
You are an assistant that answers questions about budget smartphones using ONLY \
the reference documents provided in the user message. Follow these rules:
1. Use only facts found in the provided documents. Do not use any outside or prior knowledge.
2. If the documents do not contain enough information to answer, reply exactly: "{REFUSAL}"
3. Do not invent specs, numbers, or opinions that are not in the documents.
4. When you state a fact, mention which document number ([1], [2], ...) it came from.\
"""

_client = None

def get_client() -> Groq:
    global _client
    if _client is None:
        key = os.environ.get("GROQ_API_KEY")
        if not key:
            raise SystemExit("GROQ_API_KEY is not set in .env")
        _client = Groq(api_key=key)
    return _client

# Format retrieved chunks as numbered and labelled reference documents.
def build_context(hits: list[dict]) -> str:
    blocks = []
    for i, h in enumerate(hits, 1):
        blocks.append(f"[{i}] (source: {h['source']})\n{h['text']}")
    return "\n\n".join(blocks)

# Return a grounded answer plus the sources it was allowed to draw from.
def ask(question: str, k: int = TOP_K) -> dict:
    hits = retrieve(question, k)
    relevant = [h for h in hits if h["distance"] <= RELEVANCE_THRESHOLD]

    if not relevant:
        return {"answer": REFUSAL, "sources": [], "chunks": hits}

    context = build_context(relevant)
    user_msg = (
        f"Reference documents:\n\n{context}\n\n"
        f"Question: {question}\n\n"
        "Answer using only the reference documents above."
    )

    resp = get_client().chat.completions.create(
        model=MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
    )
    answer = resp.choices[0].message.content.strip()

    # If the model refused, cite nothing
    if REFUSAL.rstrip(".").lower() in answer.lower():
        return {"answer": answer, "sources": [], "chunks": relevant}

    # Sources from the chunks actualy used
    sources, seen = [], set()
    for h in relevant:
        key = h["url"] or h["source"]
        if key not in seen:
            seen.add(key)
            sources.append({"source": h["source"], "url": h["url"]})

    return {"answer": answer, "sources": sources, "chunks": relevant}


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "How many years of updates does the CMF Phone 2 Pro get?"
    out = ask(q)
    print(f"Q: {q}\n\nA: {out['answer']}\n\nSources:")
    for s in out["sources"]:
        print(f"  - {s['source']}  ({s['url']})")
