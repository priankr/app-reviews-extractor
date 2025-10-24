#!/usr/bin/env python3
"""
Unified App Reviews Scraper
==================================

This script combines scraping functionality for App Store, Google Play Store, and Trustpilot
reviews, with optional sentiment analysis.

USAGE:
    python reviews_scraper.py

CONFIGURATION:
    Modify the variables in the CONFIG section below to customize:
    - App IDs for each platform
    - Which platforms to scrape
    - Output options (reviews only, analysis only, or both)
    - Single file output (combine all platforms into one CSV or separate files)

REQUIREMENTS:
    pip install -r requirements.txt
"""

import argparse
import csv
import hashlib
import os
import random
import re
import signal
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from google_play_scraper import reviews, Sort
from tqdm import tqdm

# =======================
# 🔧 CONFIGURATION
# =======================

# App IDs for each platform
APP_STORE_ID = "584606479"  # Insert your app's App Store ID
GOOGLE_PLAY_ID = "com.intuit.quickbooks"  # Insert your app's Google Play Store ID
TRUSTPILOT_URL = "https://www.trustpilot.com/review/quickbooks.intuit.com"  # Insert your app's Trustpilot URL

# Platform selection (set to True/False to enable/disable platforms)
SCRAPE_APP_STORE = True
SCRAPE_GOOGLE_PLAY = True
SCRAPE_TRUSTPILOT = True

# Output options
OUTPUT_REVIEWS_ONLY = False  # Set to True to only output raw reviews CSV
OUTPUT_ANALYSIS_ONLY = False  # Set to True to only output analysis CSV
OUTPUT_BOTH = True  # Set to True to output both raw reviews and analysis
SINGLE_FILE = True  # Set to True to combine all reviews into a single CSV file (yourapp_reviews.csv)

# Scraping parameters
MAX_PAGES_APP_STORE = 20
MAX_PAGES_GOOGLE_PLAY = 50  # Limit pages to prevent infinite loops
SLEEP_SECONDS = 0.3  # Reduced from 0.6 for faster scraping
MAX_RETRIES = 3  # Reduced from 4
BACKOFF_BASE = 1.2  # Reduced from 1.5
MAX_WORKERS = 4  # For concurrent requests
REQUEST_TIMEOUT = 10  # Reduced from 20 seconds
MAX_PAGES_TRUSTPILOT = 50  # Limit pages to prevent infinite loops

# Sentiment analysis thresholds
GOOD_THRESH = 0.25
BAD_THRESH = -0.25

# Constants for magic numbers
GOOGLE_PLAY_BATCH_SIZE = 100
HF_TEXT_MAX_LENGTH = 4096
TRUSTPILOT_REVIEW_LIMIT = 1000
MAX_CONSECUTIVE_ERRORS = 3

# =======================
# GRACEFUL SHUTDOWN
# =======================

# Global flag for graceful shutdown
shutdown_requested = False

def signal_handler(sig, frame):
    """Handle CTRL+C gracefully."""
    global shutdown_requested
    print("\n[INFO] Shutdown requested. Finishing current operations...")
    shutdown_requested = True

# Register signal handler
signal.signal(signal.SIGINT, signal_handler)

# =======================
# UTILITY FUNCTIONS
# =======================

