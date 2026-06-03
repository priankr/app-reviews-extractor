#!/usr/bin/env python3
"""
Unified App Reviews Scraper
==================================

Scrapes App Store and Google Play Store reviews with optional sentiment analysis.
Supports direct CLI use and agent invocation.

Note: Trustpilot support was removed in v2 because DataDome bot detection reliably
blocks non-browser HTTP clients. See README.md for details.

USAGE (CLI):
    python reviews_scraper.py \\
        --app-store-id 123456789 \\
        --google-play-id com.example.app \\
        --app-name myapp --output-dir ./output --output-mode analysis

USAGE (Agent):
    python reviews_scraper.py [flags] --quiet --json-summary

See docs/configuration.md for the full flag and environment variable reference.
See AGENTS.md for agent-specific invocation guidance.

REQUIREMENTS:
    pip install -r requirements.txt
"""

import argparse
import csv
import dataclasses
import hashlib
import json
import logging
import os
import random
import re
import signal
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import certifi
    _SSL_VERIFY: object = certifi.where()
except ImportError:
    _SSL_VERIFY = True  # Fall back to default if certifi not installed
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from google_play_scraper import reviews, Sort
from tqdm import tqdm

# =======================
# CONFIGURATION DEFAULTS
# =======================
# These are defaults only. All values can be overridden via CLI flags or
# environment variables. See docs/configuration.md for the full reference.

APP_STORE_ID = "123456789"
GOOGLE_PLAY_ID = "com.example"

SCRAPE_APP_STORE = True
SCRAPE_GOOGLE_PLAY = True

OUTPUT_REVIEWS_ONLY = False
OUTPUT_ANALYSIS_ONLY = True
OUTPUT_BOTH = False
SINGLE_FILE = True

MAX_PAGES_APP_STORE = 20
MAX_PAGES_GOOGLE_PLAY = 50
SLEEP_SECONDS = 0.3
MAX_RETRIES = 3
BACKOFF_BASE = 1.2
MAX_WORKERS = 4
REQUEST_TIMEOUT = 10

GOOD_THRESH = 0.25
BAD_THRESH = -0.25

GOOGLE_PLAY_BATCH_SIZE = 100
HF_TEXT_MAX_LENGTH = 4096
MAX_CONSECUTIVE_ERRORS = 3

_PLACEHOLDER_APP_STORE_ID = "123456789"
_PLACEHOLDER_GOOGLE_PLAY_ID = "com.example"

EXIT_SUCCESS = 0
EXIT_CONFIG_ERROR = 1
EXIT_PARTIAL_FAILURE = 2
EXIT_TOTAL_FAILURE = 3
EXIT_INTERRUPTED = 130

# Synced from Config in main(); used by scraping functions to suppress tqdm.
_QUIET = False

# =======================
# CONFIG DATACLASS
# =======================

@dataclasses.dataclass
class Config:
    app_store_id: str = APP_STORE_ID
    google_play_id: str = GOOGLE_PLAY_ID
    platforms: List[str] = dataclasses.field(
        default_factory=lambda: ["app-store", "google-play"]
    )
    app_name: str = "yourapp"
    output_dir: str = "."
    output_mode: str = "analysis"
    single_file: bool = True
    json_summary: bool = False
    extended_fields: bool = False
    max_pages_app_store: int = MAX_PAGES_APP_STORE
    max_pages_google_play: int = MAX_PAGES_GOOGLE_PLAY
    countries: List[str] = dataclasses.field(default_factory=lambda: ["us"])
    sleep_seconds: float = SLEEP_SECONDS
    max_workers: int = MAX_WORKERS
    request_timeout: int = REQUEST_TIMEOUT
    quiet: bool = False
    dry_run: bool = False
    use_hf: bool = False
    no_verify_ssl: bool = False


# =======================
# GRACEFUL SHUTDOWN
# =======================

shutdown_requested = False


