# Unified Reviews Scraper

## Context

### Why This Scraper Exists

Product managers need quick, actionable insights from customer reviews to understand pain points, identify feature requests, and track sentiment trends. However, accessing this data can be challenging:

- **Platform Limitations**: App Store and Google Play don't provide easy ways to export or analyze reviews in bulk
- **API Complexity**: Building proper API integrations requires developer resources, authentication setup, and ongoing maintenance
- **Time Constraints**: Product teams often need insights *today*, not after weeks of dashboard development

This scraper solves these problems by providing a **quick, no-setup solution** to extract and analyze reviews from multiple platforms in minutes. We can also upload reviews directly to an AI model (e.g., Claude, ChatGPT, or Gemini) to quickly analyze patterns in reviews to identify issues and opportunities. 

### How This Scraper Was Built

 All the code was created and optimized using Cursor Agent + Claude Sonnet 4.5.  

### Use Cases

- **Discovery**: Quickly understanding what users are saying about your app (e.g., when planning the next product iteration, reviewing product ideas, or assessing gaps).
- **Competitor Analysis**: Quickly understanding what users are saying about competing apps.
- **Incident Response**: Reviewing how users are reacting to a recent issue or bug.
- **Sentiment Analysis**: Generate sentiment analysis for stakeholder meetings.

**When to build a proper dashboard instead:**
- You need real-time monitoring with automated alerts
- Your team requires role-based access controls and audit trails
- You want to track trends over months/years with historical data warehousing
- You need to integrate review data with other product metrics (MAU, retention, etc.)

### Benefits

✅ **Free:** No API usage fees or recurring subscription costs.
✅ **Rapid Implementation:** Full configuration and execution are achievable within five minutes.
✅ **Cross-Platform Reviews:** Unified scraping functionality across App Store, Google Play, and Trustpilot platforms.
✅ **Automated Sentiment Analysis:** Integrated analytical capabilities for immediate identification of sentiment trends and patterns.
✅ **Zero-Configuration Setup:** Operates without API credentials or authentication protocols, enabling immediate deployment.
✅ **Configurable Data Output:** Support for both platform-specific and consolidated reviews to accommodate diverse workflow requirements.

### Limitations

⚠️ **No Real-Time Updates:** Script has to be re-run to get fresh data.
⚠️ **Data Completeness:** Web scraping may result in partial data retrieval.
⚠️ **Maintenance**: Platform changes may break the scraper, requiring updates to the code.
⚠️ **Data Accuracy**: Scraped content may occasionally have formatting issues or missing fields.
⚠️ **Rate Limits**: Excessive requests may trigger rate-limiting protocols, temporarily blocking your IP.
⚠️ **Temporal Data Access:** Retrieval is limited to currently accessible reviews, with no guaranteed access to historical or archived content.

**Bottom line**: This scraper can be helpful for quick research and ad-hoc analysis, but shouldn't replace a production-grade reviews monitoring system for mission-critical use cases.

**Note**
- *reviews_scraper_quickboooks.py* is an example of using reviews_scraper.py to extract App Store, Google Play Store, and Trustpilot reviews for Quickbooks. 
- *quickbooks_reviews_analysis* and *quickbooks_reviews_analysis* are the outputs from running reviews_scraper_quickboooks.py 

---

## Configuration

Edit the configuration section at the top of `reviews_scraper.py`:

### App IDs and URLs
```python
APP_STORE_ID = "123456789"  # Insert your app's App Store ID
GOOGLE_PLAY_ID = "com.example"  # Insert your app's Google Play Store ID
TRUSTPILOT_URL = "https://www.trustpilot.com/review/exampleapp.com"  # Insert your app's Trustpilot URL
```
### Platform Selection
```python
SCRAPE_APP_STORE = True      # Set to False to skip App Store
SCRAPE_GOOGLE_PLAY = True   # Set to False to skip Google Play Store
SCRAPE_TRUSTPILOT = True    # Set to False to skip Trustpilot
```

### Output Options
```python
OUTPUT_REVIEWS_ONLY = False   # Only output raw reviews CSV files
OUTPUT_ANALYSIS_ONLY = False  # Only output analysis CSV files
OUTPUT_BOTH = True           # Output both raw reviews and analysis
SINGLE_FILE = False          # Set to True to combine all reviews into a single CSV file
```

### Scraping Parameters
```python
MAX_PAGES_APP_STORE = 20     # Maximum pages to scrape from App Store
MAX_PAGES_GOOGLE_PLAY = 50   # Maximum pages to scrape from Google Play Store
MAX_PAGES_TRUSTPILOT = 50    # Maximum pages to scrape from Trustpilot
SLEEP_SECONDS = 0.3          # Delay between requests
MAX_RETRIES = 3              # Maximum retry attempts
BACKOFF_BASE = 1.2           # Base delay for retries
MAX_WORKERS = 4              # Number of concurrent workers
REQUEST_TIMEOUT = 10         # Request timeout in seconds
```

## Usage

### Setup
1) Create and activate a virtual environment
```
python -m venv .venv
./.venv/Scripts/Activate.ps1   # PowerShell on Windows
```

2) Install dependencies
```
pip install -r requirements.txt
```


### Scrape And Analyze Reviews
```bash
python reviews_scraper.py
```

