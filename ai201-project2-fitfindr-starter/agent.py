"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re
from tools import search_listings, suggest_outfit, create_fit_card


# ── query parsing ─────────────────────────────────────────────────────────────

# Common alphabetic size tokens we recognize in a free-text query.
_SIZE_WORDS = {
    "xxs": "XXS", "xs": "XS", "s": "S", "small": "S",
    "m": "M", "medium": "M", "l": "L", "large": "L",
    "xl": "XL", "xxl": "XXL",
}

def parse_query(query: str) -> dict:
    """
    Extract {description, size, max_price} from a free-text query using regex.

    - max_price: pulled from "under $30", "$30", "under 30", "less than 40".
    - size: pulled from "size M" or a standalone size word (S/M/L/XL/...).
    - description: the query with the size/price phrases stripped out, so the
      keywords passed to search_listings stay relevant.

    Returns a dict; size and max_price are None when not found.
    """
    text = query.strip()
    lowered = text.lower()

    # --- price ---
    max_price = None
    # Only treat a number as a price if it's clearly money-related.
    money_match = re.search(
        r"(?:under|below|less than|max|<|\$)\s*\$?\s*(\d+(?:\.\d{1,2})?)", lowered
    )
    if money_match:
        max_price = float(money_match.group(1))

    # --- size ---
    size = None
    size_phrase = re.search(r"size\s+([a-z0-9/]+)", lowered)
    if size_phrase:
        token = size_phrase.group(1)
        size = _SIZE_WORDS.get(token, token.upper())
    else:
        # standalone size word, e.g. "...tee M" — match whole words only
        for word, norm in _SIZE_WORDS.items():
            if len(word) > 1 and re.search(rf"\b{word}\b", lowered):
                size = norm
                break

    # --- description: strip price + size phrases so keywords stay clean ---
    description = text
    description = re.sub(
        r"(?:under|below|less than|max|<)\s*\$?\s*\d+(?:\.\d{1,2})?\s*(?:dollars|bucks)?",
        "",
        description,
        flags=re.IGNORECASE,
    )
    description = re.sub(r"\$\s*\d+(?:\.\d{1,2})?", "", description)
    description = re.sub(r"size\s+[a-z0-9/]+", "", description, flags=re.IGNORECASE)
    description = re.sub(r"\s+", " ", description).strip()
    if not description:
        description = text  # fall back to raw query if we stripped everything

    return {"description": description, "size": size, "max_price": max_price}


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    TODO — implement this function using the planning loop you designed in planning.md:

        Step 1: Initialize the session with _new_session().

        Step 2: Parse the user's query to extract a description, size, and
                max_price. You can use regex, string splitting, or ask the LLM
                to parse it — document your choice in planning.md.
                Store the result in session["parsed"].

        Step 3: Call search_listings() with the parsed parameters.
                Store results in session["search_results"].
                If no results: set session["error"] to a helpful message and
                return the session early. Do NOT proceed to suggest_outfit
                with empty input.

        Step 4: Select the item to use (e.g., the top result).
                Store it in session["selected_item"].

        Step 5: Call suggest_outfit() with the selected item and wardrobe.
                Store the result in session["outfit_suggestion"].

        Step 6: Call create_fit_card() with the outfit suggestion and selected item.
                Store the result in session["fit_card"].

        Step 7: Return the session.

    Before writing code, complete the Planning Loop and State Management sections
    of planning.md — your implementation should match what you described there.
    """
    # Step 1 — initialize session state.
    session = _new_session(query, wardrobe)

    # Step 2 — parse the query into search parameters.
    session["parsed"] = parse_query(query)
    parsed = session["parsed"]

    # Step 3 — search. Branch on what comes back.
    session["search_results"] = search_listings(
        description=parsed["description"],
        size=parsed["size"],
        max_price=parsed["max_price"],
    )

    # Branch A: no matches. Try once with filters loosened before giving up.
    if not session["search_results"]:
        if parsed["size"] is not None or parsed["max_price"] is not None:
            session["search_results"] = search_listings(
                description=parsed["description"],
                size=None,
                max_price=None,
            )
            session["loosened"] = bool(session["search_results"])

        # Still nothing → set a specific error and STOP. Downstream tools
        # are not called with empty input.
        if not session["search_results"]:
            bits = [f"'{parsed['description']}'"]
            if parsed["size"]:
                bits.append(f"size {parsed['size']}")
            if parsed["max_price"] is not None:
                bits.append(f"under ${parsed['max_price']:.0f}")
            session["error"] = (
                "No listings matched " + ", ".join(bits) + ". "
                "Try loosening the description, raising your budget, or removing the size."
            )
            return session

    # Branch B: we have results — select the top-ranked item.
    session["selected_item"] = session["search_results"][0]

    # Step 4 — suggest an outfit. Always returns a non-empty string.
    session["outfit_suggestion"] = suggest_outfit(
        session["selected_item"], session["wardrobe"]
    )

    # Step 5 — create the fit card, only if we actually have an outfit.
    if session["outfit_suggestion"] and session["outfit_suggestion"].strip():
        session["fit_card"] = create_fit_card(
            session["outfit_suggestion"], session["selected_item"]
        )

    # Step 6 — done.
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