def signal_handler(sig, frame):
    global shutdown_requested
    logging.warning("Shutdown requested. Finishing current operations...")
    shutdown_requested = True


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# =======================
# CLI / CONFIG RESOLUTION
# =======================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scrape and analyze app reviews from App Store and Google Play Store.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="See docs/configuration.md for the full flag and env var reference.",
    )

    ids = parser.add_argument_group("App identifiers")
    ids.add_argument("--app-store-id", metavar="ID",
                     help="App Store numeric ID (env: APP_STORE_ID)")
    ids.add_argument("--google-play-id", metavar="ID",
                     help="Google Play package name, e.g. com.example.app (env: GOOGLE_PLAY_ID)")

    parser.add_argument(
        "--platform", nargs="+",
        choices=["app-store", "google-play"],
        metavar="PLATFORM",
        help="Platforms to scrape. Choices: app-store, google-play (default: both)",
    )

    out = parser.add_argument_group("Output")
    out.add_argument("--app-name", metavar="NAME",
                     help="Output filename prefix (env: APP_NAME, default: yourapp)")
    out.add_argument("--output-dir", metavar="DIR",
                     help="Directory for output files; created if absent (env: OUTPUT_DIR, default: .)")
    out.add_argument("--output-mode", choices=["reviews", "analysis", "both"],
                     help="Output type: raw reviews, sentiment analysis, or both "
                          "(env: OUTPUT_MODE, default: analysis)")
    sf_group = out.add_mutually_exclusive_group()
    sf_group.add_argument("--single-file", action="store_true", default=None,
                          help="Combine all platforms into one CSV file")
    sf_group.add_argument("--no-single-file", action="store_false", dest="single_file",
                          help="Write separate CSV files per platform")
    out.add_argument("--json-summary", action="store_true", default=False,
                     help="Print a JSON run summary to stdout on completion (for agent use)")
    out.add_argument("--extended-fields", action="store_true", default=False,
                     help="Include optional fields: review_title, developer_reply, "
                          "thumbs_up_count, verified_purchase")

    scrape = parser.add_argument_group("Scraping")
    scrape.add_argument("--max-pages", type=int, metavar="N",
                        help="Max pages for all platforms (overrides per-platform settings)")
    scrape.add_argument("--max-pages-app-store", type=int, metavar="N",
                        help=f"Max pages for App Store (env: MAX_PAGES_APP_STORE, default: {MAX_PAGES_APP_STORE})")
    scrape.add_argument("--max-pages-google-play", type=int, metavar="N",
                        help=f"Max pages for Google Play (env: MAX_PAGES_GOOGLE_PLAY, default: {MAX_PAGES_GOOGLE_PLAY})")
    scrape.add_argument("--countries", nargs="+", metavar="CC",
                        help="App Store country codes to scrape (env: APP_STORE_COUNTRIES, default: us). "
                             "Example: --countries us gb ca au in")
    scrape.add_argument("--sleep", type=float, metavar="SECS",
                        help=f"Delay between requests in seconds (env: SLEEP_SECONDS, default: {SLEEP_SECONDS})")
    scrape.add_argument("--max-workers", type=int, metavar="N",
                        help=f"Concurrent HTTP workers (env: MAX_WORKERS, default: {MAX_WORKERS})")
    scrape.add_argument("--timeout", type=int, metavar="SECS",
                        help=f"Request timeout in seconds (env: REQUEST_TIMEOUT, default: {REQUEST_TIMEOUT})")

    parser.add_argument("--quiet", action="store_true", default=False,
                        help="Suppress progress output; errors still go to stderr")
    parser.add_argument("--dry-run", action="store_true", default=False,
                        help="Validate config and print run plan without scraping, then exit 0")
    parser.add_argument("--use-hf", action="store_true", default=False,
                        help="Use Hugging Face transformers for sentiment (alternative to USE_HF=1)")
    parser.add_argument("--no-verify-ssl", action="store_true", default=False,
                        help="Disable SSL certificate verification. Use on networks with corporate "
                             "SSL proxies. Not recommended on untrusted networks. "
                             "Alternative: set REQUESTS_CA_BUNDLE to your proxy's CA cert path.")

    return parser


def _env_int(key: str) -> Optional[int]:
    val = os.getenv(key)
    if val:
        try:
            return int(val)
        except ValueError:
            return None
    return None


