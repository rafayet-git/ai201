"""Milestone 4 — Embedding and retrieval.

Pipeline:
    data/chunks.jsonl  ->  embed (all-MiniLM-L6-v2)  ->  ChromaDB  ->  retrieve(query, k)

Build the index:   python embed.py --rebuild
Test retrieval:    python embed.py
"""

import argparse
import json
import chromadb
from pathlib import Path
from sentence_transformers import SentenceTransformer

CHUNKS_FILE = Path("data/chunks.jsonl")
CHROMA_DIR = Path("data/chroma")
COLLECTION = "budget_phones"
MODEL_NAME = "all-MiniLM-L6-v2"
# Cosine distance so scores fall in [0, 2]; smaller = more similar.
COLLECTION_METADATA = {"hnsw:space": "cosine"}

_model = None

# Load the embedding model once and reuse it.
def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def get_collection():
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(
        name=COLLECTION, metadata=COLLECTION_METADATA
    )

# Embed every chunk and (re)load it into ChromaDB with metadata.
def build_index() -> None:
    if not CHUNKS_FILE.exists():
        raise SystemExit(f"{CHUNKS_FILE} not found — run ingest.py first.")

    records = [json.loads(line) for line in CHUNKS_FILE.read_text().splitlines() if line.strip()]

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    # Start clean so re-runs don't duplicate or leave stale chunks behind.
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    collection = client.create_collection(name=COLLECTION, metadata=COLLECTION_METADATA)

    model = get_model()
    texts = [r["text"] for r in records]
    print(f"Embedding {len(texts)} chunks with {MODEL_NAME} ...")
    embeddings = model.encode(texts, show_progress_bar=True, normalize_embeddings=True)

    collection.add(
        ids=[r["id"] for r in records],
        documents=texts,
        embeddings=[e.tolist() for e in embeddings],
        metadatas=[
            {
                "source": r["source"],
                "url": r["url"],
                "position": int(r["id"].rsplit("-", 1)[-1]),  # chunk index in doc
            }
            for r in records
        ],
    )
    print(f"Stored {collection.count()} chunks in ChromaDB at {CHROMA_DIR}/")

# Return the top-k most relevant chunks for a query, with source + distance.
def retrieve(query: str, k: int = 4):
    collection = get_collection()
    q_emb = get_model().encode([query], normalize_embeddings=True)[0].tolist()
    res = collection.query(query_embeddings=[q_emb], n_results=k)
    hits = []
    for doc, meta, dist in zip(
        res["documents"][0], res["metadatas"][0], res["distances"][0]
    ):
        hits.append({"text": doc, "source": meta["source"],
                     "url": meta["url"], "distance": dist})
    return hits

TEST_QUERIES = [
    "What phones under $300 have the longest battery life in testing?",
    "Does the CMF Phone 2 / Pixel 9a have overheating issues?",
    "How many years of security updates does the CMF Phone 2 / Pixel 9a get?",
]

def run_tests(k: int = 4) -> None:
    for q in TEST_QUERIES:
        print("\n" + "=" * 90)
        print(f"QUERY: {q}")
        print("=" * 90)
        for i, hit in enumerate(retrieve(q, k), 1):
            preview = hit["text"].replace("\n", " ")[:240]
            print(f"\n[{i}] distance={hit['distance']:.3f}  source={hit['source'][:45]}")
            print(f"    {preview}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true", help="re-embed and reload ChromaDB")
    parser.add_argument("-k", type=int, default=4, help="top-k chunks to retrieve")
    args = parser.parse_args()

    if args.rebuild or get_collection().count() == 0:
        build_index()
    run_tests(args.k)
