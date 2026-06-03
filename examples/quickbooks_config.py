"""
QuickBooks Example Configuration
=================================
Equivalent CLI command to reproduce the QuickBooks example outputs
in this directory (quickbooks_reviews.csv, quickbooks_reviews_analysis.csv).

Run from the repo root:

    python reviews_scraper.py \
        --app-store-id 584606479 \
        --google-play-id com.intuit.quickbooks \
        --app-name quickbooks \
        --output-dir ./examples \
        --output-mode both \
        --single-file

Or with environment variables:

    APP_STORE_ID=584606479 \
    GOOGLE_PLAY_ID=com.intuit.quickbooks \
    APP_NAME=quickbooks \
    OUTPUT_DIR=./examples \
    OUTPUT_MODE=both \
    python reviews_scraper.py --single-file

Note: if you're on a corporate network with SSL inspection, add --no-verify-ssl.

See docs/configuration.md for the full flag reference.
"""
