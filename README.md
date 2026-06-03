# Unified Reviews Scraper

![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)
![pandas](https://img.shields.io/badge/pandas-2.0%2B-150458?logo=pandas&logoColor=white)
![requests](https://img.shields.io/badge/requests-2.32%2B-2C7D6E?logo=python&logoColor=white)
![NLTK](https://img.shields.io/badge/NLTK-VADER_Sentiment-154f3c?logo=python&logoColor=white)
![BeautifulSoup](https://img.shields.io/badge/BeautifulSoup4-HTML_Parsing-4B8BBE?logo=python&logoColor=white)

## Context

### Why This Scraper Exists

Product managers need quick, actionable insights from customer reviews to understand pain points, identify feature requests, and track sentiment trends. However, accessing this data can be challenging:

- **Platform Limitations**: App Store and Google Play don't provide easy ways to export or analyze reviews in bulk
- **API Complexity**: Building proper API integrations requires developer resources, authentication setup, and ongoing maintenance
- **Time Constraints**: Product teams often need insights *today*, not after weeks of dashboard development

This scraper solves these problems by providing a **quick, no-setup solution** to extract and analyze reviews from multiple platforms in minutes. The CSV output can be uploaded directly to an AI model (Claude, ChatGPT, Gemini) for deeper pattern analysis.

### How This Scraper Was Built

All the code was created and optimized using Cursor Agent + Claude Sonnet 4.6.

### Use Cases

- **Discovery**: Quickly understanding what users are saying about your app (when planning the next product iteration, reviewing product ideas, or assessing gaps)
- **Competitor Analysis**: Understanding what users are saying about competing apps
- **Incident Response**: Reviewing how users are reacting to a recent issue or bug
- **Sentiment Analysis**: Generating sentiment analysis for stakeholder meetings

**When to build a proper dashboard instead:**
- You need real-time monitoring with automated alerts
- Your team requires role-based access controls and audit trails
- You want to track trends over months/years with historical data warehousing
- You need to integrate review data with other product metrics (MAU, retention, etc.)

### Benefits

- **Free**: No API usage fees or recurring subscription costs
- **Rapid**: Full configuration and execution within five minutes
- **Cross-platform**: App Store and Google Play Store in one run
- **Sentiment Analysis**: Integrated VADER sentiment scoring (Hugging Face optional)
- **No credentials required**: No API keys or authentication needed
- **Agent-friendly**: CLI flags, structured JSON output, and exit codes for automated use

### Limitations

- **No real-time updates**: Script must be re-run to get fresh data
- **Data completeness**: Web scraping may result in partial data retrieval
- **Maintenance**: Platform changes may break the scraper, requiring code updates
- **Rate limits**: Excessive requests may trigger temporary IP blocks
- **12-month window**: Only retrieves reviews from the past 12 months

**Bottom line**: Useful for quick research and ad-hoc analysis, not a replacement for a production-grade reviews monitoring system.

> **Platform note:** Previous versions of this script also scraped Trustpilot. This was removed in v2 because Trustpilot's DataDome bot detection reliably blocks non-browser HTTP clients, making it return 0 results on every run. App Store and Google Play Store are both fully functional.

---

## Two Ways to Use This Script

### Direct CLI — for developers

Pass flags directly or set environment variables. Full flag reference: [docs/configuration.md](docs/configuration.md).

```bash
python reviews_scraper.py \
  --app-store-id 584606479 \
  --google-play-id com.intuit.quickbooks \
  --app-name quickbooks \
  --output-dir ./output \
  --output-mode analysis
```

### Agent — for AI automation

Use `--quiet` to suppress progress output, `--json-summary` to get a structured result on stdout, and `--dry-run` to validate config before a real run. See [AGENTS.md](AGENTS.md) and [docs/agent-guidelines.md](docs/agent-guidelines.md).

```bash
python reviews_scraper.py [all flags] --quiet --json-summary
```

---

## Setup & Usage

See [docs/getting-started.md](docs/getting-started.md) for setup instructions, common examples, troubleshooting, and tips.

---

## Examples

See the `examples/` folder for QuickBooks output and the exact command used to produce it.

---

## Output Files

Filenames are controlled by `--app-name` (prefix) and `--no-single-file` (per-platform split).

### Single combined file (default: `--single-file`)

| Output mode | File |
|-------------|------|
| `--output-mode reviews` | `{app_name}_reviews.csv` |
| `--output-mode analysis` | `{app_name}_reviews_analysis.csv` |
| `--output-mode both` | both of the above |

### Separate files per platform (`--no-single-file`)

| Output mode | Files |
|-------------|-------|
| `--output-mode reviews` | `{app_name}_app_store_reviews.csv`, `{app_name}_google_play_reviews.csv` |
| `--output-mode analysis` | same pattern with `_analysis` suffix |

Output is written to `--output-dir` (default: current directory).

---

## CSV Format

Standard columns (always present):

| Column | Description |
|--------|-------------|
| `review_date` | Date in YYYY-MM-DD format |
| `star_rating` | Rating from 1–5 |
| `reviewer_anonymized` | Reviewer initials (e.g. `J. D.`) |
| `review_text` | The review content |
| `platform` | `App Store` or `Google Play Store` |

Analysis files also include:

| Column | Description |
|--------|-------------|
| `sentiment_score` | Float from -1.0 (most negative) to 1.0 (most positive) |
| `sentiment_label` | `good`, `neutral`, or `bad` |

Optional extended fields (`--extended-fields`) add: `review_title` (App Store), `developer_reply`, `developer_reply_date`, `thumbs_up_count` (Google Play). See [docs/configuration.md](docs/configuration.md) for details.

---

## Agent Usage

For AI agents automating this script, see [AGENTS.md](AGENTS.md) for the quick-start command and [docs/agent-guidelines.md](docs/agent-guidelines.md) for:

- How to interpret exit codes
- How to parse the `--json-summary` output
- How to handle partial failures
- Rate limiting strategies
- Expected runtimes per platform

---

## Requirements

Required packages (see `requirements.txt`):
- `pandas`, `requests`, `beautifulsoup4`, `lxml`
- `google-play-scraper`, `nltk`, `tqdm`, `python-dateutil`

Optional for Hugging Face sentiment:
- `transformers`, `torch`

---



## Performance

On a typical internet connection with default settings:

| Platform | Speed |
|----------|-------|
| App Store | ~2–5 reviews/second |
| Google Play | ~10–20 reviews/second |

Total time for ~1000 reviews across both platforms: **2–4 minutes**