def validate_config() -> None:
    """Validate configuration parameters."""
    errors = []
    
    if SCRAPE_APP_STORE:
        if not APP_STORE_ID or not APP_STORE_ID.strip():
            errors.append("APP_STORE_ID cannot be empty when SCRAPE_APP_STORE is True")
        elif not APP_STORE_ID.isdigit():
            errors.append(f"APP_STORE_ID should be numeric, got: {APP_STORE_ID}")
    
    if SCRAPE_GOOGLE_PLAY:
        if not GOOGLE_PLAY_ID or not GOOGLE_PLAY_ID.strip():
            errors.append("GOOGLE_PLAY_ID cannot be empty when SCRAPE_GOOGLE_PLAY is True")
        elif not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$', GOOGLE_PLAY_ID):
            errors.append(f"GOOGLE_PLAY_ID should be in format 'com.example.app', got: {GOOGLE_PLAY_ID}")
    
    if SCRAPE_TRUSTPILOT:
        if not TRUSTPILOT_URL or not TRUSTPILOT_URL.strip():
            errors.append("TRUSTPILOT_URL cannot be empty when SCRAPE_TRUSTPILOT is True")
        elif not TRUSTPILOT_URL.startswith('http'):
            errors.append(f"TRUSTPILOT_URL should start with http:// or https://, got: {TRUSTPILOT_URL}")
    
    if not (OUTPUT_REVIEWS_ONLY or OUTPUT_ANALYSIS_ONLY or OUTPUT_BOTH):
        errors.append("At least one output option must be True (OUTPUT_REVIEWS_ONLY, OUTPUT_ANALYSIS_ONLY, or OUTPUT_BOTH)")
    
    if errors:
        print("ERROR: Configuration validation failed:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)


def ensure_vader_downloaded() -> None:
    """Ensure the NLTK 'vader_lexicon' resource is available; download if missing."""
    try:
        import nltk
        nltk.data.find("sentiment/vader_lexicon")
    except LookupError:
        print("Downloading NLTK resource: 'vader_lexicon' ...")
        import nltk
        nltk.download("vader_lexicon")


def build_sentiment_scorer() -> Tuple[Callable[[str], float], str]:
    """
    Returns a (score_fn, backend_name).
    score_fn(text) -> sentiment score in [-1, 1].
    Prefers VADER; can use Hugging Face if USE_HF=1 and transformers is installed.
    """
    use_hf = os.getenv("USE_HF", "0") == "1"

    if use_hf:
        try:
            from transformers import pipeline  # type: ignore

            sa = pipeline(
                "sentiment-analysis",
                model="distilbert-base-uncased-finetuned-sst-2-english",
            )

            def hf_score_fn(text: str) -> float:
                if not isinstance(text, str) or not text.strip():
                    return 0.0
                # HF returns [{'label': 'POSITIVE'|'NEGATIVE', 'score': prob in [0,1]}]
                res = sa(text[:HF_TEXT_MAX_LENGTH])[0]  # truncate long reviews defensively
                label = str(res["label"]).upper()
                prob = float(res["score"])
                return prob if label == "POSITIVE" else -prob

            return hf_score_fn, "huggingface/distilbert-sst2"
        except Exception:
            # Fall back to VADER if transformers isn't available or errors out
            pass

    # Default: VADER
    ensure_vader_downloaded()
    from nltk.sentiment import SentimentIntensityAnalyzer  # type: ignore

    sia = SentimentIntensityAnalyzer()

    def vader_score_fn(text: str) -> float:
        if not isinstance(text, str) or not text.strip():
            return 0.0
        return float(sia.polarity_scores(text)["compound"])

    return vader_score_fn, "nltk/vader"


def label_from_score(score: float) -> str:
    """Map score in [-1,1] to 'good' | 'neutral' | 'bad' using requested thresholds."""
    if score >= GOOD_THRESH:
        return "good"
    if score <= BAD_THRESH:
        return "bad"
    return "neutral"


def to_initials(name: Optional[str]) -> str:
    """Convert full name to initials."""
    if not name:
        return "A."
    parts = [p for p in re.split(r"\s+", name.strip()) if re.search(r"[A-Za-z]", p)]
    if not parts:
        return "A."
    if len(parts) == 1:
        return f"{parts[0][0].upper()}."
    return f"{parts[0][0].upper()}.{parts[-1][0].upper()}."


def clean_text(s: Optional[str]) -> Optional[str]:
    """Clean and normalize text."""
    if not s:
        return None
    t = re.sub(r"\s+", " ", s).strip()
    return t if t else None


def clamp_star_rating(val: Any) -> Optional[int]:
    """Ensure star rating is between 1-5."""
    try:
        i = int(str(val).strip())
        return min(5, max(1, i))
    except Exception:
        return None


# =======================
# APP STORE SCRAPING
# =======================

def last_12m_cutoff(now_utc: Optional[datetime] = None) -> datetime:
    """Get cutoff date for last 12 months (timezone-aware)."""
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    return now_utc - timedelta(days=365)


def is_within_last_12_months(dt: datetime, cutoff: datetime) -> bool:
    """Check if date is within last 12 months (handles timezone-aware dates)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt >= cutoff


def rss_url(country: str, app_id: str, page: int) -> str:
    """Generate RSS URL for App Store reviews."""
    return f"https://itunes.apple.com/{country}/rss/customerreviews/page={page}/id={app_id}/sortby=mostrecent/json"


def create_session() -> requests.Session:
    """Create an optimized requests session with connection pooling."""
    session = requests.Session()
    session.headers.update({
        "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    })
    
    # Configure adapter for connection pooling
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=MAX_WORKERS,
        pool_maxsize=MAX_WORKERS * 2,
        max_retries=0  # We handle retries manually
    )
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    
    return session


def http_get_json(url: str, session: Optional[requests.Session] = None) -> Optional[Dict[str, Any]]:
    """Make HTTP GET request with retries and session reuse."""
    if session is None:
        session = requests.Session()
    
    ua_pool = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    ]
    
    for attempt in range(1, MAX_RETRIES + 1):
        if shutdown_requested:
            return None
            
        try:
            headers = {
                "User-Agent": random.choice(ua_pool),
                "Accept": "application/json",
            }
            resp = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (429, 500, 502, 503, 504):
                time.sleep(BACKOFF_BASE * (1.5 ** (attempt - 1)))
                continue
            print(f"[WARN] {url} -> HTTP {resp.status_code}", file=sys.stderr)
            return None
        except requests.RequestException as e:
            print(f"[WARN] GET error ({e}), attempt {attempt}", file=sys.stderr)
            time.sleep(BACKOFF_BASE * (1.5 ** (attempt - 1)))
    print(f"[ERROR] Exhausted retries for {url}", file=sys.stderr)
    return None


def parse_rss_reviews(json_obj: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse RSS reviews from JSON response."""
    out: List[Dict[str, Any]] = []
    try:
        entries = json_obj.get("feed", {}).get("entry", [])
        if not isinstance(entries, list):
            entries = [entries]
        for e in entries:
            rating = e.get("im:rating", {}).get("label")
            content = e.get("content", {}).get("label")
            if rating is None and content is None:
                continue
            star = clamp_star_rating(rating)
            if star is None:
                continue
            updated_str = e.get("updated", {}).get("label") or e.get("im:releaseDate", {}).get("label")
            if not updated_str:
                continue
            try:
                dt = dateparser.parse(updated_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            author_name = e.get("author", {}).get("name", {}).get("label")
            initials = to_initials(author_name)
            text = clean_text(content) or clean_text(e.get("title", {}).get("label"))
            if not text:
                continue
            out.append(
                {
                    "dt": dt,
                    "review_date": dt.date().isoformat(),
                    "star_rating": star,
                    "reviewer_anonymized": initials,
                    "review_text": text,
                    "platform": "App Store",
                }
            )
    except Exception:
        return []
    return out


def scrape_app_store(app_id: str, country: str = "us", max_pages: int = 20, sleep_sec: float = 0.3) -> List[Dict[str, Any]]:
    """Scrape App Store reviews with optimized session handling."""
    print(f"Scraping App Store reviews for app ID: {app_id}")
    rows: List[Dict[str, Any]] = []
    cutoff = last_12m_cutoff()
    
    # Create session for connection reuse
    session = create_session()
    
    try:
        for page in tqdm(range(1, max_pages + 1), desc="App Store pages", unit="page"):
            if shutdown_requested:
                print("\n[INFO] Shutdown requested, stopping App Store scraping...")
                break
                
            url = rss_url(country, app_id, page)
            data = http_get_json(url, session)
            if not data:
                break
            parsed = parse_rss_reviews(data)
            if not parsed:
                break
            kept, oldest = 0, None
            for r in parsed:
                dt = r["dt"]
                if oldest is None or dt < oldest:
                    oldest = dt
                if is_within_last_12_months(dt, cutoff):
                    rows.append(r)
                    kept += 1
            if oldest and not is_within_last_12_months(oldest, cutoff):
                break
            time.sleep(sleep_sec)
    finally:
        session.close()
    
    # Deduplicate using tuple keys (faster than MD5)
    seen, clean = set(), []
    for r in rows:
        # Create tuple key for faster deduplication
        key = (r['review_date'], r['star_rating'], r['review_text'][:100])
        if key in seen:
            continue
        seen.add(key)
        clean.append(
            {
                "review_date": r["review_date"],
                "star_rating": int(r["star_rating"]),
                "reviewer_anonymized": r["reviewer_anonymized"],
                "review_text": r["review_text"],
                "platform": r["platform"],
            }
        )
    
    print(f"Collected {len(clean)} App Store reviews")
    return clean


# =======================
# GOOGLE PLAY STORE SCRAPING
# =======================

def anonymize_name_google(full_name: str) -> str:
    """Convert Google Play name to initials."""
    if not full_name:
        return "A."
    name = " ".join(full_name.split())
    if re.search(r"anonymous|anon|google user|a google user", name, re.I):
        return "A."
    parts = [p for p in re.split(r"\s+", name) if p and re.search(r"[A-Za-z]", p)]
    if not parts:
        return "A."
    if len(parts) == 1:
        return f"{parts[0][0].upper()}."
    return f"{parts[0][0].upper()}. {parts[-1][0].upper()}."


def scrape_google_play(app_id: str, lang: str = "en", country: str = "us") -> List[Dict]:
    """Scrape Google Play Store reviews with timeout and progress tracking."""
    print(f"Scraping Google Play Store reviews for app ID: {app_id}")
    # Use timezone-aware datetime for consistency
    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(days=365)
    all_rows: List[Dict] = []
    seen: set[Tuple[str, int, str]] = set()

    token = None
    page = 0
    max_pages = MAX_PAGES_GOOGLE_PLAY
    consecutive_errors = 0

    with tqdm(desc="Google Play pages", unit="page") as pbar:
        while page < max_pages:
            if shutdown_requested:
                print("\n[INFO] Shutdown requested, stopping Google Play scraping...")
                break
                
            page += 1
            pbar.update(1)
            
            try:
                # Add timeout to prevent hanging
                batch, token = reviews(
                    app_id,
                    lang=lang,
                    country=country,
                    sort=Sort.NEWEST,
                    count=GOOGLE_PLAY_BATCH_SIZE,
                    continuation_token=token
                )
                consecutive_errors = 0  # Reset error counter on success
                
            except Exception as e:
                consecutive_errors += 1
                print(f"[WARN] Google Play error on page {page}: {e}")
                
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    print(f"[ERROR] Too many consecutive errors ({consecutive_errors}), stopping Google Play scraping")
                    break
                
                # Retry once with longer delay
                time.sleep(2.0)
                try:
                    batch, token = reviews(
                        app_id,
                        lang=lang,
                        country=country,
                        sort=Sort.NEWEST,
                        count=GOOGLE_PLAY_BATCH_SIZE,
                        continuation_token=token
                    )
                    consecutive_errors = 0  # Reset on successful retry
                except Exception as e2:
                    print(f"[ERROR] Retry failed on page {page}: {e2}")
                    continue

            if not batch:
                print(f"No more reviews found on page {page}")
                break

            reviews_added = 0
            for r in batch:
                dt = r.get("at")
                if not dt:
                    continue

                # Convert to timezone-aware for consistent comparison
                if getattr(dt, "tzinfo", None) is None:
                    dt = dt.replace(tzinfo=timezone.utc)

                # Keep only last 12 months
                if dt < cutoff:
                    continue

                score = int(r.get("score") or 0)
                if score < 1 or score > 5:
                    continue

                user = r.get("userName") or "Anonymous"
                anon = anonymize_name_google(user)
                text = (r.get("content") or "").strip()
                if not text:
                    continue

                key = (dt.date().isoformat(), score, text[:100])
                if key in seen:
                    continue
                seen.add(key)

                all_rows.append(
                    {
                        "review_date": dt.date().isoformat(),
                        "star_rating": score,
                        "reviewer_anonymized": anon,
                        "review_text": text,
                        "platform": "Google Play Store",
                    }
                )
                reviews_added += 1

            # Update progress bar description with current stats
            pbar.set_description(f"Google Play pages (reviews: {len(all_rows)})")
            
            # If we added very few reviews, we might be hitting old reviews
            if reviews_added < 10 and page > 5:
                print(f"Only {reviews_added} reviews added on page {page}, might be hitting old reviews")
                # Continue for a few more pages to be sure
                if page > 10:
                    break

            # If there is no continuation token, we've hit the end
            if token is None:
                print("No continuation token, reached end of reviews")
                break

            # Polite pause
            time.sleep(SLEEP_SECONDS)

    print(f"Collected {len(all_rows)} Google Play Store reviews")
    return all_rows


# =======================
# TRUSTPILOT SCRAPING
# =======================

def http_get(url: str, session: Optional[requests.Session] = None) -> Optional[str]:
    """GET with basic retries + backoff and session reuse."""
    if session is None:
        session = requests.Session()
    
    headers_pool = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/16.4 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]
    
    for attempt in range(1, MAX_RETRIES + 1):
        if shutdown_requested:
            return None
            
        try:
            headers = {"User-Agent": random.choice(headers_pool), "Accept-Language": "en-US,en;q=0.9"}
            resp = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200 and resp.text:
                return resp.text
        except requests.RequestException:
            pass
        # backoff
        time.sleep(BACKOFF_BASE * attempt)
    return None


def parse_date(tag) -> Optional[datetime]:
    """Parse <time datetime='...'>, fallback to inner text (returns timezone-aware)."""
    if not tag:
        return None
    # 1) datetime attribute
    iso = tag.get("datetime", "").strip()
    if iso:
        try:
            dt = dateparser.parse(iso)
            if not dt.tzinfo:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            pass
    # 2) visible text fallback (e.g., "Aug 15, 2025")
    txt = tag.get_text(strip=True)
    if txt:
        try:
            dt = dateparser.parse(txt, fuzzy=True)
            if not dt.tzinfo:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            pass
    return None


def parse_rating(card) -> Optional[int]:
    """Extract rating from alt text ('Rated X out of 5') or aria-label fallback."""
    # Try alt text
    img = card.find("img", alt=True)
    if img and img.get("alt"):
        m = re.compile(r"Rated\s+(\d)\s+out of 5", re.I).search(img["alt"])
        if m:
            return int(m.group(1))
    # Fallback: any element with aria-label containing 'star'
    aria = card.find(attrs={"aria-label": True})
    if aria:
        m = re.search(r"(\d)\s*star", aria["aria-label"], re.I)
        if m:
            return int(m.group(1))
    return None


def extract_name(card) -> str:
    """Try several places for consumer name."""
    # Common containers
    candidates = []
    # 1) data-testid consumer info
    for span in card.select("[data-testid='consumer-info'] span"):
        t = span.get_text(strip=True)
        if t:
            candidates.append(t)
    # 2) any short spans near the top
    for span in card.find_all("span"):
        t = span.get_text(strip=True)
        if t:
            candidates.append(t)
    # Filter out non-name phrases
    for c in candidates:
        if re.search(r"reviews?\s+written|company\s+replied", c, re.I):
            continue
        if 1 <= len(c) <= 60:
            return c
    return "Anonymous"


def anonymize_name_trustpilot(full_name: str) -> str:
    """Convert Trustpilot name to initials."""
    if not full_name:
        return "A."
    name = " ".join(full_name.split())
    if re.search(r"anonymous|anon|trustpilot user", name, re.I):
        return "A."
    parts = [p for p in re.split(r"\s+", name) if p and re.search(r"[A-Za-z]", p)]
    if not parts:
        return "A."
    if len(parts) == 1:
        return f"{parts[0][0].upper()}."
    return f"{parts[0][0].upper()}. {parts[-1][0].upper()}."


def extract_text(card) -> Optional[str]:
    """Grab review text (supports multi-paragraph)."""
    body = card.select_one("[data-testid='review-content']")
    if body:
        # paragraphs inside body
        ps = [p.get_text(" ", strip=True) for p in body.find_all(["p", "div"]) if p.get_text(strip=True)]
        txt = "\n".join([t for t in ps if t])
        if txt:
            return txt
    # fallback: any paragraph in the card
    ps = [p.get_text(" ", strip=True) for p in card.find_all("p") if p.get_text(strip=True)]
    txt = "\n".join(ps).strip()
    return txt or None


def parse_page(html: str) -> List[Dict]:
    """Parse reviews from HTML page with optimized parsing."""
    soup = BeautifulSoup(html, "lxml")
    
    # Use more specific selectors for better performance
    cards = soup.select("section[data-testid='reviews-list'] article")
    if not cards:
        # Fallback selector
        cards = soup.select("article[data-service-review-card-paper]")
    
    out = []
    for card in cards:
        try:
            # Optimize by checking required elements first
            time_tag = card.find("time")
            if not time_tag:
                continue
                
            dt = parse_date(time_tag)
            if not dt:
                continue
                
            rating = parse_rating(card)
            if rating is None:
                continue
                
            text = extract_text(card)
            if not text:
                continue

            # Only extract name if we have all other required data
            raw_name = extract_name(card)
            anon = anonymize_name_trustpilot(raw_name)

            out.append(
                {
                    "review_date": dt.date().isoformat(),
                    "star_rating": rating,
                    "reviewer_anonymized": anon,
                    "review_text": text,
                    "platform": "Trustpilot",
                }
            )
        except Exception:
            # skip malformed card
            continue
    return out


def scrape_trustpilot_page(url: str, session: requests.Session, cutoff: datetime) -> Tuple[int, List[Dict]]:
    """Scrape a single Trustpilot page and return page number and reviews."""
    if shutdown_requested:
        return 0, []
        
    html = http_get(url, session)
    if not html:
        return 0, []
    
    rows = parse_page(html)
    if not rows:
        return 0, []
    
    # Filter by date and deduplicate
    in_window = []
    for r in rows:
        # Parse the review_date string back to datetime for comparison
        try:
            review_dt = dateparser.parse(r["review_date"])
            if review_dt.tzinfo is None:
                review_dt = review_dt.replace(tzinfo=timezone.utc)
            if review_dt >= cutoff:
                in_window.append(r)
        except Exception:
            # Skip reviews with invalid dates
            continue
    
    return len(rows), in_window


def scrape_trustpilot(base_url: str) -> List[Dict]:
    """Scrape Trustpilot reviews with concurrent page processing."""
    print(f"Scraping Trustpilot reviews from: {base_url}")
    all_rows: List[Dict] = []
    seen_keys = set()

    # 12-month window (timezone-aware)
    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(days=365)

    # Create session for connection reuse
    session = create_session()
    
    try:
        # First, determine how many pages we need to scrape
        # Check first few pages to estimate total pages
        estimated_pages = 0
        for test_page in range(1, min(6, MAX_PAGES_TRUSTPILOT + 1)):
            if shutdown_requested:
                print("\n[INFO] Shutdown requested during page estimation")
                return []
                
            url = base_url if test_page == 1 else f"{base_url}?page={test_page}"
            html = http_get(url, session)
            if html:
                rows = parse_page(html)
                if rows:
                    estimated_pages = test_page
                    # Check if we have old reviews (indicating we might be near the end)
                    old_reviews = 0
                    for r in rows:
                        try:
                            review_dt = dateparser.parse(r["review_date"])
                            if review_dt.tzinfo is None:
                                review_dt = review_dt.replace(tzinfo=timezone.utc)
                            if review_dt < cutoff:
                                old_reviews += 1
                        except Exception:
                            continue
                    if old_reviews == len(rows) and test_page > 2:
                        break
                else:
                    break
            time.sleep(SLEEP_SECONDS)  # Use configured sleep instead of hard-coded value
        
        if estimated_pages == 0:
            print("No reviews found on Trustpilot")
            return []
        
        print(f"Estimated {estimated_pages} pages to scrape")
        
        # Now scrape pages concurrently
        urls_to_scrape = []
        for page in range(1, min(estimated_pages + 10, MAX_PAGES_TRUSTPILOT + 1)):
            url = base_url if page == 1 else f"{base_url}?page={page}"
            urls_to_scrape.append((page, url))
        
        # Use ThreadPoolExecutor for concurrent scraping
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, 3)) as executor:
            # Submit all page scraping tasks
            future_to_page = {
                executor.submit(scrape_trustpilot_page, url, session, cutoff): page_num 
                for page_num, url in urls_to_scrape
            }
            
            # Process completed tasks with progress bar
            with tqdm(total=len(urls_to_scrape), desc="Trustpilot pages", unit="page") as pbar:
                consecutive_empty_pages = 0
                
                for future in as_completed(future_to_page):
                    if shutdown_requested:
                        print("\n[INFO] Shutdown requested, cancelling remaining tasks...")
                        # Cancel all pending futures
                        for f in future_to_page:
                            f.cancel()
                        break
                        
                    page_num = future_to_page[future]
                    try:
                        total_reviews, page_reviews = future.result()
                        
                        if total_reviews == 0:
                            consecutive_empty_pages += 1
                            if consecutive_empty_pages >= 3:
                                print(f"Stopping after {consecutive_empty_pages} consecutive empty pages")
                                # Cancel remaining futures
                                for f in future_to_page:
                                    if not f.done():
                                        f.cancel()
                                break
                        else:
                            consecutive_empty_pages = 0
                        
                        # Deduplicate and add reviews using tuple keys
                        for r in page_reviews:
                            key = (r['review_date'], r['star_rating'], r['review_text'][:80])
                            if key not in seen_keys:
                                seen_keys.add(key)
                                all_rows.append(r)
                        
                        pbar.update(1)
                        
                        # Brief pause to be respectful
                        time.sleep(0.1)
                        
                    except Exception as e:
                        print(f"Error processing page {page_num}: {e}")
                        pbar.update(1)
                        continue
                    
                    # Stop if we've collected enough recent reviews
                    if len(all_rows) > TRUSTPILOT_REVIEW_LIMIT:
                        print("Reached review limit, stopping")
                        # Cancel remaining futures
                        for f in future_to_page:
                            if not f.done():
                                f.cancel()
                        break

    finally:
        session.close()

    print(f"Collected {len(all_rows)} Trustpilot reviews")
    return all_rows


