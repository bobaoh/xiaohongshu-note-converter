# AGENTS.md

This repository turns a link into structured Markdown + JSON notes. Examples: a recipe, a travel guide, a product review, a tutorial, a summary, or a format the user describes. Supported links:

- Xiaohongshu / RedNote notes, both video and image posts
- Reddit posts, read through Reddit's public RSS feeds: text, image, GIF, video, gallery, and link posts, with their comments
- any ordinary web page: articles, blogs, recipe sites, documentation

`scripts/discover.py` lists popular Reddit posts for the topics in `reddit_topics.toml`. Turning them into notes on a schedule is designed in `docs/reddit.md` but not built.

It also records what every conversion costs and flags the expensive ones.

## When the user gives a link

Trigger this workflow for any http(s) link the user wants turned into notes, or when the user asks to reformat something already extracted (for example "换成 tutorial 格式").

1. Read `.claude/skills/note/SKILL.md` in full, then follow its workflow and general rules exactly. It is the single source of truth, shared with Claude Code. Do not work from memory of an earlier read.
   - Source-specific notes live in `.claude/skills/note/sources/<source>.md`.
   - `.claude/skills/xhs-note/SKILL.md` is the older Xiaohongshu-only skill. It is kept unchanged for the xhs-library project; do not use it for new work.
2. Output formats live in `.claude/skills/xhs-note/formats/`, shared by all sources.
   - The user names a format (`recipe`, `菜谱`, `travel-guide`…): read that file.
   - The user gives no format: read only the frontmatter of each file and pick one, as SKILL.md describes.
   - The user describes fields instead of naming a format: create a `custom:<name>` result, as SKILL.md describes.
3. Finish every conversion with the two steps below. Report the result of both to the user, along with any cost flags.
   - Write `results/<note_id>-<format>.md` and `results/<note_id>-<format>.json`.
   - Run `python scripts/validate_result.py results/<note_id>-<format>.json` and fix any errors.

## Environment notes for Codex

- **Network is required.** `scripts/extract.py` fetches the page and downloads images or video. The first run also downloads the Whisper model. If the sandbox blocks network access, request approval to run the command with network access; do not try to work around the block.
- **Video notes take 2–4 minutes** because of local transcription. Let the command finish; do not kill it early or rerun it in parallel. Web pages take seconds.
- **Reddit allows about one request per minute.** The extractor waits as Reddit's rate-limit headers ask, so a Reddit link can sit for up to a minute before anything happens. Do not run several Reddit extractions in parallel to save time; they share the same limit.
- **Reuse extractions.** `scripts/extract.py` reuses a complete extraction by itself. Pass `--force` only when the user asks to extract again.
- **Images.** SKILL.md asks you to look at `media/image-NN.jpg` when steps, maps, or price lists are shown only in pictures. If you cannot view local images, rely on `ocr.txt` and list what could not be checked in the result's `missing` field.
- **FFmpeg on Windows.** If `ffmpeg` is not found right after installation, reload PATH in PowerShell before retrying:
  `$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')`

## If you cannot run commands

This applies to web chat AIs or agents without a shell, for example when the user uploads this file or links the repository.

1. You cannot extract the link yourself. Ask the user to run the extractor locally:
   `python scripts/extract.py "<LINK>"` (it prints the output directory)
2. Ask them to upload these files:
   - `metadata.json`, `caption.txt`, `ocr.txt`, and `transcript.txt` from that directory
   - `.claude/skills/note/SKILL.md` and the matching `.claude/skills/note/sources/<source>.md`
   - the chosen format file from `.claude/skills/xhs-note/formats/`
   - any images from `media/` that show steps, maps, or prices
3. Follow SKILL.md as usual. You cannot write files, so reply with exactly two code blocks: first ```markdown, then ```json. The JSON must use the envelope defined in SKILL.md.
4. Tell the user to save them as `results/<note_id>-<format>.md` and `.json`, then run `python scripts/validate_result.py` on the JSON.

## Safety

- Process only public links the user supplied.
- Do not bypass login walls, private-note permissions, paywalls, CAPTCHAs, or DRM.
- Never ask for, store, or print cookies, session tokens, QR-login data, or passwords.
- Reddit: read only the public RSS feeds and media hosts, identified by `notekit.sources.reddit.USER_AGENT`. Do not retry around a 403, spoof a browser, or use other endpoints to get past a block. Future API credentials go only in the git-ignored `reddit_credentials.toml` (see `docs/reddit.md`).
- If a link is unavailable, report the `error` from `metadata.json` and stop.

## Architecture

