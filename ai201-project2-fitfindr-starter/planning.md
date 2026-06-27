# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the listings dataset for secondhand pieces matching the user's request. It filters by price and size, then scores the remaining listings by keyword overlap with the description and returns them ranked by the best match.

**Input parameters:**
- `description` (str): keywords describing what the user wants (e.g. `"vintage graphic tee"`). Used for keyword/style-tag scoring.
- `size` (str | None): a size string to filter by (e.g. `"M"`). Matching is case-insensitive and substring-based so `"M"` also matches `"S/M"`. Optional.
- `max_price` (float | None): inclusive price ceiling. Listings priced above it are dropped. Optional.

**What it returns:**
A `list[dict]` of matching listings sorted by relevance score (highest first). Each dict has the full details of the listing. Listings that score 0 on keyword overlap are removed. Returns `[]` when nothing matches.

**What happens if it fails or returns nothing:**
Returns an empty list. The agent detects the empty list, returns an error with what it searched for, and returns early without calling the downstream tools (optionally retrying without size or price filters).

---

### Tool 2: suggest_outfit

**What it does:**
Given the user's wardrobe and any items found from `search_listings`, asks the LLM to build a complete outfit that pair the new item with their existing clothes and their preferences, including a short styling note (how to wear it).

**Input parameters:**
- `new_item` (dict): a listing dict from `search_listings` (the item being considered).
- `wardrobe` (dict): a wardrobe dict with an `items` key — a list of wardrobe item dicts with all the details of each clothing the user owns. May be empty.

**What it returns:**
A non-empty `str` describing one or two outfit combinations that name specific wardrobe pieces plus a styling tip. When the wardrobe is empty it instead returns general styling advice for the item (what categories/colors pair well, what vibe it suits).

**What happens if it fails or returns nothing:**
If `wardrobe["items"]` is empty or the clothes are too unrelated, it does not fully fail, but instead it returns general styling advice instead of named combinations. If the LLM call errors, the tool returns a short fallback string (generic styling advice for the item) so the agent can still proceed to the fit card; the agent never receives an empty string.

---

### Tool 3: create_fit_card

**What it does:**
Turns the chosen outfit and item into a short, casual, shareable caption, the kind of thing someone would post under an OOTD/thrift-haul photo. Uses a higher LLM temperature so the output differs for different inputs.

**Input parameters:**
- `outfit` (str): the outfit suggestion string returned by `suggest_outfit`.
- `new_item` (dict): the listing dict for the thrifted item from `search_listing`, used to mention name, price, and platform naturally.

**What it returns:**
A 2–4 sentence `str` usable as an Instagram/TikTok caption. It mentions the item name, price, and platform once each, captures the outfit vibe in specific terms, and reads casually rather than like a product description.

**What happens if it fails or returns nothing:**
If `outfit` or `new_item` is empty, the tool returns a descriptive error-message string (it does not raise and does not fabricate a caption). If the LLM call errors, it returns a simple templated caption built from the item fields as a fallback so the user still gets something shareable.

## Planning Loop

**How does your agent decide which tool to call next?**

The loop is a linear pipeline with conditional early-exit branches. It is driven by the provided data in the session, not a fixed unconditional sequence. Each step only runs if the previous step produced usable state.

1. **Parse.** Extract and store `description`, `size`, `max_price` from the raw query (LLM-based parse with a regex fallback for price/size).
2. **Search.** Call `search_listings(parsed)` and store the list.
   - **Branch A — empty results:** if `search_results == []`, retry once with `size=None` and `price=None` (loosened). If still empty, set `session["error"]` to a message naming what was searched and `return session` immediately. `suggest_outfit` and `create_fit_card` are not called.
   - **Branch B — has results:** set the selected item to`search_results[0]` (top-ranked) and continue.
3. **Suggest.** Call `suggest_outfit(selected_item, wardrobe)` and store the suggestion. This always returns a non-empty string (empty wardrobe → general advice), so there is no early-exit here.
4. **Fit card.** Only if `outfit_suggestion` is non-empty, call `create_fit_card(outfit_suggestion, selected_item)`; store in session.
5. **Done.** Return the session. The loop knows it is finished when `fit_card` is set, or earlier when `error` is set.

The behavior changes based on what is returned: an empty search short-circuits the whole pipeline, and an empty wardrobe changes what `suggest_outfit` produces without stopping the run.

---

## State Management

**How does information from one tool get passed to the next?**

All state for one interaction lives in a single `session` dict created by `_new_session(query, wardrobe)` in `agent.py`. It is the single source of truth. Tools never read each other's output directly; the planning loop reads from the session and writes results back into it. 

Tracked fields:

- `query` (str) — original user input.
- `parsed` (dict) — `{description, size, max_price}` extracted in step 1.
- `search_results` (list[dict]) - output of `search_listings`.
- `selected_item` (dict | None) - `search_results[0]`, the input to both `suggest_outfit` and `create_fit_card`.
- `wardrobe` (dict) - passed in by the caller, used by `suggest_outfit`.
- `outfit_suggestion` (str | None) - output of `suggest_outfit`, input to `create_fit_card`.
- `fit_card` (str | None) - output of `create_fit_card`, the final shareable caption.
- `error` (str | None) - set only when the run ends early; `None` on success.

