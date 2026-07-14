# PR Response Doc — CineLog Watchlist Feature

## AI Usage
- **Codebase orientation (Milestone 1):** Before looking at any review comments, I read `models.py`, `services/collection_service.py`, and `tests/test_collection.py` directly and used them to identify the actual patterns (verb_to_noun naming, dedup-before-insert, fixture-based tests) rather than asking AI to summarize them — reading the code first made it obvious what each of the six review comments was pointing at (e.g. `save_to_watchlist` immediately reads as a naming-convention violation once you've seen `add_to_collection`).
- **Comments 4 & 5 (devil's-advocate stress-test):** After drafting my positions on default visibility and sort order, I asked what counterargument a careful reviewer would raise against each, per the milestone's instructions. For Comment 4, the pushback was that citing "collections have no privacy flag either" as justification is circular — precedent isn't itself a reason. I revised the writeup to instead ground the default in the README's own stated purpose ("community film tracking app") and to be explicit that the lack of a removal/visibility-toggle endpoint in this PR's scope is what makes the default effectively permanent, rather than just gesturing at consistency with collections. For Comment 5, the pushback was that alphabetical's scannability benefit only kicks in once a watchlist is long, while recency's "see what I just added" benefit applies on every single add regardless of list size — I added that concession explicitly instead of only arguing my side. In both cases the position and the CineLog-specific reasoning are mine; AI's role was limited to poking holes in a draft I'd already written.
- **Commit history self-check (Milestone 4):** Before finalizing the rewritten history, I reviewed `git log --oneline origin/main..HEAD` myself against the Conventional Commits spec rather than taking the rewrite at face value: confirmed each of the 7 commits uses a `feat:`/`fix:`/`test:`/`docs:` prefix, imperative mood, and represents one coherent change. I flagged one judgment call rather than treating AI's pass as final: several `fix:`/`test:` commits also touch `pr-response.md` in the same commit — I decided this is the write-up for that same change (not a second, unrelated change) and left it bundled, rather than splitting docs into a separate commit for every code change.

## Comment 1 — Rename

**What I did:** Renamed `save_to_watchlist()` to `add_to_watchlist()` in `services/watchlist_service.py` to match the project's `verb_to_noun` convention (`add_to_collection`, `remove_from_collection`, `get_collection`). Updated the one call site in `routes/watchlist/watchlist.py` (both the import and the function call).

**How I verified:** Ran `grep -rn "save_to_watchlist"` across the project (excluding `.venv`) and got zero matches. Confirmed `routes.watchlist.watchlist` and `services.watchlist_service.add_to_watchlist` still import without errors.

## Comment 2 — Deduplication
**What I did:** Added an `AlreadyInWatchlistError` exception and a duplicate check in `add_to_watchlist()`, mirroring `add_to_collection()`'s pattern exactly: query for an existing `WatchlistEntry` by `(user_id, film_id)` before inserting, and raise if one is found. I also updated the `/watchlist/<user_id>/add` route to catch `FilmNotFoundError` (404) and `AlreadyInWatchlistError` (409), since `add_to_watchlist()` could already raise `FilmNotFoundError` but the route wasn't catching either exception — following the full pattern used in `routes/collection.py`, not just the service-layer check.
**How I verified:** Ran a manual script against an in-memory SQLite app: added a film to a watchlist (succeeded), then attempted to add the same film again and confirmed `AlreadyInWatchlistError` was raised instead of creating a duplicate row.

## Comment 3 — Missing test
**What I did:** Created `tests/test_watchlist.py` and wrote `test_add_to_watchlist_nonexistent_film_raises`, modeled directly on `test_add_to_collection_nonexistent_film_raises` in `tests/test_collection.py`. I reused the same `app` and `sample_user` fixtures (fixture bodies copied as-is since they're generic, not collection-specific) and the same assertion shape: construct a fake UUID that doesn't exist in the DB, then assert `pytest.raises(FilmNotFoundError)` when calling `add_to_watchlist()` with it. I didn't need a `sample_film` fixture for this test since the whole point is that no matching film exists.
**How I verified:** Ran `pytest tests/test_watchlist.py -v` — passed. Then ran the full suite with `pytest tests/ -v` — all 5 tests (4 existing collection tests + the new watchlist test) pass, confirming the new test file doesn't break anything else.

## Comment 4 — Default visibility
**My position:** Keep `public=True` as the default for new `WatchlistEntry` rows.
**Reasoning:** CineLog describes itself, in its own README, as "a community film tracking app" — the product's stated purpose is social, not private journaling. `CollectionEntry` (what you've already watched) has no privacy flag at all — it's unconditionally visible. That's not just an existing pattern to copy for its own sake; it reflects the app's controlling design philosophy that logging activity is meant to be seen and compared (recommendations, overlap between friends, "have you seen this?" conversations). A watchlist that defaults to private would introduce visibility as an inconsistent, one-off exception rather than a considered stance, and it would weaken the exact discovery use case the app is built around: a friend seeing "this is queued on so-and-so's watchlist" is a natural prompt for a joint watch or a recommendation, which only works if the list is visible by default.
**Tradeoff acknowledged:** A watchlist is not the same kind of signal as a collection, though, and I don't want to wave that away. A collection entry reflects something a user actually did and (usually) formed an opinion on; a watchlist entry reflects unfinished intent — it can expose that someone hasn't seen a "canonical" film yet, or reveal a niche/guilty-pleasure genre they haven't committed to publicly. That's a more exposing kind of signal than a logged rating, and it's a legitimate reason someone might want their watchlist private even if their collection isn't. The reason I'm not flipping the default despite that: right now there's no way for a user to remove an entry (`remove_from_watchlist` is a stretch feature, out of scope for this PR) or change an entry's visibility after the fact (a `public` toggle on `add_to_watchlist()` is also a stretch feature, out of scope here). That means whatever default ships now is effectively permanent for the lifetime of an entry, which is exactly why I think it's worth stating explicitly in writing here rather than leaving it as an unexamined default — and it's why I'd treat adding user-facing visibility control as a near-term follow-up rather than a nice-to-have, even though I'm not implementing it in this PR.

## Comment 5 — Sort order
**My position:** Keep `get_watchlist()` sorted alphabetically by title (`Film.title.asc()`); I'm not switching to date-added order.
**Reasoning:** The maintainer's argument is that "most users want to see what they added recently," using the collection's newest-first order as the model. But collection and watchlist answer different questions. A collection is a history/log — its natural frame is "what did I just do," so recency is the right axis. A watchlist is a working reference list you return to before deciding what to watch next, and it can grow to hold dozens of unwatched titles over time. For that browsing task, alphabetical order gives users something recency can't: a stable position for any given title. Under date-added order, a title's position shifts every time something new gets added, so a user re-scanning "is X already on my list?" has to read the whole list again each time. Under alphabetical order, that same check is a quick scan to roughly where the title would sit. That directly supports what Comment 2 already does server-side — the dedup check stops duplicate rows, and a scannable sort order gives users a client-side way to notice "I've already got this" before they even try to add it again.
**Engagement with reviewer's point:** I don't think the maintainer's reasoning is wrong, just narrower than it looks. Recency answers "what's new" well, and that matters most in the instant right after adding something — the maintainer is right that seeing your just-added film front-and-center is satisfying, and that benefit applies on every single add regardless of list size, whereas alphabetical's scannability benefit only really shows up once a list gets long. That's a real point in favor of date-added that I don't want to dismiss. Where I land differently: I'd rather not make both list views answer the same question (recency) just for consistency's sake — the two lists exist to do different jobs, and giving them different sort axes isn't an oversight, it's letting each one serve its job. If the maintainer still prefers recency after this, I think the better fix is a `?sort=` query param on `GET /watchlist/<user_id>` (defaulting to alphabetical) rather than replacing the default outright, since that lets both use cases coexist instead of relitigating which one "wins." I haven't implemented that param — it's outside what Comment 5 asked for — but I want to flag it as the compromise path if this comes up again in review.

## Comment 6 — Rebase
**What conflicted:** Ran `git fetch origin && git rebase origin/main`. The only literal merge-conflict marker was a trivial add/add conflict in `.gitignore` (both branches added a `.pytest_cache/` line independently — resolved by keeping both branches' entries). The real problem was silent, not a conflict marker: `main`'s refactor commit (`07ca580`) had deleted the `WatchlistEntry` class from `models.py` entirely, because at that point in `main`'s history the watchlist feature didn't exist yet. None of my feature-branch commits ever re-add `WatchlistEntry` to `models.py` — they all assumed it was already there (it shipped in the original starter commit). So the rebase replayed cleanly with no conflict markers, but the result was broken: `WatchlistEntry` no longer existed in `models.py`, and `services/watchlist_service.py` still imported it, plus `Film.id` and `CollectionEntry.film_id` were now UUID strings (`db.String(36)`) instead of integers.
**How I resolved it:** After the rebase finished, I confirmed the app was actually broken (`from app import create_app; create_app()` raised `ImportError: cannot import name 'WatchlistEntry' from 'models'`). I re-added the `WatchlistEntry` class to `models.py`, using `db.String(36)` for both `id` and `film_id` to match the new UUID `Film.id`, matching the same UUID pattern already used for `CollectionEntry`. I also updated the stale integer-ID references left over in `services/watchlist_service.py`'s docstring (`film_id (int)` → `film_id (str): UUID of the film.`) and in the route docstring in `routes/watchlist/watchlist.py` (`Body: { "film_id": <int> }` → `{ "film_id": "<uuid>" }`), since those were describing the pre-refactor contract.
**How I verified no conflict remains:** Ran `from app import create_app; create_app()` again — it now succeeds. Ran `pytest tests/ -v` — all 5 tests pass. Ran `grep -rn "Integer.*film_id\|film_id.*Integer\|<int>"` across the project (excluding `.venv`) and got zero matches, confirming no lingering integer-ID references. Confirmed with `git log --merges origin/main..HEAD` (empty output) that the branch has no merge commits, and `git log --oneline origin/main..HEAD` shows a clean linear sequence of commits rebased on top of the current `main`.

## Final Commit History

`git log --oneline origin/main..HEAD`:

```
a27d7eb docs: add PR description and finalize AI usage notes
2caf58f fix: restore WatchlistEntry model with UUID film_id after main refactor
457c313 docs: document default visibility and sort order design decisions
09b48d5 test: add test for nonexistent film_id in add_to_watchlist
92aebe6 fix: add deduplication check to prevent duplicate watchlist entries
039d874 fix: rename save_to_watchlist to add_to_watchlist per naming convention
7095e67 fix: use db.session.get for film retrieval in collection and watchlist services
58a4393 feat: add watchlist model and add_to_watchlist endpoint
```

8 commits, all conventional-format, no merge commits (`git log --merges origin/main..HEAD` is empty), rebased cleanly on the current `main`.

## PR Description

### What this PR does

Adds a watchlist feature to CineLog: users can save films they want to watch later (as distinct from `CollectionEntry`, which tracks films they've already watched) and view their watchlist. New endpoints:

- `POST /watchlist/<user_id>/add` — add a film to a user's watchlist. Body: `{ "film_id": "<uuid>" }`. Returns 404 if the film doesn't exist, 409 if it's already on the watchlist, 201 on success.
- `GET /watchlist/<user_id>` — return a user's watchlist, sorted alphabetically by film title.

### Design decisions

- **Default visibility (`public=True`):** New watchlist entries default to public. CineLog is a community app by design (per its own README), and `CollectionEntry` has no privacy flag at all — public-by-default keeps the watchlist consistent with the app's existing discovery-oriented philosophy rather than introducing an inconsistent privacy exception. The tradeoff: a watchlist reveals unfinished intent/taste, which is more exposing than a logged rating, and there's currently no endpoint to change an entry's visibility or remove it, so this default is effectively permanent for now — a visibility toggle and a `remove_from_watchlist()` endpoint are natural near-term follow-ups. Full reasoning in Comment 4 above.
- **Sort order (alphabetical by title, not date-added):** Watchlists and collections answer different questions — a collection is a "what did I just do" history where recency is the right frame, while a watchlist is a reference list you return to before deciding what to watch, where a stable, scannable order matters more as the list grows. I kept alphabetical rather than switching to date-added; full reasoning and engagement with the reviewer's counterpoint in Comment 5 above.

### How to manually test

```bash
pip install -r requirements.txt
python app.py
```

With the app running (`http://localhost:5000`):

1. Create a user and a film via the existing `/films/` and DB seed data (or use `db.session` directly in a shell), and note their UUIDs.
2. Add a film to the watchlist:
   ```
   POST /watchlist/<user_id>/add
   Body: { "film_id": "<film_uuid>" }
   ```
   Expect `201` with the new entry.
3. Try adding the same film again — expect `409` with an `AlreadyInWatchlistError` message, and confirm no duplicate row was created.
4. Try adding a film_id that doesn't exist — expect `404`.
5. View the watchlist:
   ```
   GET /watchlist/<user_id>
   ```
   Expect the added film(s) back, sorted alphabetically by title.

Automated coverage: `pytest tests/ -v` (includes `tests/test_watchlist.py::test_add_to_watchlist_nonexistent_film_raises`).