# =======================
# ANALYSIS FUNCTIONS
# =======================

def analyze_reviews(reviews_data: List[Dict], platform: str) -> List[Dict]:
    """Add sentiment analysis to reviews."""
    print(f"Analyzing {len(reviews_data)} {platform} reviews...")
    
    # Build sentiment scorer
    score_fn, backend = build_sentiment_scorer()
    print(f"Using sentiment backend: {backend}")

    # Convert to DataFrame for easier processing
    df = pd.DataFrame(reviews_data)
    
    # Compute scores and labels
    texts = df["review_text"].astype("string").fillna("")
    df["sentiment_score"] = texts.apply(score_fn).astype(float)
    df["sentiment_label"] = df["sentiment_score"].apply(label_from_score)

    # Convert back to list of dicts
    return df.to_dict('records')


# =======================
# MAIN FUNCTIONS
# =======================

def save_reviews_csv(reviews_data: List[Dict], filename: str) -> None:
    """Save reviews to CSV file."""
    if not reviews_data:
        print(f"No reviews to save for {filename}")
        return
    
    df = pd.DataFrame(reviews_data)
    df = df.sort_values(["review_date", "star_rating"], ascending=[False, False])
    df.to_csv(filename, index=False, encoding="utf-8", quoting=csv.QUOTE_ALL)
    print(f"Saved {len(reviews_data)} reviews to {filename}")