```
scripts/extract.py        CLI for any link (default output dir, reuse, --where, --force)
scripts/extract_note.py   original CLI, kept for xhs-library (always extracts into --output)
scripts/discover.py       CLI: popular Reddit posts per topic in reddit_topics.toml, optionally extracted
notekit/
  pipeline.py             picks a source, runs it under cost tracking, writes metadata.json
  discover.py             topic loading, filtering, deduplication, and caps for scripts/discover.py
  sources/__init__.py     Source interface and registry (SOURCES); read its docstring first
  sources/xiaohongshu.py  Xiaohongshu notes
  sources/reddit.py       Reddit posts: RSS client with rate limiting, RedditClient interface for a future API client
  sources/web.py          any other web page (trafilatura + schema.org JSON-LD)
  media.py                FFmpeg, Whisper transcription, OCR (source-agnostic)
  net.py                  fetching and downloads (tests replace these)
  cost.py                 cost tracking, expensive flags, prediction, ledger
cost_policy.toml          thresholds and estimate factors; per-source limits ([web], [reddit])
reddit_topics.toml        topics for scripts/discover.py
docs/reddit.md            how Reddit is read, discovery, and the planned scheduled crawl
scripts/cost_report.py    summary of the cost ledger
```

Every source writes the same output directory (`metadata.json`, `caption.txt`, `ocr.txt`, `transcript.txt`, `media/image-NN.jpg`, optionally `structured.json` and `comments.txt`), so the skill, formats, validation, and cost tracking work the same for all of them.

### Adding a source

The checklist is in the docstring of `notekit/sources/__init__.py`. In short:

1. Create a `Source` subclass in `notekit/sources/<name>.py` and register it before `WebSource`, which accepts any link.
2. Report cost with `cost.stage`, `cost.count`, and `cost.predict`.
3. Write output to `output/<name>/<key>/` (`output_subdir = name`). Never write to `output/<key>/` directly; that layout belongs to Xiaohongshu (see the contract below).
4. Add unit tests, a regression link in `tests/fixtures/regression_links.json`, and `.claude/skills/note/sources/<name>.md`.

## Contract with xhs-library

The xhs-library project (`claude/xhs-library`) runs this repository as a separate tool and may be running at any time. Other agents work on it. Its `xhs_library/extractor_adapter.py` relies on the following; `tests/test_contract_xhs_library.py` checks all of it.

- `python scripts/extract_note.py <url> --output <dir> [--keep-media]`. `--help` must list both flags. It must always extract, with no reuse.
- `output/<key>/` with `<key>` from `xhs_library.links.link_key`: the short code for xhslink.com, else the 24-hex note ID.
- `metadata.json` fields:
  - `status`, `error`
  - `note_id` (24 hex)
  - `note_type` (`video` or `normal`)
  - `title`, `author`, `published_at`, `live_photo_count`
- `caption.txt`, `ocr.txt`, and `transcript.txt`.
- `media/image-NN.jpg` for image notes. With `--keep-media`, also `media/frames/*.png`, `media/video.mp4`, and `media/audio.wav`.
- The `/xhs-note` skill and its tool use: it runs `scripts/validate_result.py` and writes `results/<note_id>-<format>.json/.md`.
- `.claude/skills/xhs-note/SKILL.md` and `.claude/skills/xhs-note/formats/*.md`, at those paths.
- Its contract test reads every `output/*/metadata.json`. Other sources must therefore never write directly into `output/<key>/`.

Rules:

- Do not change any of the above without a coordinated change in xhs-library. Adding fields to `metadata.json` is fine; removing or renaming them is not.
- Never edit, run tests in, or write files into the xhs-library directory from here.
- The library reads and writes this repository's `output/` and `results/`. Do not delete, move, or rewrite their contents; extract into a temp directory when experimenting.
- Develop in a separate git worktree or branch: a half-edited `scripts/` in this checkout breaks the library's running jobs.

## Cost tracking

`metadata.json["cost"]` and the ledger (`logs/conversions.jsonl`, git-ignored, one line per conversion including failures) record:

- time per stage, bytes downloaded, video seconds, OCR frames and images
- the estimated input for the AI formatting step: text tokens and images
- a prediction made before the expensive part
- `flags`, and `expensive` when any threshold in `cost_policy.toml` is exceeded

`python scripts/cost_report.py` shows:

- the flagged conversions
- where the time goes
- cost per source
- the prediction error

Conventions:

