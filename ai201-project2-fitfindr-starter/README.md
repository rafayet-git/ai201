# FitFindr 🛍️

FitFindr is a multi-tool AI agent for thrifting. Give it a thrifting request ("vintage graphic tee under $30, size M") and it searches a listing dataset, figures out how the best find fits with clothes you already own, and writes a short, shareable caption for the resulting outfit.

## Setup

```bash
pip install -r requirements.txt
```

Set your Groq API key in a `.env` file (free key at [console.groq.com](https://console.groq.com)):

```
GROQ_API_KEY=your_key_here
```

Run it:

```bash
python app.py        # Gradio UI at http://localhost:7860
python agent.py      # CLI: runs a happy-path and a no-results example
python -m pytest tests/   # run the tool tests
```


## The Mock Listings Dataset

`data/listings.json` contains 40 mock secondhand listings across categories (tops, bottoms, outerwear, shoes, accessories) and styles (vintage, y2k, grunge, cottagecore, streetwear, and more).

Each listing has: `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, and `platform`.

Load it with:
```python
from utils.data_loader import load_listings
listings = load_listings()
```

## The Wardrobe Schema

`data/wardrobe_schema.json` defines the format your agent uses to represent a user's existing wardrobe. It includes:

- `schema`: field definitions for a wardrobe item
- `example_wardrobe`: a sample wardrobe with 10 items you can use for testing
- `empty_wardrobe`: a starting template for a new user

Load an example wardrobe with:
```python
from utils.data_loader import get_example_wardrobe
wardrobe = get_example_wardrobe()
```

## Tool Inventory

All three tools live in [`tools.py`](tools.py) and can be called and tested in isolation.

### 1. `search_listings(description, size, max_price) -> list[dict]`

**Purpose:** Find secondhand pieces in the dataset matching the request.

| Parameter | Type | Meaning |
|-----------|------|---------|
| `description` | `str` | Keywords describing the item (e.g. `"vintage graphic tee"`). Scored against each listing. |
| `size` | `str \| None` | Size filter. Case-insensitive, two-way substring match, so `"M"` matches `"S/M"`. `None` skips the filter. |
| `max_price` | `float \| None` | Inclusive price ceiling. Listings above it are dropped. `None` skips the filter. |

**Returns:** A `list[dict]` of matching listings sorted by relevance (best first). Each dict has `id, title, description, category, style_tags, size, condition, price, colors, brand, platform`. Listings that score 0 keyword overlap are removed. Returns `[]` when nothing matches.

**Implementation note:** Relevance score = number of query keywords found across the listing's title, description, style tags, category, colors, and brand. No LLM call.

### 2. `suggest_outfit(new_item, wardrobe) -> str`

**Purpose:** Suggest 1–2 complete outfits pairing the found item with the user's wardrobe.

| Parameter | Type | Meaning |
|-----------|------|---------|
| `new_item` | `dict` | A listing dict from `search_listings` (the item being considered). |
| `wardrobe` | `dict` | `{"items": [...]}` — the user's closet. May be empty. |

**Returns:** A non-empty `str`. With a populated wardrobe it names specific pieces and adds a styling tip. With an empty wardrobe it returns general styling advice instead. Uses Groq `llama-3.3-70b-versatile` at temperature 0.7.

### 3. `create_fit_card(outfit, new_item) -> str`

**Purpose:** Turn the outfit into a casual, shareable Instagram/TikTok-style caption.

| Parameter | Type | Meaning |
|-----------|------|---------|
| `outfit` | `str` | The outfit suggestion from `suggest_outfit`. |
| `new_item` | `dict` | The listing dict, so the caption can mention name/price/platform. |

**Returns:** A 2–4 sentence `str` caption mentioning the item name, price, and platform once each. Runs at temperature 0.9 so repeated calls on the same input produce different captions.

---

## Planning Loop

The loop lives in `run_agent()` in [`agent.py`](agent.py). It is not a fixed sequence, as each step runs only if the previous one produced usable state, and the agent short-circuits when a search comes back empty.

```
User query + wardrobe
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ PLANNING LOOP  (agent.run_agent)                                          │
│                                                                           │
│  1. parse query ──► session["parsed"] = {description, size, max_price}    │
│        │                                                                  │
│  2. search_listings(description, size, max_price)                         │
│        │                                                                  │
│        ├─ results == []                                                   │
│        │     └─► retry with size=None                                     │
│        │            └─ still [] ─► session["error"] = "No listings..."    │
│        │                            └──► return session   ◄── ERROR EXIT  │
│        │                                                                  │
│        └─ results = [item, ...]                                           │
│              └─► session["selected_item"] = results[0]                    │
│                     │                                                     │
│  3. suggest_outfit(selected_item, wardrobe)                               │
│        │   (wardrobe empty ─► general advice, no exit)                    │
│        └─► session["outfit_suggestion"] = "..."                           │
│                     │                                                     │
│  4. create_fit_card(outfit_suggestion, selected_item)                     │
│        └─► session["fit_card"] = "..."                                    │
│                     │                                                     │
│  5. return session                                                        │
└───────────────────────────────────┬───────────────────────────────────-─┘
                                     │
                          ┌──────────┴───────────┐
                          │   SESSION (state)     │
                          │  query, parsed,       │
                          │  search_results,      │
                          │  selected_item,       │
                          │  wardrobe,            │
                          │  outfit_suggestion,   │
                          │  fit_card, error      │
                          └───────────────────────┘
                                     │
                                     ▼
        User sees: listing (title/price/platform/condition),
                   outfit suggestion, and fit card OR the error message
```

---

## State Management

All state for one interaction lives in a single `session` dict built by `_new_session()`. It is the single source of truth: tools never read each other's output directly — the loop reads from the session and writes results back into it.

| Field | Set by | Consumed by |
|-------|--------|-------------|
| `query` | caller | `parse_query` |
| `parsed` | parse step | `search_listings` |
| `search_results` | `search_listings` | item selection |
| `selected_item` | item selection (`results[0]`) | `suggest_outfit`, `create_fit_card` |
| `wardrobe` | caller | `suggest_outfit` |
| `outfit_suggestion` | `suggest_outfit` | `create_fit_card` |
| `fit_card` | `create_fit_card` | final output |
| `error` | error branches | final output |

Because the found item is stored in `session["selected_item"]`, it flows into the next tools automatically — the user never re-enters it. This is verifiable: at the end of a run, `session["selected_item"] is session["search_results"][0]` is `True`, i.e. the exact same dict object that came out of search is the one that went into `suggest_outfit`.

---

## Error Handling (per tool)

| Tool | Failure mode | What the agent does |
|------|--------------|---------------------|
| `search_listings` | No listing matches | Retry once with size + price filters removed; if still empty, set a specific `error` and stop — downstream tools are not called. |
| `suggest_outfit` | Wardrobe is empty / LLM call fails | Empty wardrobe → general styling advice instead of named combos (no crash, pipeline continues). LLM error → short generic fallback string, so the agent never gets `""`. |
| `create_fit_card` | `outfit` empty or item missing / LLM fails | Empty outfit → returns a descriptive message ("run suggest_outfit first") instead of fabricating a caption. LLM error → a templated caption built from the item's name/price/platform. |

**Concrete example from testing** (the no-results branch, run via `python agent.py`):

```
Query:  "designer ballgown size XXS under $5"
search_listings(...) → []      # nothing matches
retry with size=None, price=None → []   # still nothing
Result: session["error"] = "No listings matched 'designer ballgown', size XXS,
        under $5. Try loosening the description, raising your budget, or removing the size."
        session["outfit_suggestion"] = None
        session["fit_card"]          = None
```

The agent stops cleanly: no exception, no empty call to `suggest_outfit`, and the UI shows the error in the listing panel with the other two panels blank. The `tests/test_tools.py` suite covers each failure mode (empty search → `[]`, empty wardrobe → non-empty advice, empty outfit → guard message).

---

## AI Usage

I used Claude during implementation. Two specific instances:

**1. Implementing `search_listings`:** I gave Claude the Tool 1 block from `planning.md` (the three parameters with types, the "returns ranked list / `[]` on no match" contract, and the "scores by keyword overlap" note) plus the function stub and its TODO list in `tools.py`. It produced a filter-then-score implementation using `load_listings()`. **What I changed:** I added punctuation stripping in the keyword tokenizer after testing showed `"tee,"` (a trailing comma left by the query parser) failed to match `"tee"`.

**2. Implementing the planning loop in `run_agent`.**
I gave Claude the Planning Loop section, the State Management section, and the ASCII agent diagram from `planning.md`, plus the `_new_session`/`run_agent` scaffolding. It produced the parse → search → branch → suggest → fit-card flow writing into the session dict. **What I changed:** my spec calls for the loosened retry to drop both size and price (the generated version only dropped size), so I corrected the retry call and the error message to reflect both. I also added the guard so `create_fit_card` only runs when a non-empty outfit string exists, matching the diagram's conditional call.

---

## Spec Reflection

Writing `planning.md` before coding paid off most in the planning loop: because the branch logic (empty-results → loosened retry → early return) was already written as explicit conditionals, the implementation was almost a carbon copy, and it was easy to catch where the generated code diverged from the spec. The one place my implementation diverged from the spec was query parsing, as the spec assumed clean parameters, but free-text queries leave punctuation and ambiguous size tokens ("M" vs. the letter m), which is why the parser strips price/size phrases out of the description and only matches whole-word size tokens.

---

## Project Layout

```
├── agent.py             # planning loop + query parser + session state
├── tools.py             # the 3 tools
├── app.py               # Gradio UI (handle_query maps session → 3 panels)
├── tests/test_tools.py  # one test per failure mode + structural checks
├── data/
│   ├── listings.json        # 40 mock listings
│   └── wardrobe_schema.json # wardrobe format + example/empty wardrobes
├── utils/data_loader.py # load_listings(), get_example_wardrobe(), get_empty_wardrobe()
└── planning.md          # design spec (tools, loop, state, errors, diagram)
```
