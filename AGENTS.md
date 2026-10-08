# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Commands

```shell
uv sync                                  # install deps (or: pip install -r requirements.txt)
uv run python -m playwright install      # install browser binaries (required once)

uv run python -m src.main_loop           # run the bot (must be from repo root — src/ has no __init__.py)
uv run python -m src.screenshot_threads  # capture Threads posts only (module has its own __main__)
uv run python -m src.screenshot_ig       # capture IG stories only (writes to stories/)
uv run python -m src.record_login        # headed browser to log in and (re)generate auth.json

LOG_LEVEL=DEBUG uv run python -m src.main_loop   # show skipped posts / per-story navigation

uv run ruff check --fix .
uv run ruff format .

docker compose up -d --build             # deploy; docker compose logs -f threads-bot
```

`pytest` is a dev dependency but there are no tests yet.

Lint config is `select = ["ALL"]` with a long ignore list in `pyproject.toml`; line length 120, double quotes.
`ruff check .` currently reports pre-existing E501/RUF001-3 findings (long UA strings, full-width CJK
punctuation) — don't treat those as regressions from your change.

Python is pinned to 3.10 everywhere: `.python-version`, `requires-python`, ruff `target-version = "py310"`,
and the `playwright/python:v1.52.0-jammy` base image (Ubuntu 22.04 ships 3.10).

## Architecture

A single long-running loop (`src/main_loop.py`) that every `INTERVAL_SECONDS` (10 min) scrapes three
sources and pushes anything new to a Discord webhook:

1. `capture_latest_post_screenshots(...THREAD_URLS[0])` — Threads posts
2. `capture_latest_post_screenshots(...THREAD_URLS[1])` — Threads replies
3. `capture_latest_stories(...)` — Instagram stories

Target account (`paul_pork`), URLs, interval and lookback windows are hardcoded constants at the top of
`main_loop.py`. Only `DISCORD_WEBHOOK_URL` comes from `.env`.

### Deduplication is filename-based, and that is the only state

Every captured item is named `{epoch_seconds}.{ext}` where the timestamp is parsed from the post's
`<time datetime="...">` attribute — *not* from capture time. A `path.exists()` check is what prevents
re-sending. There is no hash file or database (the README's mention of "hash 記錄" is stale). Consequences:

- Deleting a file from `screenshots/` causes it to be re-captured and re-sent to Discord.
- `n_lookback` (how many posts to walk) and `time_lookback` (ignore posts older than this) only bound
  the work; correctness of "is this new?" rests entirely on the filename.
- `main_loop` passes `SCREENSHOT_DIR` for stories too, so stories land in `screenshots/` as `.webp`
  even though `stories/` exists and is mounted in `docker-compose.yaml`.

### Two very different capture strategies

- **Threads** (`src/screenshot_threads.py`): renders in a mobile-emulated, dark-mode Chromium context
  (iPhone UA, 390x1688, dsf=3) with **no** `storage_state` — it scrapes logged-out. It takes an
  *element* screenshot of `div[data-pagelet^="threads_profile_posts_timeline_"]`, so the interstitials
  must be nuked first: `page.evaluate` calls delete `div[role="dialog"]`, `nav`, and (retried 3x, since
  it reappears) the `div[role="alert"]` cookie/terms banner by walking fixed `parentElement` chains.
  Those chains and the selector are the fragile part — when Threads ships a DOM change, screenshots come
  out blank or clipped and this is where to look.
- **Instagram** (`src/screenshot_ig.py`): does *not* screenshot. `IGStoryCrawler` drives the story
  player (enter → pause → read `<time>` → next) and downloads the `img[referrerpolicy=...]` `src` via
  `requests`. Videos and unplayable frames are detected and skipped. It requires a valid `auth.json`
  (Playwright `storage_state`) and uses `locale="zh-TW"` because selectors match Chinese
  `aria-label`s ("暫停", "下一則", "查看限時動態"). Changing the locale breaks the crawler.

`auth.json` is only consumed by the IG path. It expires periodically; when stories stop being captured,
re-run `record_login.py` (the Docker container mounts the file, so regenerate it on the host).

### Failure handling

Both capture functions swallow exceptions with `logger.exception` and return whatever they collected, so
one broken source never kills the loop. Meta rate-limits aggressively (429) — the lookback constants were
tuned for that; be conservative about lowering the interval or raising `n_lookback`.