- **Flagging only.** Nothing is refused yet. A future limit will use `cost.predicted`, so keep predictions honest: predict with what is known just before the expensive step.
- **When adding work that costs time or tokens**, report it with `cost.stage` and `cost.count`. If it can be large, add a threshold and flag to `cost_policy.toml`, `DEFAULT_POLICY`, and `FLAGS` in `notekit/cost.py`. `tests/test_cost.py` checks that the three stay in sync.
- **Bound the cost up front where possible.** For example, `[web] max_images` limits how many images go through OCR, instead of only flagging afterwards.
- **Tests never write to the real ledger.** `tests/conftest.py` points `NOTE_COST_LEDGER` to a temp file.
- **Tag the ledger context.** Set `NOTE_COST_CONTEXT` (for example `regression`) so the report can separate real use from tests.

## Working on the code

- `scripts/extract_recipe.py` and `scripts/extract_post.py` are aliases of `extract_note.py`; keep them working. `extract_note.py` also re-exports the old function names, which existing tests use.
- Adding a format means adding a file to `.claude/skills/xhs-note/formats/` that follows `_TEMPLATE.md`. `validate_result.py` reads each format's `## 字段说明` table, so keep its columns (`字段 | 类型 | 必填 | 说明`) intact.
- `output/`, `results/`, `logs/`, and `tests/fixtures/local/` are git-ignored and hold other people's content. Do not commit them.

## Testing

There are three layers. Run them in this order, and report which ones you ran and their results.

| Layer | Command | When | Time |
|---|---|---|---|
| 1. Offline | `python -m pytest` | After every code or format change. CI also runs it on every push. | ~1–2 min |
| 2a. Cached real pages | `python -m pytest -m "local and not slow"` | After any change to page parsing in a source | < 1 s |
| 2b. Cached real media | `python -m pytest -m local` | Before merging changes to OCR, transcription, FFmpeg calls (`notekit/media.py`), image handling, `WHISPER_REVISIONS`, or dependencies | 7–11 min |
| 3. Live regression | `python scripts/regression.py` | Before merging source changes, and when a site may have changed its pages | ~12 min, needs network |

- **Layer 1** has three parts:
  - Unit tests for parsing, routing, cost tracking, discovery, and validation. They use synthetic pages and Reddit feeds built in `tests/conftest.py` and `tests/test_web.py`. Reddit's rate limiter never sleeps in tests (`no_reddit_waits` in conftest).
  - Media tests. They run FFmpeg, OCR, and Whisper `tiny` on original synthetic media in `tests/fixtures/synthetic/`.
  - The xhs-library contract (`tests/test_contract_xhs_library.py`). If it fails, the change breaks xhs-library.
- **Layer 2** uses real notes and pages cached in `tests/fixtures/local/`. Create the cache once with `python tests/fixtures/fetch_local.py`. Tests for links that are not cached are skipped, so a skip is not a pass. Say so if the cache is missing.
  - The fast part (2a) parses the cached pages.
  - The slow part (2b, marked `slow`) reruns OCR and transcription. About 85% of its time is OCR: roughly 1.8 s per video frame and 5–7 s per image.
- **OCR speed.** Before changing OCR settings to speed things up, compare the recognized text on every cached frame and image, not a sample.
  - Tried and rejected: running OCR in several processes gives no speedup, because onnxruntime already uses every core.
  - Tried and rejected: `det_limit_type=max` with `det_limit_side_len=960` is 19% faster, but it merges ingredient lines and drops text.
- **Layer 3** exit code 2 means some links were unavailable, not that the code is broken. Report it; do not change the expectations to make it pass.
- Expectations for layers 2 and 3 live in `tests/fixtures/regression_links.json`. Change an expectation only when the page itself changed, and say why.
- When you fix a bug, add a test that fails without the fix.
- The synthetic media is generated by `tests/fixtures/make_synthetic.py`, which needs Windows for the zh-CN speech voice. Regenerate it only when the fixtures need to change, and commit the output.

## Dependencies

- Install with `python -m pip install -r requirements-dev.txt -c requirements.lock`. Test against the locked versions, not whatever happens to be installed.
- `requirements.txt` holds the allowed ranges; `requirements.lock` holds the exact tested versions, including indirect dependencies. When adding or upgrading a package:
  1. Update both files.
  2. Run layer 1 on the locked versions.
  3. Let CI confirm all three platforms before merging.
- Refresh the lock from the weekly `latest dependencies` workflow artifacts, as described at the top of `.github/workflows/latest-deps.yml`. Keep the environment-marker line pairs for packages that resolve differently by Python version, such as `rapidocr-onnxruntime`.
- Whisper models are pinned by commit ID in `WHISPER_REVISIONS` (`notekit/media.py`). If you change a revision, also update the cache key in `.github/workflows/tests.yml`.
- Do not work around a broken upstream release by loosening the lock. Pin away from it or avoid the broken code path, as `load_wav` does for PyAV 19, and add a test.