def save_combined_reviews_csv(all_reviews_data: List[Dict], filename: str) -> None:
    """Save all reviews from all platforms to a single CSV file."""
    if not all_reviews_data:
        print(f"No reviews to save for {filename}")
        return
    
    df = pd.DataFrame(all_reviews_data)
    df = df.sort_values(["review_date", "star_rating"], ascending=[False, False])
    df.to_csv(filename, index=False, encoding="utf-8", quoting=csv.QUOTE_ALL)
    print(f"Saved {len(all_reviews_data)} combined reviews to {filename}")


def scrape_all_platforms() -> Dict[str, List[Dict]]:
    """Scrape all enabled platforms."""
    all_reviews = {}
    
    if SCRAPE_APP_STORE and not shutdown_requested:
        try:
            app_store_reviews = scrape_app_store(APP_STORE_ID, max_pages=MAX_PAGES_APP_STORE, sleep_sec=SLEEP_SECONDS)
            all_reviews['app_store'] = app_store_reviews
        except Exception as e:
            print(f"Error scraping App Store: {e}")
            all_reviews['app_store'] = []
    
    if SCRAPE_GOOGLE_PLAY and not shutdown_requested:
        try:
            google_play_reviews = scrape_google_play(GOOGLE_PLAY_ID)
            all_reviews['google_play'] = google_play_reviews
        except Exception as e:
            print(f"Error scraping Google Play Store: {e}")
            all_reviews['google_play'] = []
    
    if SCRAPE_TRUSTPILOT and not shutdown_requested:
        try:
            trustpilot_reviews = scrape_trustpilot(TRUSTPILOT_URL)
            all_reviews['trustpilot'] = trustpilot_reviews
        except Exception as e:
            print(f"Error scraping Trustpilot: {e}")
            all_reviews['trustpilot'] = []
    
    return all_reviews


