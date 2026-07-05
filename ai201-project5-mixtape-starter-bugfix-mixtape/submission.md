# Mixtape Bug Hunt 

![](https://raw.githubusercontent.com/rafayet-git/ai201-project5-mixtape-starter/refs/heads/bugfix/mixtape/image.png)
## AI Usage

I used Claude Code as a navigation and explanation partner throughout, but treated every AI claim as a hypothesis to verify — not an answer. The workflow was consistently: *find the suspicious code myself → ask the AI to explain or compare it → confirm by reading it and running the code.*

**Codebase orientation.** I had the AI summarize each `services/` file's responsibilities and trace the `route → service → model` call chains (e.g. how adding a song to a playlist reaches `create_notification`). This is what let me write the codebase map quickly. I spot-checked the summaries against the actual files — they were accurate for this small, cleanly-layered codebase.

**Debugging.** Two specific, useful asks: (1) comparing the sibling functions `add_to_playlist` and `rate_song` side by side to articulate the *structural* difference — that `rate_song` fetches everything needed to notify but never makes the call (Issue #4); (2) confirming Python's `datetime.weekday()` convention (Sunday == 6) *after* I'd already narrowed Issue #1 to the weekday clause by noticing the bug only triggered on Sundays. In both cases the AI explained code I had already located; it did not "find" the bugs for me.

**Where I had to verify / where AI was incomplete.** The most important correction was on the search bug (Issue #3). The surface-level explanation — "the `outerjoin(song_tags)` multiplies a 3-tag song into 3 rows, so it appears 3× in results" — is the *intent* of the bug and sounds authoritative, but when I actually ran `search_songs` against the seeded DB and the test suite, **no duplicates appeared**. Verifying empirically revealed the missing nuance: SQLAlchemy's ORM deduplicates full-entity `.all()` results by primary key, so the duplicate rows collapse before I ever see them. The join is still wrong (tags come from the relationship in `to_dict()`, not the join), but the "you'll see 3 copies" story is incomplete in this environment. This is exactly the case the brief warns about — a plausible AI explanation that would have been documented as fact if I hadn't reproduced it myself. Every fix in this submission was verified by reproducing the bug first and re-running the behavior after the change; no fix rests on an unverified AI hypothesis.

### How the app is organized

Mixtape is a Flask app using the **application-factory + blueprint** pattern with a **routes → services → models** layering. The layering is strict and consistent:

- **Routes** parse the HTTP request (query params / JSON body), call exactly one service function, and format the response with `jsonify`. They contain no business logic.
- **Services** hold all business logic and are the only layer that talks to the database.
- **Models** are pure SQLAlchemy schema + `to_dict()` serialization.

Because of this, every bug in the tracker lives in `services/` — the routes just surface it.

### Main files and their roles

| File | Responsibility |
|------|----------------|
| `app.py` | Application factory `create_app()`. Creates the shared `db = SQLAlchemy()` instance, configures the SQLite URI, registers the four blueprints under URL prefixes (`/songs`, `/playlists`, `/users`, `/feed`), and calls `db.create_all()`. Must be launched with `FLASK_APP=app:create_app flask run`. |
| `models.py` | Defines the data model: **6 models** — `User`, `Tag`, `Song`, `ListeningEvent`, `Rating`, `Notification` — plus **3 association tables** — `friendships` (symmetric self-referential M2M on User), `song_tags` (Song↔Tag M2M), and `playlist_entries` (Playlist↔Song M2M **with extra `position`, `added_by`, `added_at` columns** — so playlist order is explicit, not insertion order). |
| `seed_data.py` | Drops and recreates all tables, then loads deterministic test data: 5 users with friendships, 13 songs (deliberately grouped into 0-tag, 1-tag, and 3+-tag sets to expose the search bug), 3 playlists, listening events split into a "recent" set (~10–20 min ago) and an "old" set (2+ hours ago) to exercise the feed window, and one working `song_added_to_playlist` notification so the correct notification pattern is visible when investigating the missing rating notification. |
| `routes/songs.py` | `/songs/search`, `/songs/<id>`, `/songs/<id>/rate` (POST), `/songs/<id>/listen` (POST). Delegates to `search_service`, `notification_service.rate_song`, and `streak_service.record_listening_event`. |
| `routes/playlists.py` | Create playlist, get playlist metadata, get playlist songs, add song to playlist. Add-song delegates to `notification_service.add_to_playlist`. |
| `routes/users.py` | Get user, get streak, list notifications, mark notification read. |
| `routes/feed.py` | `/feed/<user_id>/listening-now` and `/feed/<user_id>/activity`. |
| `services/streak_service.py` | `record_listening_event` (writes an event + updates streak) and `update_listening_streak` (the consecutive-calendar-day increment/reset rules). |
| `services/feed_service.py` | `get_friends_listening_now` (friends active within a recency window, deduped to the latest song per friend) and `get_activity_feed` (most recent N events, no recency filter). |
| `services/search_service.py` | `search_songs` (title/artist `ilike` match) and `get_song`. |
| `services/notification_service.py` | `create_notification`, `add_to_playlist` (adds song + notifies sharer), `rate_song` (upsert a rating), `get_notifications`, `mark_as_read`. |
| `services/playlist_service.py` | `create_playlist`, `get_playlist_songs` (ordered by `position`), `get_playlist`, `get_user_playlists`. |
| `tests/` | Pytest suites for streaks, search, and playlists (each with an in-memory SQLite fixture). No suite exists for notifications or feed. |

### Data flow trace — adding a song to a playlist triggers a notification

This is the flow the "missing rating notification" bug (Issue #4) should be compared against.

1. `POST /playlists/<playlist_id>/songs` with JSON `{song_id, added_by}` hits `add_song()` in `routes/playlists.py`. The route validates both fields are present, then calls `add_to_playlist(playlist_id, song_id, added_by)`.
2. `notification_service.add_to_playlist()`:
   - loads the `Song`, adding `User` (the person doing the add), and `Playlist`, raising `ValueError` if any is missing;
   - appends the song to `playlist.songs` (the `playlist_entries` M2M) if not already present, and commits;
   - if the adder is not the original sharer (`song.shared_by != added_by_user_id`), calls `create_notification(user_id=song.shared_by, type="song_added_to_playlist", body=...)`.
3. `create_notification()` builds a `Notification` row, adds it, and commits.
4. Later, the sharer sees it via `GET /users/<id>/notifications` →
   `get_notifications()` → ordered `Notification` rows serialized by `to_dict()`.

The rating flow (`POST /songs/<id>/rate` → `rate_song`) mirrors this — it loads the song and rater, and knows `song.shared_by` — but it stops after upserting the `Rating` and **never calls `create_notification`**. That asymmetry is the root cause of Issue #4.

### Patterns worth noting

- **Strict route→service delegation.** No DB access in routes; trace any endpoint bug into its one service call.
- **The join table carries data.** `playlist_entries.position` means song order is authoritative and queries must `order_by(position)` — relevant to the playlist bug.
- **Recency is a service-level constant.** `feed_service.RECENT_THRESHOLD` is the single knob defining "now."
- **Ratings are upserts** guarded by a `UniqueConstraint(user_id, song_id)` — re-rating updates the score rather than inserting.
- **Timezone handling is defensive.** `update_listening_streak` re-attaches `timezone.utc` to naive `last_listened_at` values before comparing dates.

---

## Milestone 1: Issue triage (all five read; rough plan)

I read all five issue descriptions and reproduced each against the seeded DB / test suite before choosing. Findings so far (root causes to be confirmed and fixed in later milestones):

| # | Issue | Suspected root cause | Reproducible now? |
|---|-------|----------------------|-------------------|
| 1 | Streak keeps resetting | `update_listening_streak` has a spurious `and today.weekday() != 6` guard on the increment branch — a Sunday consecutive-day listen falls through to the reset branch. | Yes - `test_streak_increments_on_sunday` fails. |
| 2 | Listening Now shows people from yesterday | `RECENT_THRESHOLD = timedelta(hours=24)` — far too wide for "now"; stale events within a day leak in. | Yes - Older events fall inside the 24h window. |
| 3 | Same song appears twice in search | `search_songs` does a pointless `outerjoin(song_tags)`; a 3-tag song fans out to 3 rows. Currently masked because the SQLAlchemy ORM dedupes full-entity `.all()` results by PK — but the join is fragile and wrong (tags come from the relationship in `to_dict()`, not the join). | No - Latent — the design flaw is real; needs the join removed / `.distinct()` to be backend-proof. |
| 4 | Rated but not notified | `rate_song` never calls `create_notification`, unlike `add_to_playlist`. Architectural omission, not a typo. | Yes - Notification count unchanged after a rating. |
| 5 | Last song in a playlist never shows | `get_playlist_songs` returns `songs[:-1]`, dropping the final element. | Yes - `test_playlist_returns_all_songs` fails (returns 4 of 5). |

**Rough plan:** the three I'll fix first are the cleanly reproducible, highest-impact ones — **#1 (streak)**, **#4 (notification)**, and **#5 (playlist)** — each with a full root cause analysis and its own commit. Stretch: **#2 (feed)** and **#3 (search)**.

### AI tool disclosure

AI assistance (Claude Code) was used to accelerate codebase orientation — summarizing each service file's responsibilities and tracing the route→service→model call chains above. All bug reproductions were confirmed by running the test suite and executing the service functions against the seeded database.

---

## Root Cause Analyses

The three bugs fixed are **#1 (streak reset)**, **#4 (missing rating notification)**, and **#5 (dropped last playlist song)**. Each was reproduced deterministically before any code changed, fixed with the smallest targeted change, and re-verified against both the test suite and a direct behavioral re-check (including the boundary on both sides).

### Issue #1 — My listening streak keeps resetting

**How I reproduced it.** The streak rules live in `update_listening_streak(user, now)`, and the trigger is calendar-day based, so I drove the function directly with fixed datetimes rather than through HTTP (faster and deterministic — no dependence on today's real date). I called it with a Saturday (`2024-06-15`, `weekday() == 5`) then the following Sunday (`2024-06-16`, `weekday() == 6`). Expected the streak to go `1 → 2`; it stayed at `1`. The existing `test_streak_increments_on_sunday` fails for the same reason, confirming it's the reported bug and not my test harness.

**How I found the root cause.** Navigation path: `routes/songs.py` `/listen` → `streak_service.record_listening_event` → `update_listening_streak`. Reading the branch ladder, the increment branch was `elif days_since_last == 1 and today.weekday() != 6:`. The moment of confidence: the reproduction only failed *on Sunday*, and `weekday() == 6` is exactly Sunday in Python's convention — the extra `and today.weekday() != 6` clause is the only thing in the function that treats Sunday differently, so a consecutive-day listen that lands on a Sunday skips the increment branch and falls through to the `else: streak = 1` reset.

**The root cause.** Python's `datetime.weekday()` returns `6` for Sunday. The increment branch required `days_since_last == 1 AND today.weekday() != 6`. On every other day a consecutive-day listen increments; but when "today" is Sunday the second condition is false, so control falls to the `else` branch and the streak is reset to `1`. The streak rules make no mention of weekdays — the `weekday() != 6` guard has no legitimate purpose; it's spurious logic that silently breaks the streak once a week for anyone whose streak crosses into a Sunday.

**My fix and side-effect check.** Removed the `and today.weekday() != 6` clause so the branch is simply `elif days_since_last == 1:`. I verified both sides of the boundary: Sat→Sun now yields `2` (increment restored), and the reset path is untouched — Mon→Wed (a skipped Tuesday, `days_since_last == 2`) still resets to `1`, and same-day (`days_since_last == 0`) still no-ops. All four existing streak tests pass, including `test_streak_resets_after_skipped_day` and `test_streak_does_not_double_count_same_day`.

### Issue #4 — Notified when a friend adds my song to a playlist, but not when they rate it

**How I reproduced it.** The rating path is `POST /songs/<id>/rate` → `rate_song`. Against the seeded DB I recorded nova's notification count, had **darius rate a song nova shared**, then re-counted. It stayed at `1` — no notification was created. For contrast I ran the *working* path (`add_to_playlist`), which does produce a notification, confirming the feature works in general and only the rating path is broken.

**How I found the root cause.** This is architectural, so I compared the two sibling functions in `notification_service.py` line by line. `add_to_playlist` ends with a guarded `create_notification(user_id=song.shared_by, notification_type="song_added_to_playlist", …)`. `rate_song` performs all the same prerequisite work — it loads `song`, loads `rater`, and therefore has `song.shared_by`, `rater.username`, `song.title`, and `score` in scope — but after `db.session.commit()` it simply `return rating`. Confidence came from seeing that the data needed to notify was already fetched and unused: nothing was missing except the call itself.

**The root cause.** `rate_song` never calls `create_notification`. It's not a typo or a wrong condition — the notify step that its sibling `add_to_playlist` performs was simply never written into the rating path, so rating a song persists the `Rating` row and stops. The recipient (`song.shared_by`) is never told.

**My fix and side-effect check.** After the commit, added a guarded notification mirroring `add_to_playlist` exactly: `if song.shared_by != user_id:` → `create_notification(user_id= song.shared_by, notification_type="song_rated", body=f"{rater.username} rated your song '{song.title}' {score}/5.")`. The `!=` guard prevents self-notification (same guard style as the playlist path). Side-effect checks: (a) a friend rating another user's song now increments the count `1 → 2`; (b) a user rating **their own** song does *not* notify (`2 → 2`); (c) the rating upsert itself is unchanged — re-rating still updates the score via the existing branch and does not create a duplicate `Rating` (the `UniqueConstraint(user_id, song_id)` still holds); (d) `get_notifications` ordering and the existing playlist notification behavior are unaffected. All existing tests still pass.

### Issue #5 — The last song in a playlist never shows up

**How I reproduced it.** Path: `GET /playlists/<id>/songs` → `get_playlist_songs`. I picked a seeded playlist with 7 `playlist_entries` rows and called the function: it returned **6** songs. `test_playlist_returns_all_songs` (expects 5, gets 4) fails identically. The song that goes missing is always the highest-`position` one, which matched the report ("the *last* song").

**How I found the root cause.** Straight read of `get_playlist_songs`: the query correctly joins `playlist_entries`, filters by `playlist_id`, and orders by `asc(position)` — the ordering and filtering were right. The return line was `return [song.to_dict() for song in songs[:-1]]`. The `[:-1]` slice was the giveaway: it drops the final element of an already-correct, position-ordered list. Because the list is ordered ascending by position, the dropped element is always the last song in the playlist — exactly the reported symptom.

**The root cause.** The list comprehension sliced the result with `songs[:-1]`, which excludes the last element. The database query returns the complete, correctly ordered set; the truncation happens purely in the Python return statement. There is no legitimate reason to drop the last song — it's an off-by-one truncation, not a query or ordering error.

**My fix and side-effect check.** Changed `songs[:-1]` to `songs` so every row is returned. Verified: the 7-entry playlist now returns 7, in ascending position order (order was never the problem and is preserved). Boundary check on the small side — `test_empty_playlist_ returns_empty_list` still passes (an empty list sliced or not is `[]`, and importantly `[:-1]` on a 1-song playlist would have wrongly returned `[]`, so this fix also repairs the single-song case). `test_playlist_returns_songs_in_order` and `test_playlist_returns_all_ songs` both pass.

### AI usage during investigation (Milestone 3)

I used Claude Code as a navigation and explanation aid, following the recommended workflow (find the suspicious code myself → have the AI explain/compare it → verify by reading and running it). Specifically: comparing the two sibling functions `add_to_playlist` vs `rate_song` to articulate the structural difference (Issue #4), and confirming Python's `datetime.weekday()` Sunday convention (`Sunday == 6`) once I'd already narrowed Issue #1 to the weekday clause. Every diagnosis was verified by reproducing the bug and re-running the behavior after the fix — no fix was made on an unverified hypothesis.

