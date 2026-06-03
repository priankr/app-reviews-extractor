# Examples

This folder contains example output from a real run of `reviews_scraper.py` against QuickBooks.

## Files

| File | Description |
|------|-------------|
| `quickbooks_reviews_analysis.csv` | Combined reviews from App Store and Google Play Store with sentiment analysis (generated with an earlier version that included Trustpilot) |
| `quickbooks_reviews.csv` | Raw reviews without sentiment analysis (if generated separately) |
| `quickbooks_config.py` | The CLI command and env var setup used to produce these files |

## How to reproduce

See `quickbooks_config.py` for the exact command. In short:

```bash
python reviews_scraper.py \
    --app-store-id 584606479 \
    --google-play-id com.intuit.quickbooks \
    --app-name quickbooks \
    --output-dir ./examples \
    --output-mode both \
    --single-file
```

## Output schema

See [docs/configuration.md](../docs/configuration.md) for the full CSV column reference.