def _env_float(key: str) -> Optional[float]:
    val = os.getenv(key)
    if val:
        try:
            return float(val)
        except ValueError:
            return None
    return None


def resolve_config(args: argparse.Namespace) -> Config:
    """Build Config from CLI args → env vars → hardcoded defaults (priority order)."""
    def _first(*vals):
        for v in vals:
            if v is not None:
                return v
        return None

    max_pages_override = args.max_pages

    countries = args.countries
    if not countries:
        env_countries = os.getenv("APP_STORE_COUNTRIES")
        countries = env_countries.split() if env_countries else ["us"]

    single_file = args.single_file
    if single_file is None:
        env_sf = os.getenv("SINGLE_FILE")
        if env_sf is not None:
            single_file = env_sf.lower() in ("1", "true", "yes")
        else:
            single_file = SINGLE_FILE

    return Config(
        app_store_id=_first(args.app_store_id, os.getenv("APP_STORE_ID"), APP_STORE_ID),
        google_play_id=_first(args.google_play_id, os.getenv("GOOGLE_PLAY_ID"), GOOGLE_PLAY_ID),
        platforms=args.platform or ["app-store", "google-play"],
        app_name=_first(args.app_name, os.getenv("APP_NAME"), "yourapp"),
        output_dir=_first(args.output_dir, os.getenv("OUTPUT_DIR"), "."),
        output_mode=_first(args.output_mode, os.getenv("OUTPUT_MODE"), "analysis"),
        single_file=single_file,
        json_summary=args.json_summary,
        extended_fields=args.extended_fields,
        max_pages_app_store=_first(
            max_pages_override, args.max_pages_app_store,
            _env_int("MAX_PAGES_APP_STORE"), MAX_PAGES_APP_STORE,
        ),
        max_pages_google_play=_first(
            max_pages_override, args.max_pages_google_play,
            _env_int("MAX_PAGES_GOOGLE_PLAY"), MAX_PAGES_GOOGLE_PLAY,
        ),
        countries=countries,
        sleep_seconds=_first(args.sleep, _env_float("SLEEP_SECONDS"), SLEEP_SECONDS),
        max_workers=_first(args.max_workers, _env_int("MAX_WORKERS"), MAX_WORKERS),
        request_timeout=_first(args.timeout, _env_int("REQUEST_TIMEOUT"), REQUEST_TIMEOUT),
        quiet=args.quiet,
        dry_run=args.dry_run,
        use_hf=args.use_hf or (os.getenv("USE_HF", "0") == "1"),
        no_verify_ssl=args.no_verify_ssl or (os.getenv("NO_VERIFY_SSL", "0") == "1"),
    )


def apply_config_globals(cfg: Config) -> None:
    """Sync global constants from resolved Config for backward compatibility."""
    global APP_STORE_ID, GOOGLE_PLAY_ID
    global SCRAPE_APP_STORE, SCRAPE_GOOGLE_PLAY
    global OUTPUT_REVIEWS_ONLY, OUTPUT_ANALYSIS_ONLY, OUTPUT_BOTH, SINGLE_FILE
    global MAX_PAGES_APP_STORE, MAX_PAGES_GOOGLE_PLAY
    global SLEEP_SECONDS, MAX_WORKERS, REQUEST_TIMEOUT, _QUIET

    APP_STORE_ID = cfg.app_store_id
    GOOGLE_PLAY_ID = cfg.google_play_id

    SCRAPE_APP_STORE = "app-store" in cfg.platforms
    SCRAPE_GOOGLE_PLAY = "google-play" in cfg.platforms

    OUTPUT_REVIEWS_ONLY = cfg.output_mode == "reviews"
    OUTPUT_ANALYSIS_ONLY = cfg.output_mode == "analysis"
    OUTPUT_BOTH = cfg.output_mode == "both"
    SINGLE_FILE = cfg.single_file

    MAX_PAGES_APP_STORE = cfg.max_pages_app_store
    MAX_PAGES_GOOGLE_PLAY = cfg.max_pages_google_play
    SLEEP_SECONDS = cfg.sleep_seconds
    MAX_WORKERS = cfg.max_workers
    REQUEST_TIMEOUT = cfg.request_timeout
    _QUIET = cfg.quiet

    if cfg.no_verify_ssl:
        global _SSL_VERIFY
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        _SSL_VERIFY = False
        logging.warning(
            "SSL certificate verification is DISABLED (--no-verify-ssl). "
            "For a more secure alternative, set REQUESTS_CA_BUNDLE to your proxy's CA cert path."
        )


