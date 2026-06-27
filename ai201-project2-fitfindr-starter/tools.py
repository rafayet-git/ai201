"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()

    # Tokenize the query description into lowercase keywords, stripping surrounding punctuation so "tee," still matches "tee".
    keywords = [w.strip(".,!?;:'\"") for w in description.lower().split()]
    keywords = [w for w in keywords if w]

    results = []
    for item in listings:
        # --- price filter ---
        if max_price is not None and item["price"] > max_price:
            continue

        # --- size filter (case-insensitive substring match both ways) ---
        if size is not None:
            want = size.lower().strip()
            have = str(item.get("size", "")).lower()
            if want not in have and have not in want:
                continue

        # --- relevance score: keyword overlap with title, description, tags ---
        haystack = " ".join([
            item["title"],
            item["description"],
            " ".join(item.get("style_tags", [])),
            item.get("category", ""),
            " ".join(item.get("colors", [])),
            str(item.get("brand") or ""),
        ]).lower()

        score = sum(1 for kw in keywords if kw in haystack)
        if score == 0:
            continue

        results.append((score, item))

    # Sort by score, highest first; stable sort keeps dataset order for ties.
    results.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in results]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    item_desc = (
        f"{new_item.get('title', 'this item')} "
        f"(category: {new_item.get('category', 'unknown')}, "
        f"colors: {', '.join(new_item.get('colors', [])) or 'n/a'}, "
        f"style: {', '.join(new_item.get('style_tags', [])) or 'n/a'})"
    )

    items = wardrobe.get("items", []) if wardrobe else []

    if not items:
        # Empty/minimal wardrobe → general styling advice instead of failing.
        prompt = (
            f"A user is considering buying this secondhand item: {item_desc}.\n"
            "They have not entered any wardrobe items yet. In 2-3 sentences, give "
            "general styling advice: what categories and colors pair well with it, "
            "and what overall vibe or occasion it suits. Be specific and practical."
        )
    else:
        wardrobe_lines = "\n".join(
            f"- {it['name']} ({it.get('category', '')}; "
            f"{', '.join(it.get('colors', []))}; "
            f"{', '.join(it.get('style_tags', []))})"
            for it in items
        )
        prompt = (
            f"A user is considering buying this secondhand item: {item_desc}.\n\n"
            f"Here is their current wardrobe:\n{wardrobe_lines}\n\n"
            "Suggest 1-2 complete outfits that pair the new item with SPECIFIC pieces "
            "named from their wardrobe above. End with one short styling tip (how to "
            "wear it). Keep it under 5 sentences and reference real wardrobe items by name."
        )

    try:
        client = _get_groq_client()
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        text = resp.choices[0].message.content.strip()
        if text:
            return text
    except Exception:
        pass

    # Fallback so the agent never receives an empty string.
    return (
        f"Style {new_item.get('title', 'this piece')} as the centerpiece: pair it with "
        "neutral basics and let its colors and vibe lead the look."
    )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    # Guard against missing/incomplete input — do not fabricate a caption.
    if not outfit or not outfit.strip():
        return (
            "Can't make a fit card without an outfit — run suggest_outfit first."
        )
    if not new_item:
        return "Can't make a fit card without item details."

    title = new_item.get("title", "this piece")
    price = new_item.get("price")
    platform = new_item.get("platform", "secondhand")
    price_str = f"${price:.0f}" if isinstance(price, (int, float)) else "a steal"

    prompt = (
        "Write a short, casual Instagram/TikTok caption for a thrift find. "
        "It should sound like a real person's OOTD post, NOT a product description.\n\n"
        f"Item: {title}\n"
        f"Price: {price_str}\n"
        f"Platform: {platform}\n"
        f"Outfit/styling: {outfit}\n\n"
        "Rules: 2-4 sentences. Mention the item name, the price, and the platform "
        "naturally — once each. Capture the outfit's specific vibe. Keep it casual "
        "and authentic, emojis welcome but optional."
    )

    try:
        client = _get_groq_client()
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9,  # higher temp → varied captions for repeated calls
        )
        text = resp.choices[0].message.content.strip()
        if text:
            return text
    except Exception:
        pass

    # Templated fallback so the user still gets something shareable.
    return (
        f"scored this {title} off {platform} for {price_str} 🤍 already obsessed "
        "with how it fits the rest of my closet — full look soon!"
    )
