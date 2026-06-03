# Architecture

Internal technical reference for `reviews_scraper.py`. For usage instructions see [README.md](../README.md). For CLI flags see [configuration.md](configuration.md).

> **Note:** Trustpilot support was removed in v2. DataDome bot detection reliably blocks non-browser HTTP clients, making it unreliable for automated use.

---

## High-Level Flow

```
main()
  └── build_parser() + resolve_config()   # CLI args → env vars → defaults → Config
  └── apply_config_globals()              # Sync Config back to module-level constants
  └── validate_config()                   # Exit EXIT_CONFIG_ERROR on bad input
  └── [dry_run] → print plan, exit 0
  └── scrape_all_platforms(cfg)
        ├── scrape_app_store()            # RSS API, per-country
        └── scrape_google_play()          # google-play-scraper library
  └── analyze_reviews()                   # VADER or Hugging Face sentiment
  └── save_csv()                          # pandas → CSV
  └── [json_summary] → print JSON to stdout
  └── sys.exit(exit_code)
```

---

## Config Resolution

Priority order: **CLI flag → environment variable → hardcoded default**

`resolve_config(args)` implements this with a `_first(*vals)` helper that returns the first non-None value. `apply_config_globals()` then writes the resolved values back into the module-level constants so existing internal code that reads globals directly continues to work.

---

## App Store Scraping

- **Source:** Apple's public RSS JSON endpoint — no API key required.
- **URL pattern:** `itunes.apple.com/{country}/rss/customerreviews/page={n}/id={app_id}/sortby=mostrecent/json`
- **Multi-country:** Countries are scraped sequentially (not concurrently) because the RSS endpoint is rate-sensitive. Deduplication happens after all countries are collected using the same hash key.
- **Stopping condition:** When the oldest review in a page falls outside the 12-month window, scraping stops for that country.
- **Deduplication key:** `(review_date, star_rating, sha256(review_text)[:16])`
- **Session:** Connection pooling via `requests.Session` + `HTTPAdapter`.

---

## Google Play Scraping

- **Source:** `google-play-scraper` library (wraps the internal Play Store API).
- **Pagination:** Token-based (`continuation_token`). Iterates until the token is None, max pages is reached, or consecutive errors exceed `MAX_CONSECUTIVE_ERRORS`.
- **Stopping condition:** When the oldest `at` timestamp in a batch falls outside the 12-month window. This is age-based (not sparsity-based) to avoid premature termination on apps with low review volume.
- **Extended fields:** `thumbsUpCount`, `replyContent` (developer reply), `repliedAt` available from the library's response dict.
- **Deduplication key:** `(review_date, star_rating, sha256(review_text)[:16])`

---

## Sentiment Analysis

`build_sentiment_scorer(use_hf)` returns a `(score_fn, backend_name)` tuple. The scorer is built once in `main()` and passed to `analyze_reviews()`.

| Backend | Trigger | Score range | Notes |
|---------|---------|-------------|-------|
| NLTK VADER | Default | [-1, 1] | Runs locally, no download beyond lexicon |
| Hugging Face distilbert-sst2 | `--use-hf` or `USE_HF=1` | [-1, 1] mapped from prob | Requires `transformers` package |

Score → label mapping (configurable via `GOOD_THRESH` / `BAD_THRESH` globals):
- `>= 0.25` → `good`
- `<= -0.25` → `bad`
- otherwise → `neutral`

---

## Output

`build_output_path(output_dir, app_name, platform, analysis)` assembles filenames:

| single_file | output_mode | Filename |
|-------------|-------------|----------|
| True | reviews | `{app_name}_reviews.csv` |
| True | analysis | `{app_name}_reviews_analysis.csv` |
| False | reviews | `{app_name}_{platform}_reviews.csv` |
| False | analysis | `{app_name}_{platform}_reviews_analysis.csv` |

All output sorted by `review_date DESC, star_rating DESC`. Written with `csv.QUOTE_ALL` to handle embedded commas and newlines in review text.

---

## Exit Codes

| Code | Constant | Meaning |
|------|----------|---------|
| 0 | `EXIT_SUCCESS` | All platforms returned data; all files written |
| 1 | `EXIT_CONFIG_ERROR` | Invalid or placeholder configuration |
| 2 | `EXIT_PARTIAL_FAILURE` | At least one platform returned data; at least one returned nothing |
| 3 | `EXIT_TOTAL_FAILURE` | All platforms returned 0 reviews |
| 130 | `EXIT_INTERRUPTED` | SIGINT or SIGTERM received |

---

## Graceful Shutdown

`signal_handler()` sets a module-level `shutdown_requested` flag on SIGINT or SIGTERM. All scraping loops check this flag at the start of each iteration and break cleanly. Partial data collected before shutdown is saved normally.

---

## Deduplication

All three platforms use the same key structure: `(review_date, star_rating, sha256(review_text)[:16])`. Using a hash of the full text (rather than a truncated substring) prevents false deduplication of reviews that share long identical openings but differ in the body.
