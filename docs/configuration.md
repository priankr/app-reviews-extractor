# Configuration Reference

Complete reference for all CLI flags and environment variables. For usage examples see [README.md](../README.md). For agent-specific patterns see [agent-guidelines.md](agent-guidelines.md).

Priority order for every setting: **CLI flag → environment variable → hardcoded default**

---

## App Identifiers

| Flag | Env Var | Type | Required when |
|------|---------|------|---------------|
| `--app-store-id` | `APP_STORE_ID` | string (numeric) | `--platform app-store` is active |
| `--google-play-id` | `GOOGLE_PLAY_ID` | string (`com.example.app` format) | `--platform google-play` is active |

**Finding your IDs:**
- **App Store ID:** The numeric ID in the App Store URL — `apps.apple.com/app/id{ID}`
- **Google Play ID:** The package name in the Play Store URL — `play.google.com/store/apps/details?id={ID}`

> **Trustpilot removed in v2.** DataDome bot detection blocks non-browser HTTP clients. See [README.md](../README.md) for context.

---

## Platform Selection

| Flag | Env Var | Type | Default | Notes |
|------|---------|------|---------|-------|
| `--platform` | — | string (repeatable) | both | Choices: `app-store`, `google-play` |

Example — scrape only App Store:
```bash
python reviews_scraper.py --platform app-store
```

---

## Output

| Flag | Env Var | Type | Default | Notes |
|------|---------|------|---------|-------|
| `--app-name` | `APP_NAME` | string | `yourapp` | Controls output filename prefix |
| `--output-dir` | `OUTPUT_DIR` | path | `.` (current directory) | Created automatically if absent |
| `--output-mode` | `OUTPUT_MODE` | string | `analysis` | Choices: `reviews`, `analysis`, `both` |
| `--single-file` | `SINGLE_FILE` | bool flag | `true` | Combine all platforms into one CSV |
| `--no-single-file` | — | bool flag | — | Write separate CSVs per platform |
| `--json-summary` | — | bool flag | `false` | Print JSON run summary to stdout |
| `--extended-fields` | — | bool flag | `false` | Include optional fields in CSV output |

### Output filename patterns

With `--single-file` (default):
- Reviews: `{app_name}_reviews.csv`
- Analysis: `{app_name}_reviews_analysis.csv`

With `--no-single-file`:
- Reviews: `{app_name}_{platform}_reviews.csv`
- Analysis: `{app_name}_{platform}_reviews_analysis.csv`

### CSV schema — standard fields (always present)

| Column | Type | Description |
|--------|------|-------------|
| `review_date` | string (YYYY-MM-DD) | Date the review was posted |
| `star_rating` | integer (1–5) | Star rating |
| `reviewer_anonymized` | string | Reviewer initials (e.g. `J. D.`) |
| `review_text` | string | Full review body |
| `platform` | string | `App Store` or `Google Play Store` |
| `sentiment_score` | float (-1.0 to 1.0) | Present in analysis output only |
| `sentiment_label` | string | `good`, `neutral`, or `bad`. Present in analysis output only |

### CSV schema — extended fields (`--extended-fields`)

| Column | Platforms | Description |
|--------|-----------|-------------|
| `review_title` | App Store | Review headline (when available and differs from body) |
| `developer_reply` | Google Play | Developer response text, or null |
| `developer_reply_date` | Google Play | Date of developer response (YYYY-MM-DD), or null |
| `thumbs_up_count` | Google Play | Number of helpful votes |

---

## Scraping Parameters

| Flag | Env Var | Type | Default | Notes |
|------|---------|------|---------|-------|
| `--max-pages` | — | integer | — | Overrides all per-platform page limits |
| `--max-pages-app-store` | `MAX_PAGES_APP_STORE` | integer | `20` | ~50 reviews/page |
| `--max-pages-google-play` | `MAX_PAGES_GOOGLE_PLAY` | integer | `50` | 100 reviews/page |
| `--countries` | `APP_STORE_COUNTRIES` | string list | `us` | App Store country codes (space-separated) |
| `--sleep` | `SLEEP_SECONDS` | float | `0.3` | Seconds between requests |
| `--max-workers` | `MAX_WORKERS` | integer | `4` | Concurrent HTTP workers |
| `--timeout` | `REQUEST_TIMEOUT` | integer | `10` | Request timeout in seconds |

### Multi-country App Store scraping

The default `--countries us` scrapes only the US storefront. Apps with a global user base should specify additional country codes to avoid missing reviews from other regions:

```bash
python reviews_scraper.py --countries us gb ca au in [other flags]
```

Each additional country code adds proportional scraping time and rate limit exposure. Scraping is sequential per country to avoid triggering Apple's rate limits.

Common country codes: `us` (United States), `gb` (United Kingdom), `ca` (Canada), `au` (Australia), `in` (India), `de` (Germany), `fr` (France), `jp` (Japan), `br` (Brazil).

### Rate limiting

If a platform starts returning errors or empty pages:
- Increase `--sleep` to `0.6` or higher
- Reduce `--max-workers` to `2` or `1`
- Wait 10–15 minutes before retrying

---

## Mode Flags

| Flag | Env Var | Type | Default | Notes |
|------|---------|------|---------|-------|
| `--quiet` | — | bool flag | `false` | Suppress all progress output; errors still go to stderr |
| `--dry-run` | — | bool flag | `false` | Validate config and print run plan without scraping |
| `--use-hf` | `USE_HF` (set to `1`) | bool flag | `false` | Use Hugging Face distilbert-sst2 instead of VADER |
| `--no-verify-ssl` | `NO_VERIFY_SSL` (set to `1`) | bool flag | `false` | Disable SSL certificate verification. See note below. |

### SSL certificate verification

By default the script verifies SSL certificates using `certifi`'s CA bundle. On networks with a corporate SSL proxy (MITM inspection), certificate verification will fail even with `certifi` installed because the proxy's root CA is not in any public bundle.

**Options:**

1. **`--no-verify-ssl`** — Disables verification entirely. Acceptable on trusted corporate networks; not recommended on untrusted networks. Prints a warning to stderr.

2. **`REQUESTS_CA_BUNDLE`** — Preferred alternative. Export your proxy's root certificate and point this env var at the PEM file:
   ```bash
   REQUESTS_CA_BUNDLE=/path/to/corporate-ca.pem python reviews_scraper.py [flags]
   ```
   This keeps verification enabled and trusted against your specific proxy cert.

---

## JSON Summary (`--json-summary`)

When passed, prints a JSON object to stdout after all files are saved. All other output goes to stderr, so stdout can be piped or captured cleanly.

```json
{
  "status": "success",
  "exit_code": 0,
  "total_reviews": 342,
  "by_platform": {
    "app_store": 120,
    "google_play": 180
  },
  "files_written": ["output/myapp_reviews_analysis.csv"],
  "duration_seconds": 47.2,
  "platforms_failed": [],
  "interrupted": false
}
```

Possible `status` values: `"success"`, `"partial"`, `"failed"`, `"interrupted"`.

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | All platforms returned data; all files written successfully |
| `1` | Invalid or placeholder configuration |
| `2` | Partial failure — at least one platform returned data, at least one returned nothing |
| `3` | Total failure — all platforms returned 0 reviews |
| `130` | Interrupted by SIGINT or SIGTERM |