### With Environment Variables
```bash
# Use Hugging Face transformers for sentiment analysis (optional)
USE_HF=1 python reviews_scraper.py
```

## Output Files

The scraper generates CSV files based on your configuration:

### Separate Files (SINGLE_FILE = False)
**Raw Reviews Files:**
- `yourapp_app_store_reviews.csv`
- `yourapp_google_play_reviews.csv`
- `yourapp_trustpilot_reviews.csv`

**Analysis Files (with sentiment scores):**
- `yourapp_app_store_reviews_analysis.csv`
- `yourapp_google_play_reviews_analysis.csv`
- `yourapp_trustpilot_reviews_analysis.csv`

### Single Combined Files (SINGLE_FILE = True)
**Raw Reviews File:**
- `yourapp_reviews.csv` (contains all platforms combined)

**Analysis File:**
- `yourapp_reviews_analysis.csv` (contains all platforms with sentiment analysis)

## CSV Format

All CSV files contain these columns:
- `review_date` - Date in YYYY-MM-DD format
- `star_rating` - Rating from 1-5 stars
- `reviewer_anonymized` - Reviewer initials (e.g., "J. D.")
- `review_text` - The review content
- `platform` - Source platform ("App Store", "Google Play Store", or "Trustpilot")

Analysis files additionally include:
- `sentiment_score` - Sentiment score from -1.0 to 1.0
- `sentiment_label` - "good", "neutral", or "bad"

## Requirements

Required packages:
- pandas
- requests
- beautifulsoup4
- lxml
- google-play-scraper
- nltk
- tqdm
- python-dateutil

Optional packages:
- transformers (for Hugging Face sentiment analysis)

## Examples

### Scrape Only App Store Reviews
```python
SCRAPE_APP_STORE = True
SCRAPE_GOOGLE_PLAY = False
SCRAPE_TRUSTPILOT = False
OUTPUT_BOTH = True
```

### Generate Only Analysis Files
```python
OUTPUT_REVIEWS_ONLY = False
OUTPUT_ANALYSIS_ONLY = True
OUTPUT_BOTH = False
```

### Scrape All Platforms, Raw Reviews Only
```python
SCRAPE_APP_STORE = True
SCRAPE_GOOGLE_PLAY = True
SCRAPE_TRUSTPILOT = True
OUTPUT_REVIEWS_ONLY = True
OUTPUT_ANALYSIS_ONLY = False
OUTPUT_BOTH = False
```

### Combine All Platforms Into Single Files
```python
SCRAPE_APP_STORE = True
SCRAPE_GOOGLE_PLAY = True
SCRAPE_TRUSTPILOT = True
OUTPUT_BOTH = True
SINGLE_FILE = True
```

### Single File With Analysis Only
```python
SCRAPE_APP_STORE = True
SCRAPE_GOOGLE_PLAY = True
SCRAPE_TRUSTPILOT = True
OUTPUT_REVIEWS_ONLY = False
OUTPUT_ANALYSIS_ONLY = True
OUTPUT_BOTH = False
SINGLE_FILE = True
```

---

## Troubleshooting

### Common Issues

1. **Configuration validation errors**: 
   - Check that your `APP_STORE_ID` is numeric
   - Verify `GOOGLE_PLAY_ID` follows the format "com.example.app"
   - Ensure `TRUSTPILOT_URL` starts with http:// or https://

2. **No reviews collected**: 
   - Verify the app IDs are correct
   - Check that the apps have reviews on those platforms
   - Ensure the platforms are accessible from your network

3. **Rate limiting**: 
   - Increase `SLEEP_SECONDS` to 0.6 or higher
   - Reduce `MAX_WORKERS` to 2 or 1
   - Try again after waiting 10-15 minutes

4. **Sentiment analysis errors**: 
   - Ensure NLTK data is downloaded (happens automatically)
   - Install transformers if using `USE_HF=1`: `pip install transformers`

5. **Connection timeouts**: 
   - Increase `REQUEST_TIMEOUT` to 20 or 30 seconds
   - Check your internet connection
   - Try running at a different time of day

6. **Scraper hangs or freezes**:
   - Press CTRL+C to safely interrupt and save partial results
   - Check the progress bars for activity
   - Reduce concurrent workers if system resources are low

---

## Performance Notes

### Expected Performance

On a typical internet connection:
- **App Store**: ~2-5 reviews per second
- **Google Play**: ~10-20 reviews per second  
- **Trustpilot**: ~20-30 reviews per second (with concurrent workers)

Total time for 1000 reviews across all platforms: **2-5 minutes**

---

## Tips for Best Results

1. **Start small**: Test with low page limits first to verify configuration
2. **Monitor progress**: Watch the progress bars and review counts
3. **Use CTRL+C freely**: Don't hesitate to interrupt if you have enough data
4. **Upload to AI**: The CSV files work great with Claude, ChatGPT, or other AI tools for deeper analysis
5. **Adjust rate limiting**: If you get blocked, increase `SLEEP_SECONDS` to 0.6 or higher and try again
6. **Check output files**: Always verify the generated CSVs contain expected data

---

## Support

For issues or questions:
1. Check the Troubleshooting section above
2. Verify your configuration is valid
3. Try with a smaller page limit to isolate the issue
4. Check that the platform websites are accessible in your browser
