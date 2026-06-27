"""
Tests for the three FitFindr tools, run with `pytest tests/`.

The search_listings tests are fully offline (no LLM). The suggest_outfit and
create_fit_card tests focus on the failure modes and structural guarantees so
they pass without depending on exact LLM wording — and the LLM tests are
skipped automatically when no GROQ_API_KEY is configured.
"""

import os

import pytest

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe, load_listings

_HAS_KEY = bool(os.environ.get("GROQ_API_KEY")) or os.path.exists(".env")


# ── search_listings ────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    # Failure mode: nothing matches → empty list, no exception.
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_sorted_by_relevance():
    # More matching keywords should rank a listing higher (score is non-increasing).
    results = search_listings("vintage denim jacket", size=None, max_price=100)
    assert isinstance(results, list)
    # Results are ranked, so the first item should contain at least one keyword.
    if results:
        hay = (results[0]["title"] + results[0]["description"]).lower()
        assert any(kw in hay for kw in ["vintage", "denim", "jacket"])


def test_search_size_substring_match():
    # "M" should match listings whose size is "S/M".
    results = search_listings("baby tee butterfly", size="M", max_price=50)
    assert any("m" in item["size"].lower() for item in results)


# ── suggest_outfit ─────────────────────────────────────────────────────────

@pytest.mark.skipif(not _HAS_KEY, reason="needs GROQ_API_KEY")
def test_suggest_with_wardrobe():
    item = load_listings()[5]  # a graphic tee
    out = suggest_outfit(item, get_example_wardrobe())
    assert isinstance(out, str)
    assert out.strip() != ""


@pytest.mark.skipif(not _HAS_KEY, reason="needs GROQ_API_KEY")
def test_suggest_empty_wardrobe():
    # Failure mode: empty wardrobe → still returns non-empty general advice.
    item = load_listings()[5]
    out = suggest_outfit(item, get_empty_wardrobe())
    assert isinstance(out, str)
    assert out.strip() != ""


# ── create_fit_card ────────────────────────────────────────────────────────

def test_fit_card_empty_outfit():
    # Failure mode: missing outfit → descriptive error string, no exception.
    item = load_listings()[5]
    card = create_fit_card("", item)
    assert isinstance(card, str)
    assert card.strip() != ""
    assert "suggest_outfit" in card or "outfit" in card.lower()


def test_fit_card_whitespace_outfit():
    item = load_listings()[5]
    card = create_fit_card("   ", item)
    assert isinstance(card, str)
    assert card.strip() != ""


@pytest.mark.skipif(not _HAS_KEY, reason="needs GROQ_API_KEY")
def test_fit_card_varies():
    # Different items should produce different captions.
    listings = load_listings()
    outfit = "Pair it with baggy jeans and chunky sneakers."
    c1 = create_fit_card(outfit, listings[5])
    c2 = create_fit_card(outfit, listings[0])
    assert c1.strip() and c2.strip()
    assert c1 != c2
