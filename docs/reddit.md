# Reddit: posts, discovery, and the planned scheduled crawl

| Part | Status |
|---|---|
| Turn a Reddit post link into a note (`/note <link>`, `scripts/extract.py`) | Built |
| List popular posts per topic, optionally extract them (`scripts/discover.py`, `reddit_topics.toml`) | Built; run by hand |
| Turn popular posts into notes automatically on a schedule | Designed below, not built |
| Official Reddit API client | Interface ready, not built |

## How Reddit is read

Reddit returns HTTP 403 to scripts that read its JSON endpoints or post pages without signing in, and old.reddit.com returns a block page. This tool does not try to get around that. It reads Reddit's public RSS (Atom) feeds, which stay open, and identifies itself as `python:notekit:0.1 (personal note converter)` instead of posing as a browser.

| A post feed (`/comments/<id>/.rss`) has | It does not have |
|---|---|
| title, author, subreddit, time | scores, comment counts |
| the post text (HTML) | which comment replies to which |
| what the post links to: an i.redd.it image or GIF, a v.redd.it video, a gallery, or an outside page | the images of a gallery after the first one |
| a preview image | more than about 40 comments |
| about 40 comments in Reddit's default order, replies right after their parent | |

Media comes from Reddit's media hosts without signing in:

- **Images and GIFs:** downloaded from i.redd.it.
- **Videos:** saved from `https://v.redd.it/<id>/HLSPlaylist.m3u8` with FFmpeg. The best quality is chosen and the audio is merged in.
- **Galleries:** only a cropped preview of the first image is available.

**Rate limit.** In October 2026, every feed request left `x-ratelimit-remaining: 0` with `x-ratelimit-reset` between 12 and 59 seconds, so in practice one request per minute is allowed. The client in `notekit/sources/reddit.py`:

- waits as long as that header says;
- retries up to 4 times after HTTP 429;
- stops at once on HTTP 403.

As a result:

- Extracting one post takes one request.
- Discovery takes one request per subreddit per topic.
- A run with 2 topics, 3 subreddits, and 4 extracted posts takes about 7 minutes, mostly waiting.

## Discovery, by hand

```powershell
python scripts/discover.py                     # what each topic would pick; changes nothing
python scripts/discover.py --topic recipes     # one topic
python scripts/discover.py --all               # also show filtered and duplicate posts
python scripts/discover.py --extract           # extract the picked posts into output/reddit/<id>/
python scripts/discover.py --json              # machine-readable, for the scheduler
```

Topics live in `reddit_topics.toml`. A topic is a set of subreddits, read through their feeds (`sort`, `time`) or searched with a `query`, plus filters:

- `kinds`: which post kinds to keep (text, image, gif, video, gallery, link, crosspost)
- `include` / `exclude`: words to look for in the title

Popularity comes from Reddit's own ranking: with `sort = "top"` and `time = "day"`, the first post is the highest-scored post of the day. `min_score` and `min_comments` are accepted but only apply once an API client supplies scores.

Each listed post gets one status:

| Status | Meaning |
|---|---|
| `picked` | Will be extracted with `--extract` |
| `done` | Already extracted (`output/reddit/<id>/metadata.json` is complete) |
| `failed-before` | An earlier extraction failed; `--retry-failed` picks it again |
| `filtered` | Fails a topic filter, or was posted by AutoModerator (pinned announcements) |
| `duplicate` | Already listed under an earlier topic in this run |
| `over-limit` | The topic's `max_new` or the run's `max_total` is used up |

`--extract` only extracts. The formatting step stays in Claude Code (`/note <link>`) or in xhs-library.

## Planned: scheduled crawl into notes (not built)

**Goal:** once a day, pick a few popular posts per topic and add them to the note library as formatted notes, within a daily budget, without anyone watching.

**Where:** in xhs-library, which already has the job queue, the AI formatting step, the board, and per-job AI cost estimates. This repository supplies discovery and extraction, as it does now.

### Flow

1. **Trigger.** Once a day at a configured time. Two options:
   - A timer inside the library server. Simpler, but only runs while the server is up.
   - Windows Task Scheduler running a library command. Runs even when the server is down.
2. **Discover.** Run `python scripts/discover.py --json --max-total <N>`, where `N` is what is left of today's budget. It is one command, which fits the library's command allowlist.
3. **Deduplicate.** discover.py already skips extracted posts. The library also skips posts already in its database. It should match on the note ID (derived from the post ID), so that different links to the same post match.
4. **Submit.** Each picked post goes through the library's existing path for non-Xiaohongshu links: extract (`OtherLinksExtractor`), then format with `/note` using the topic's `format`, then the board. Tag each note with "Reddit" and its topic.
5. **Hold expensive posts.** After extraction and before formatting, check the result:
   - If `metadata.cost.expensive` is true, hold the note for approval instead of formatting it.
   - Long GIFs and videos are the usual cause.
6. **Caps.** Stop submitting once any of these is reached:
   - notes per day
   - AI dollars per day, using the library's own estimate for each job
   - wall time per run (rate-limit waits make runs long)
7. **Failures.**
   - Reddit 429 or 403: stop the run, log it, and try again the next day.
   - Failed extraction: recorded in that post's `metadata.json`. discover.py then marks the post `failed-before` and skips it.
8. **Report.** A view of what the last run added, what is held, and what failed. The cost ledger (`logs/conversions.jsonl`, context `scheduled`) records every extraction.

### Proposed settings (xhs-library `config.toml`)

```toml
[reddit_crawl]
enabled = false
time = "07:00"
topics_file = "../Xiaohongshu/reddit_topics.toml"
max_notes_per_day = 5
max_ai_dollars_per_day = 1.50
max_run_minutes = 30
hold_expensive = true      # false: skip expensive posts instead of holding them
```

### Decide before building

- When and how it runs: the server timer or Task Scheduler.
- The real topics and subreddits.
- The daily caps.
- What happens to expensive posts: held or skipped.
- Whether new notes appear on the board directly or wait for review.

## Later: the official API client

**What it would add:**

- scores and comment counts, so `min_score` and `min_comments` work
- every gallery image
- more comments, with reply structure
- a higher rate limit: Reddit documents 100 queries per minute for OAuth clients; check the current Data API terms before building

**What it needs:**

- A Reddit account and a "script" app registered at reddit.com/prefs/apps, which provides a client ID and secret.
- A user agent that names the Reddit account, as Reddit's API rules require.
- Acceptance of Reddit's Data API terms for personal, non-commercial use.

**How it plugs in:**

1. Implement the four methods of `RedditClient` (`post`, `listing`, `search`, `resolve_share_link`) in `notekit/sources/reddit_api.py`, filling in `score` and `num_comments`.
2. Have `make_client()` in `notekit/sources/reddit.py` return it when `reddit_credentials.toml` exists.
   - That file is git-ignored.
   - Credentials must never be committed, logged, or written to `metadata.json`.
3. Nothing else changes: the source, discovery, tests with fake clients, and output all stay the same.

## Rules that do not change

- **Public posts only.** No login, and no working around blocks, private subreddits, or quarantines.
- **Credit every note** with the 原作者 and 原链接 lines.
- **Notes are for personal use.** Do not republish other people's posts.