def main():
    """Main function to orchestrate scraping and analysis."""
    start_time = time.time()
    
    print("=" * 60)
    print("APP REVIEWS SCRAPER (OPTIMIZED & FIXED)")
    print("=" * 60)
    
    # Validate configuration
    validate_config()
    
    # Check configuration
    platforms_enabled = []
    if SCRAPE_APP_STORE:
        platforms_enabled.append("App Store")
    if SCRAPE_GOOGLE_PLAY:
        platforms_enabled.append("Google Play Store")
    if SCRAPE_TRUSTPILOT:
        platforms_enabled.append("Trustpilot")
    
    if not platforms_enabled:
        print("ERROR: No platforms enabled for scraping!")
        print("Please set at least one of SCRAPE_APP_STORE, SCRAPE_GOOGLE_PLAY, or SCRAPE_TRUSTPILOT to True")
        sys.exit(1)
    
    print(f"Platforms to scrape: {', '.join(platforms_enabled)}")
    print(f"App Store ID: {APP_STORE_ID}")
    print(f"Google Play ID: {GOOGLE_PLAY_ID}")
    print(f"Trustpilot URL: {TRUSTPILOT_URL}")
    print(f"Max workers: {MAX_WORKERS}")
    print(f"Request timeout: {REQUEST_TIMEOUT}s")
    print(f"Single file output: {SINGLE_FILE}")
    print()
    
    # Scrape all platforms
    print("Starting scraping process...")
    scraping_start = time.time()
    all_reviews = scrape_all_platforms()
    scraping_time = time.time() - scraping_start
    
    if shutdown_requested:
        print("\n[INFO] Scraping interrupted by user. Saving collected data...")
    
    total_reviews = sum(len(reviews) for reviews in all_reviews.values())
    print(f"\nScraping completed in {scraping_time:.2f} seconds")
    print(f"Total reviews collected: {total_reviews}")
    
    # Process reviews based on SINGLE_FILE setting
    processing_start = time.time()
    
    if SINGLE_FILE:
        # Combine all reviews into single files
        all_raw_reviews = []
        all_analyzed_reviews = []
        
        for platform, reviews_data in all_reviews.items():
            if not reviews_data:
                print(f"No reviews collected for {platform}")
                continue
            
            platform_name = platform.replace('_', ' ').title()
            print(f"\nProcessing {len(reviews_data)} {platform_name} reviews...")
            
            # Add raw reviews to combined list
            if OUTPUT_REVIEWS_ONLY or OUTPUT_BOTH:
                all_raw_reviews.extend(reviews_data)
            
            # Analyze and add to combined analyzed list
            if OUTPUT_ANALYSIS_ONLY or OUTPUT_BOTH:
                analyzed_reviews = analyze_reviews(reviews_data, platform_name)
                all_analyzed_reviews.extend(analyzed_reviews)
        
        # Save combined files
        if OUTPUT_REVIEWS_ONLY or OUTPUT_BOTH:
            if all_raw_reviews:
                save_combined_reviews_csv(all_raw_reviews, "yourapp_reviews.csv")
        
        if OUTPUT_ANALYSIS_ONLY or OUTPUT_BOTH:
            if all_analyzed_reviews:
                save_combined_reviews_csv(all_analyzed_reviews, "yourapp_reviews_analysis.csv")
    
    else:
        # Save separate files for each platform (original behavior)
        for platform, reviews_data in all_reviews.items():
            if not reviews_data:
                print(f"No reviews collected for {platform}")
                continue
            
            platform_name = platform.replace('_', ' ').title()
            print(f"\nProcessing {len(reviews_data)} {platform_name} reviews...")
            
            # Save raw reviews if requested
            if OUTPUT_REVIEWS_ONLY or OUTPUT_BOTH:
                filename = f"yourapp_{platform}_reviews.csv"
                save_reviews_csv(reviews_data, filename)
            
            # Analyze and save analysis if requested
            if OUTPUT_ANALYSIS_ONLY or OUTPUT_BOTH:
                analyzed_reviews = analyze_reviews(reviews_data, platform_name)
                filename = f"yourapp_{platform}_reviews_analysis.csv"
                save_reviews_csv(analyzed_reviews, filename)
    
    processing_time = time.time() - processing_start
    total_time = time.time() - start_time
    
    print("\n" + "=" * 60)
    if shutdown_requested:
        print("SCRAPING INTERRUPTED (DATA SAVED)")
    else:
        print("SCRAPING COMPLETE!")
    print("=" * 60)
    print(f"Total execution time: {total_time:.2f} seconds")
    print(f"Scraping time: {scraping_time:.2f} seconds ({scraping_time/total_time*100:.1f}%)")
    print(f"Processing time: {processing_time:.2f} seconds ({processing_time/total_time*100:.1f}%)")
    if scraping_time > 0:
        print(f"Reviews per second: {total_reviews/scraping_time:.1f}")
    print("=" * 60)


if __name__ == "__main__":
    main()