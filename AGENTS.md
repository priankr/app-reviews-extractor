# App Reviews Extractor — Agent Entry Point

This repo contains a single Python script (`reviews_scraper.py`) that scrapes app reviews from App Store and Google Play Store, with optional sentiment analysis. No API keys required.

> **Trustpilot removed in v2.** DataDome bot detection blocks non-browser HTTP clients reliably. See [README.md](README.md) for details.

## Quick Start

```bash
python reviews_scraper.py \
  --app-store-id <ID> \
  --google-play-id <com.package.name> \
  --app-name <slug> \
  --output-dir ./output \
  --output-mode analysis \
  --quiet \
  --json-summary
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate   # Linux/Mac
python -m venv .venv && .venv\Scripts\activate       # Windows
pip install -r requirements.txt
```

## Validate before running

```bash
python reviews_scraper.py [all flags] --dry-run
```

Exits `0` if config is valid, `1` if not. Output to stderr.

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Config error — fix the flagged identifier |
| `2` | Partial failure — some platforms returned nothing |
| `3` | Total failure — no reviews collected |
| `130` | Interrupted by signal |

## JSON Summary

Pass `--json-summary` to receive a structured result on stdout:

```json
{
  "status": "success",
  "exit_code": 0,
  "total_reviews": 342,
  "by_platform": {"app_store": 120, "google_play": 180},
  "files_written": ["output/myapp_reviews_analysis.csv"],
  "duration_seconds": 47.2,
  "platforms_failed": [],
  "interrupted": false
}
```

## Key Flags

| Flag | Default | Notes |
|------|---------|-------|
| `--platform` | both | `app-store`, `google-play` |
| `--output-mode` | `analysis` | `reviews`, `analysis`, or `both` |
| `--app-name` | `yourapp` | Output filename prefix |
| `--output-dir` | `.` | Created if absent |
| `--quiet` | false | Suppress progress; errors still go to stderr |
| `--json-summary` | false | Print JSON result to stdout |
| `--extended-fields` | false | Add title, developer reply, thumbs up, verified |
| `--countries` | `us` | App Store country codes (space-separated) |

All flags also accept environment variables. See [docs/configuration.md](docs/configuration.md).

## See Also

- [docs/agent-guidelines.md](docs/agent-guidelines.md) — invocation patterns, rate limiting, partial failure handling
- [docs/configuration.md](docs/configuration.md) — complete flag and env var reference
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — internal architecture
- [README.md](README.md) — human-facing overview and context