Flow: `search_listings` → `session["selected_item"]` → `suggest_outfit` → `session["outfit_suggestion"]` → `create_fit_card` → `session["fit_card"]`. Because the found item is stored in the session, it flows into `suggest_outfit` and `create_fit_card` automatically.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Retry once with the size and price filter removed. If still empty, set the error to a specific message — e.g. *"No listings matched 'designer ballgown' under $5. Try raising your budget or loosening the description."* — and stop. Downstream tools are not called. |
| suggest_outfit | Wardrobe is empty | Do not error. Detect `wardrobe["items"] == []` and return general styling advice for the item (pairings, colors, vibe) instead of named combinations, so the pipeline continues. If the LLM call itself fails, return a short generic fallback string. |
| create_fit_card | Outfit is missing or incomplete | Guard against an empty `outfit` and return a descriptive message instead of a caption: *"Can't make a fit card without an outfit — run suggest_outfit first."* If the LLM call fails, fall back to a templated caption built from the item's name, price, and platform. |

---

## Architecture

<!-- Draw a diagram of your agent showing how the components connect:
     User input → Planning Loop → Tools (search_listings, suggest_outfit, create_fit_card)
                                                                          ↕
                                                                   State / Session
     Show what triggers each tool, how state flows between them, and where error paths branch off.
     ASCII art, a Mermaid diagram (https://mermaid.js.org/syntax/flowchart.html), or an embedded
     sketch are all fine. You'll share this diagram with an AI tool when asking it to implement
     the planning loop and each individual tool. -->

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

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**
I'll use Claude. For each tool I'll give it that tool's block from the Tools section above (inputs, return type, failure mode) plus the matching docstring/TODO already in `tools.py`, and the field list from `utils/data_loader.py`.
- `search_listings`: ask Claude to implement it using `load_listings()`, filtering by `max_price` and `size`, scoring by style keyword/tag overlap with `description`, dropping zero-score items, and sorting descending. I'll verify this by checking the code filters by all three params and returns `[]` (not an exception) on no match, then test 3 queries — a normal hit ("vintage tee"), a price-excluded one, and a no-match ("designer ballgown under $5").
- `suggest_outfit`: give it the Tool 2 block and ask for an LLM call (Groq `llama-3.3-70b-versatile`) that branches on empty `wardrobe["items"]`. I'll verify this by running once with `get_example_wardrobe()` (must name real wardrobe pieces) and once with `get_empty_wardrobe()` (must still return non-empty general advice).
- `create_fit_card`: give it the Tool 3 block and ask for a higher-temperature caption mentioning name/price/platform once each, with the empty-outfit guard. I'll verify this by confirming it guards empty input, and that two different items produce two different captions.

**Milestone 4 — Planning loop and state management:**
I'll give Claude the Planning Loop, State Management, and Architecture sections plus the `run_agent`/`_new_session` scaffolding in `agent.py`. I expect it to produce the loop that parses the query, calls the three tools in order, writes each result into the session, and takes the early-exit error branch on empty search results (with the one loosened retry). *I'll verify this by running `python agent.py`, where the happy path must populate `selected_item`, `outfit_suggestion`, and `fit_card` with `error is None`; the no-results path must set a specific `error` and leave `outfit_suggestion`/`fit_card` as `None`.

---

## A Complete Interaction (Step by Step)

FitFindr is an agent that helps users with choosing the right clothes that fits their needs, and for the right price. Using the user's current and suggested clothes, FitFindr will then provide a suggested outfit that would best fit the user's style and chouces.

The `search_listings` tool is called whenever the user is requesting for a new outfit or a piece of clothing, and provides the best matching clothing. If this fails because there is no relevant clothes, it does not continue working on the prompt, and instead responds back with what it searched for, never calling `suggest_outfit` or`create_fit_card`.

The `suggest_outfit` tool is called when the user is requesting for a new outfit and `search_listings` is successful, and returns a full outfit based on the user's wardrobe.

The `create_fit_card` tool is called when the user is requesting a full outfit and returns a styled, sharable description containing the full outfit, such as one from the `suggest_outfit` tool.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1 - Search:** The agent parses the query into `search_listings(description="vintage graphic tee", size="M", max_price=30.0)` and queries the dataset. It returns the matching listings sorted by relevance and the agent picks the top result (e.g. Y2K Baby Tee — Butterfly Print).

**Step 2 - Suggest outfit:** Using the item from Step 1, the agent calls `suggest_outfit(new_item=<butterfly tee>, wardrobe=<example wardrobe>)`. It returns a styling suggestion that pairs the tee with pieces already in the wardrobe (e.g. the baggy jeans and chunky sneakers) plus a styling note.

**Step 3 - Fit card:** With the new item and the chosen outfit in state, the agent calls `create_fit_card(outfit=<suggestion>, new_item=<butterfly tee>)`, which presents the outfit to the user.

**Final output to user:** The user sees the chosen listing (title, price, platform, condition), the styling suggestion against their own wardrobe, and the shareable fit card caption.