# =======================
# UTILITY FUNCTIONS
# =======================

def validate_config(cfg: Config) -> None:
    """Validate resolved config; exit EXIT_CONFIG_ERROR on any failure."""
    errors = []
    scrape_app_store = "app-store" in cfg.platforms
    scrape_google_play = "google-play" in cfg.platforms

    if scrape_app_store:
        if not cfg.app_store_id or not cfg.app_store_id.strip():
            errors.append(
                "APP_STORE_ID is empty. Pass --app-store-id or set the APP_STORE_ID environment variable."
            )
        elif cfg.app_store_id == _PLACEHOLDER_APP_STORE_ID:
            errors.append(
                f"APP_STORE_ID is still the placeholder '{_PLACEHOLDER_APP_STORE_ID}'. "
                "Pass --app-store-id <your_id> or set the APP_STORE_ID environment variable."
            )
        elif not cfg.app_store_id.isdigit():
            errors.append(f"APP_STORE_ID must be numeric, got: {cfg.app_store_id}")

    if scrape_google_play:
        if not cfg.google_play_id or not cfg.google_play_id.strip():
            errors.append(
                "GOOGLE_PLAY_ID is empty. Pass --google-play-id or set the GOOGLE_PLAY_ID environment variable."
            )
        elif cfg.google_play_id == _PLACEHOLDER_GOOGLE_PLAY_ID:
            errors.append(
                f"GOOGLE_PLAY_ID is still the placeholder '{_PLACEHOLDER_GOOGLE_PLAY_ID}'. "
                "Pass --google-play-id <com.example.app> or set the GOOGLE_PLAY_ID environment variable."
            )
        elif not re.match(r"^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$", cfg.google_play_id):
            errors.append(f"GOOGLE_PLAY_ID must be in format 'com.example.app', got: {cfg.google_play_id}")

    if not cfg.platforms:
        errors.append("No platforms selected. Use --platform to specify at least one.")

    if errors:
        for error in errors:
            logging.error(error)
        sys.exit(EXIT_CONFIG_ERROR)


def ensure_vader_downloaded() -> None:
    """Ensure the NLTK vader_lexicon resource is available; download if missing."""
    try:
        import nltk
        nltk.data.find("sentiment/vader_lexicon")
    except LookupError:
        logging.info("Downloading NLTK resource: 'vader_lexicon'...")
        import nltk
        nltk.download("vader_lexicon")


def build_sentiment_scorer(use_hf: bool = False) -> Tuple[Callable[[str], float], str]:
    """
    Return (score_fn, backend_name). score_fn(text) -> float in [-1, 1].
    Prefers VADER; falls back to VADER if HF is requested but unavailable.
    """
    if use_hf:
        try:
            from transformers import pipeline  # type: ignore

            sa = pipeline("sentiment-analysis", model="distilbert-base-uncased-finetuned-sst-2-english")

            def hf_score_fn(text: str) -> float:
                if not isinstance(text, str) or not text.strip():
                    return 0.0
                res = sa(text[:HF_TEXT_MAX_LENGTH])[0]
                label = str(res["label"]).upper()
                prob = float(res["score"])
                return prob if label == "POSITIVE" else -prob

            return hf_score_fn, "huggingface/distilbert-sst2"
        except Exception:
            logging.warning("Hugging Face transformers unavailable; falling back to VADER.")

    ensure_vader_downloaded()
    from nltk.sentiment import SentimentIntensityAnalyzer  # type: ignore

    sia = SentimentIntensityAnalyzer()

    def vader_score_fn(text: str) -> float:
        if not isinstance(text, str) or not text.strip():
            return 0.0
        return float(sia.polarity_scores(text)["compound"])

    return vader_score_fn, "nltk/vader"


