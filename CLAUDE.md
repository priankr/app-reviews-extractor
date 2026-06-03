# App Reviews Extractor — Claude Code Entry Point

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

> Trustpilot support was removed in v2 (DataDome blocks non-browser scrapers). See README.md.

Validate config without scraping:
```bash
python reviews_scraper.py [all flags] --dry-run
```

## File Map

| Path | What it is |
|------|-----------|
| `reviews_scraper.py` | The scraper — single entry point for all use |
| `requirements.txt` | Python dependencies |
| `examples/` | QuickBooks example output and config |
| `tests/` | Unit tests (`pytest`) |
| `docs/getting-started.md` | Developer setup, usage examples, troubleshooting, tips |
| `docs/configuration.md` | All CLI flags, env vars, defaults, output schema |
| `docs/agent-guidelines.md` | Agent invocation patterns, exit codes, rate limiting |
| `docs/ARCHITECTURE.md` | Internal scraping flow, dedup logic, sentiment pipeline |
| `README.md` | What the tool does, when to use it, human-facing overview |

## Key Flags

| Flag | Purpose |
|------|---------|
| `--platform` | Limit to specific platforms: `app-store`, `google-play` |
| `--output-mode` | `reviews` (raw), `analysis` (with sentiment), or `both` |
| `--app-name` | Output filename prefix |
| `--output-dir` | Where to write CSVs (created if absent) |
| `--quiet` | Suppress progress output (errors still go to stderr) |
| `--json-summary` | Print structured JSON result to stdout |
| `--dry-run` | Validate config, print plan, exit without scraping |
| `--extended-fields` | Add `review_title`, `developer_reply`, `thumbs_up_count`, `verified_purchase` |
| `--countries` | App Store country codes (default: `us`) |

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Config error (bad or placeholder identifier) |
| `2` | Partial failure (some platforms returned nothing) |
| `3` | Total failure (all platforms returned 0 reviews) |
| `130` | Interrupted (SIGINT/SIGTERM) |

## Output Schema

Standard columns (always present): `review_date`, `star_rating`, `reviewer_anonymized`, `review_text`, `platform`

Analysis adds: `sentiment_score` (float, -1 to 1), `sentiment_label` (`good`/`neutral`/`bad`)

Extended (`--extended-fields`): `review_title` (App Store), `developer_reply`, `developer_reply_date`, `thumbs_up_count` (Google Play)

## Running Tests

```bash
pip install pytest
pytest tests/
```

## See Also

- [docs/getting-started.md](docs/getting-started.md) — developer setup, examples, troubleshooting
- [docs/agent-guidelines.md](docs/agent-guidelines.md) — full agent invocation guide
- [docs/configuration.md](docs/configuration.md) — complete flag and env var reference
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — internal scraping architecture
