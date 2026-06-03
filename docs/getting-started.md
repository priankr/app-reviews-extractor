# Getting Started

Developer guide for setting up and running `reviews_scraper.py`. For the complete flag reference see [configuration.md](configuration.md). For agent-specific patterns see [agent-guidelines.md](agent-guidelines.md).

---

## Setup

1. Create and activate a virtual environment:

```bash
python -m venv .venv
./.venv/Scripts/Activate.ps1   # PowerShell on Windows
source .venv/bin/activate       # Mac/Linux
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Usage

### Basic run

```bash
python reviews_scraper.py \
  --app-store-id <your_id> \
  --google-play-id <com.your.app> \
  --app-name myapp
```

### Validate config before scraping

```bash
python reviews_scraper.py [all flags] --dry-run
```

Exits `0` if config is valid, `1` if not. Always run this before the first real scrape.

### Scrape and get structured output (for scripting or agents)

```bash
python reviews_scraper.py [all flags] --quiet --json-summary
```

### Common examples

**App Store only, raw reviews:**
```bash
python reviews_scraper.py \
  --app-store-id 584606479 \
  --platform app-store \
  --app-name myapp --output-mode reviews
```

**Both platforms, analysis only, single combined file:**
```bash
python reviews_scraper.py \
  --app-store-id 584606479 \
  --google-play-id com.example.app \
  --app-name myapp --output-mode analysis --single-file
```

**Both platforms, separate files per platform, both raw and analysis:**
```bash
python reviews_scraper.py \
  --app-store-id 584606479 \
  --google-play-id com.example.app \
  --app-name myapp --output-mode both --no-single-file
```

**Multi-country App Store (US, UK, Canada, Australia, India):**
```bash
python reviews_scraper.py \
  --app-store-id 584606479 \
  --platform app-store \
  --countries us gb ca au in \
  --app-name myapp
```

**With extended fields (developer replies, titles, thumbs up):**
```bash
python reviews_scraper.py [all flags] --extended-fields
```

**Use Hugging Face for sentiment instead of VADER:**
```bash
pip install transformers torch
python reviews_scraper.py [all flags] --use-hf
```

### With environment variables

All identifiers and key settings can be set via environment variables instead of flags:

```bash
APP_STORE_ID=584606479 \
GOOGLE_PLAY_ID=com.example.app \
APP_NAME=myapp \
OUTPUT_DIR=./output \
python reviews_scraper.py
```

See [configuration.md](configuration.md) for the complete environment variable list.

---

## Troubleshooting

**Common issues:**

1. **Config validation errors** — placeholder IDs detected (`123456789`, `com.example`). Pass your actual app identifiers via flags or env vars.
2. **No reviews collected** — verify the app IDs are correct and the platforms are accessible from your network.
3. **Rate limiting** — increase `--sleep 0.6`, reduce `--max-workers 2`, wait 10–15 minutes, retry.
4. **Sentiment analysis errors** — NLTK lexicon downloads automatically; for Hugging Face add `pip install transformers torch`.
5. **Connection timeouts** — try `--timeout 20` or check your network.
6. **SSL certificate errors** (`CERTIFICATE_VERIFY_FAILED`) — your network has a corporate SSL proxy. Two options:
   - Quick fix: add `--no-verify-ssl` (disables verification; fine on trusted corporate networks)
   - Better fix: export your proxy's root CA cert and set `REQUESTS_CA_BUNDLE=/path/to/cert.pem`
7. **Scraper hangs** — press CTRL+C to safely interrupt; partial data collected so far will be saved.

---

## Tips

1. **Test with `--dry-run`** before the first real run to catch config errors
2. **Use `--max-pages 5`** for a quick test to verify configuration without scraping everything
3. **Multi-country**: Use `--countries us gb ca au in` for global apps — the US store alone will miss significant review volume
4. **Upload to AI**: The analysis CSV works well with Claude, ChatGPT, or other AI tools for deeper pattern analysis
5. **Interrupted runs**: CTRL+C saves whatever has been collected — useful if you have enough data before the run finishes