def label_from_score(score: float) -> str:
    """Map [-1,1] score to 'good' | 'neutral' | 'bad'."""
    if score >= GOOD_THRESH:
        return "good"
    if score <= BAD_THRESH:
        return "bad"
    return "neutral"


def to_initials(name: Optional[str]) -> str:
    if not name:
        return "A."
    parts = [p for p in re.split(r"\s+", name.strip()) if re.search(r"[A-Za-z]", p)]
    if not parts:
        return "A."
    if len(parts) == 1:
        return f"{parts[0][0].upper()}."
    return f"{parts[0][0].upper()}.{parts[-1][0].upper()}."


def clean_text(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    t = re.sub(r"\s+", " ", s).strip()
    return t if t else None


def clamp_star_rating(val: Any) -> Optional[int]:
    try:
        i = int(str(val).strip())
        return min(5, max(1, i))
    except Exception:
        return None


def _text_hash(text: str) -> str:
    """Short stable hash of full review text for deduplication."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


# =======================
# APP STORE SCRAPING
# =======================

def last_12m_cutoff(now_utc: Optional[datetime] = None) -> datetime:
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    return now_utc - timedelta(days=365)


def is_within_last_12_months(dt: datetime, cutoff: datetime) -> bool:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt >= cutoff


def rss_url(country: str, app_id: str, page: int) -> str:
    return (
        f"https://itunes.apple.com/{country}/rss/customerreviews"
        f"/page={page}/id={app_id}/sortby=mostrecent/json"
    )


def create_session() -> requests.Session:
    session = requests.Session()
    session.verify = _SSL_VERIFY
    session.headers.update({
        "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    })
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=MAX_WORKERS,
        pool_maxsize=MAX_WORKERS * 2,
        max_retries=0,
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def http_get_json(url: str, session: Optional[requests.Session] = None) -> Optional[Dict[str, Any]]:
    if session is None:
        session = create_session()
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
            headers = {"User-Agent": random.choice(ua_pool), "Accept": "application/json"}
            resp = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (429, 500, 502, 503, 504):
                time.sleep(BACKOFF_BASE * (1.5 ** (attempt - 1)))
                continue
            logging.warning("%s -> HTTP %s", url, resp.status_code)
            return None
        except requests.RequestException as e:
            logging.warning("GET error (%s), attempt %d", e, attempt)
            time.sleep(BACKOFF_BASE * (1.5 ** (attempt - 1)))
    logging.error("Exhausted retries for %s", url)
    return None


def parse_rss_reviews(json_obj: Dict[str, Any], extended_fields: bool = False) -> List[Dict[str, Any]]:
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
            updated_str = (
                e.get("updated", {}).get("label")
                or e.get("im:releaseDate", {}).get("label")
            )
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
            title_text = clean_text(e.get("title", {}).get("label"))
            text = clean_text(content) or title_text
            if not text:
                continue
            row: Dict[str, Any] = {
                "dt": dt,
                "review_date": dt.date().isoformat(),
                "star_rating": star,
                "reviewer_anonymized": initials,
                "review_text": text,
                "platform": "App Store",
            }
            if extended_fields:
                # Only include title when it differs from the body text
                row["review_title"] = title_text if title_text and title_text != text else None
            out.append(row)
    except Exception:
        return []
    return out


def scrape_app_store(
    app_id: str,
    countries: Optional[List[str]] = None,
    max_pages: int = 20,
    sleep_sec: float = 0.3,
    extended_fields: bool = False,
) -> List[Dict[str, Any]]:
    if countries is None:
        countries = ["us"]
    logging.info(
        "Scraping App Store reviews for app ID: %s (countries: %s)",
        app_id,
        ", ".join(countries),
    )
    cutoff = last_12m_cutoff()
    all_raw: List[Dict[str, Any]] = []
    session = create_session()

    try:
        for country in countries:
            logging.info("  Country store: %s", country)
            for page in tqdm(
                range(1, max_pages + 1),
                desc=f"App Store/{country}",
                unit="page",
                disable=_QUIET,
            ):
                if shutdown_requested:
                    logging.info("Shutdown requested, stopping App Store scraping...")
                    break
                url = rss_url(country, app_id, page)
                data = http_get_json(url, session)
                if not data:
                    break
                parsed = parse_rss_reviews(data, extended_fields=extended_fields)
                if not parsed:
                    break
                oldest = None
                for r in parsed:
                    dt = r["dt"]
                    if oldest is None or dt < oldest:
                        oldest = dt
                    if is_within_last_12_months(dt, cutoff):
                        all_raw.append(r)
                if oldest and not is_within_last_12_months(oldest, cutoff):
                    break
                time.sleep(sleep_sec)
    finally:
        session.close()

    seen: set = set()
    clean: List[Dict[str, Any]] = []
    for r in all_raw:
        key = (r["review_date"], r["star_rating"], _text_hash(r["review_text"]))
        if key in seen:
            continue
        seen.add(key)
        row: Dict[str, Any] = {
            "review_date": r["review_date"],
            "star_rating": int(r["star_rating"]),
            "reviewer_anonymized": r["reviewer_anonymized"],
            "review_text": r["review_text"],
            "platform": r["platform"],
        }
        if extended_fields:
            row["review_title"] = r.get("review_title")
        clean.append(row)

    logging.info("Collected %d App Store reviews", len(clean))
    return clean


# =======================
# GOOGLE PLAY STORE SCRAPING
# =======================

def anonymize_name_google(full_name: str) -> str:
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


def scrape_google_play(
    app_id: str,
    lang: str = "en",
    country: str = "us",
    max_pages: int = MAX_PAGES_GOOGLE_PLAY,
    sleep_sec: float = SLEEP_SECONDS,
    extended_fields: bool = False,
) -> List[Dict]:
    logging.info("Scraping Google Play Store reviews for app ID: %s", app_id)
    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(days=365)
    all_rows: List[Dict] = []
    seen: set = set()

    token = None
    page = 0
    consecutive_errors = 0

    with tqdm(desc="Google Play pages", unit="page", disable=_QUIET) as pbar:
        while page < max_pages:
            if shutdown_requested:
                logging.info("Shutdown requested, stopping Google Play scraping...")
                break

            page += 1
            pbar.update(1)

            try:
                batch, token = reviews(
                    app_id,
                    lang=lang,
                    country=country,
                    sort=Sort.NEWEST,
                    count=GOOGLE_PLAY_BATCH_SIZE,
                    continuation_token=token,
                )
                consecutive_errors = 0
            except Exception as e:
                consecutive_errors += 1
                logging.warning("Google Play error on page %d: %s", page, e)
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    logging.error(
                        "Too many consecutive errors (%d), stopping Google Play scraping",
                        consecutive_errors,
                    )
                    break
                time.sleep(2.0)
                try:
                    batch, token = reviews(
                        app_id,
                        lang=lang,
                        country=country,
                        sort=Sort.NEWEST,
                        count=GOOGLE_PLAY_BATCH_SIZE,
                        continuation_token=token,
                    )
                    consecutive_errors = 0
                except Exception as e2:
                    logging.error("Retry failed on page %d: %s", page, e2)
                    continue

            if not batch:
                logging.info("No more reviews on page %d", page)
                break

            oldest_in_batch: Optional[datetime] = None

            for r in batch:
                dt = r.get("at")
                if not dt:
                    continue
                if getattr(dt, "tzinfo", None) is None:
                    dt = dt.replace(tzinfo=timezone.utc)

                if oldest_in_batch is None or dt < oldest_in_batch:
                    oldest_in_batch = dt

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

                key = (dt.date().isoformat(), score, _text_hash(text))
                if key in seen:
                    continue
                seen.add(key)

                row: Dict[str, Any] = {
                    "review_date": dt.date().isoformat(),
                    "star_rating": score,
                    "reviewer_anonymized": anon,
                    "review_text": text,
                    "platform": "Google Play Store",
                }
                if extended_fields:
                    row["thumbs_up_count"] = r.get("thumbsUpCount", 0)
                    reply = (r.get("replyContent") or "").strip()
                    row["developer_reply"] = reply or None
                    reply_at = r.get("repliedAt")
                    row["developer_reply_date"] = (
                        reply_at.date().isoformat()
                        if reply_at and hasattr(reply_at, "date")
                        else None
                    )
                all_rows.append(row)

            pbar.set_description(f"Google Play pages (reviews: {len(all_rows)})")

            # Stop when oldest review in this batch falls outside the 12-month window
            if oldest_in_batch and oldest_in_batch < cutoff:
                logging.info("Oldest review in batch is outside 12-month window, stopping")
                break

            if token is None:
                logging.info("No continuation token, reached end of reviews")
                break

            time.sleep(sleep_sec)

    logging.info("Collected %d Google Play Store reviews", len(all_rows))
    return all_rows



# =======================
# ANALYSIS FUNCTIONS
# =======================

def analyze_reviews(
    reviews_data: List[Dict],
    platform: str,
    score_fn: Callable[[str], float],
    backend: str,
) -> List[Dict]:
    logging.info("Analyzing %d %s reviews with %s...", len(reviews_data), platform, backend)
    df = pd.DataFrame(reviews_data)
    texts = df["review_text"].astype("string").fillna("")
    df["sentiment_score"] = texts.apply(score_fn).astype(float)
    df["sentiment_label"] = df["sentiment_score"].apply(label_from_score)
    return df.to_dict("records")


# =======================
# OUTPUT FUNCTIONS
# =======================

def build_output_path(
    output_dir: str,
    app_name: str,
    platform: Optional[str],
    analysis: bool,
) -> str:
    parts = [app_name]
    if platform:
        parts.append(platform)
    parts.append("reviews")
    if analysis:
        parts.append("analysis")
    return str(Path(output_dir) / ("_".join(parts) + ".csv"))


def save_csv(reviews_data: List[Dict], filepath: str) -> None:
    if not reviews_data:
        logging.info("No reviews to save for %s", filepath)
        return
    df = pd.DataFrame(reviews_data)
    df = df.sort_values(["review_date", "star_rating"], ascending=[False, False])
    df.to_csv(filepath, index=False, encoding="utf-8", quoting=csv.QUOTE_ALL)
    logging.info("Saved %d reviews to %s", len(reviews_data), filepath)


# =======================
# MAIN ORCHESTRATION
# =======================

def scrape_all_platforms(cfg: Config) -> Dict[str, List[Dict]]:
    all_reviews: Dict[str, List[Dict]] = {}

    if "app-store" in cfg.platforms and not shutdown_requested:
        try:
            all_reviews["app_store"] = scrape_app_store(
                cfg.app_store_id,
                countries=cfg.countries,
                max_pages=cfg.max_pages_app_store,
                sleep_sec=cfg.sleep_seconds,
                extended_fields=cfg.extended_fields,
            )
        except Exception as e:
            logging.error("Error scraping App Store: %s", e)
            all_reviews["app_store"] = []

    if "google-play" in cfg.platforms and not shutdown_requested:
        try:
            all_reviews["google_play"] = scrape_google_play(
                cfg.google_play_id,
                max_pages=cfg.max_pages_google_play,
                sleep_sec=cfg.sleep_seconds,
                extended_fields=cfg.extended_fields,
            )
        except Exception as e:
            logging.error("Error scraping Google Play Store: %s", e)
            all_reviews["google_play"] = []

    return all_reviews


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    cfg = resolve_config(args)
    apply_config_globals(cfg)

    logging.basicConfig(
        level=logging.WARNING if cfg.quiet else logging.INFO,
        format="[%(levelname)s] %(message)s",
        stream=sys.stderr,
    )

    validate_config(cfg)

    enabled_platforms = [p for p in ["app-store", "google-play"] if p in cfg.platforms]

    if cfg.dry_run:
        print("Dry run — configuration is valid.", file=sys.stderr)
        print(f"Would scrape: {', '.join(enabled_platforms)}", file=sys.stderr)
        print(f"Output directory: {cfg.output_dir}", file=sys.stderr)
        print(f"Output prefix: {cfg.app_name}", file=sys.stderr)
        print(f"Output mode: {cfg.output_mode}", file=sys.stderr)
        print(f"Single file: {cfg.single_file}", file=sys.stderr)
        if "app-store" in cfg.platforms:
            print(f"App Store countries: {', '.join(cfg.countries)}", file=sys.stderr)
        sys.exit(EXIT_SUCCESS)

    Path(cfg.output_dir).mkdir(parents=True, exist_ok=True)

    logging.info("Platforms: %s", ", ".join(enabled_platforms))
    logging.info("Output dir: %s | mode: %s | single file: %s", cfg.output_dir, cfg.output_mode, cfg.single_file)

    start_time = time.time()
    scraping_start = time.time()
    all_reviews = scrape_all_platforms(cfg)
    scraping_time = time.time() - scraping_start

    if shutdown_requested:
        logging.warning("Scraping interrupted. Saving collected data...")

    total_reviews = sum(len(v) for v in all_reviews.values())
    logging.info("Scraping done in %.2fs — %d total reviews", scraping_time, total_reviews)

    write_raw = cfg.output_mode in ("reviews", "both")
    write_analysis = cfg.output_mode in ("analysis", "both")

    score_fn: Optional[Callable] = None
    backend: str = ""
    if write_analysis:
        score_fn, backend = build_sentiment_scorer(cfg.use_hf)
        logging.info("Sentiment backend: %s", backend)

    files_written: List[str] = []
    processing_start = time.time()

    if cfg.single_file:
        raw_combined: List[Dict] = []
        analyzed_combined: List[Dict] = []
        for platform_key, reviews_data in all_reviews.items():
            if not reviews_data:
                continue
            if write_raw:
                raw_combined.extend(reviews_data)
            if write_analysis:
                analyzed_combined.extend(
                    analyze_reviews(reviews_data, platform_key, score_fn, backend)
                )
        if write_raw and raw_combined:
            fp = build_output_path(cfg.output_dir, cfg.app_name, None, analysis=False)
            save_csv(raw_combined, fp)
            files_written.append(fp)
        if write_analysis and analyzed_combined:
            fp = build_output_path(cfg.output_dir, cfg.app_name, None, analysis=True)
            save_csv(analyzed_combined, fp)
            files_written.append(fp)
    else:
        for platform_key, reviews_data in all_reviews.items():
            if not reviews_data:
                continue
            if write_raw:
                fp = build_output_path(cfg.output_dir, cfg.app_name, platform_key, analysis=False)
                save_csv(reviews_data, fp)
                files_written.append(fp)
            if write_analysis:
                analyzed = analyze_reviews(reviews_data, platform_key, score_fn, backend)
                fp = build_output_path(cfg.output_dir, cfg.app_name, platform_key, analysis=True)
                save_csv(analyzed, fp)
                files_written.append(fp)

    processing_time = time.time() - processing_start
    total_time = time.time() - start_time

    # Map cfg.platforms slugs to all_reviews keys for failure detection
    _slug_to_key = {"app-store": "app_store", "google-play": "google_play"}
    platforms_failed = [
        p for p in cfg.platforms
        if _slug_to_key.get(p) in all_reviews and not all_reviews[_slug_to_key[p]]
    ]
    platforms_with_data = [k for k, v in all_reviews.items() if v]

    if shutdown_requested:
        status, exit_code = "interrupted", EXIT_INTERRUPTED
    elif not platforms_with_data:
        status, exit_code = "failed", EXIT_TOTAL_FAILURE
    elif platforms_failed:
        status, exit_code = "partial", EXIT_PARTIAL_FAILURE
    else:
        status, exit_code = "success", EXIT_SUCCESS

    logging.info(
        "Total: %.2fs | Scraping: %.2fs | Processing: %.2fs",
        total_time, scraping_time, processing_time,
    )
    if scraping_time > 0:
        logging.info("Reviews/second: %.1f", total_reviews / scraping_time)

    if cfg.json_summary:
        summary = {
            "status": status,
            "exit_code": exit_code,
            "total_reviews": total_reviews,
            "by_platform": {k: len(v) for k, v in all_reviews.items()},
            "files_written": files_written,
            "duration_seconds": round(total_time, 2),
            "platforms_failed": platforms_failed,
            "interrupted": shutdown_requested,
        }
        print(json.dumps(summary, indent=2))

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
