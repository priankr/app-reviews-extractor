"""Tests for parser functions and deduplication logic."""

import sys

import pytest

sys.path.insert(0, ".")
from reviews_scraper import (
    anonymize_name_google,
    clamp_star_rating,
    clean_text,
    parse_rss_reviews,
    _text_hash,
)


# --- anonymize_name_google ---

def test_google_single_name():
    assert anonymize_name_google("Alice") == "A."


def test_google_full_name():
    assert anonymize_name_google("Alice Smith") == "A. S."


def test_google_anonymous_user():
    assert anonymize_name_google("A Google User") == "A."


def test_google_empty_name():
    assert anonymize_name_google("") == "A."


# --- clamp_star_rating ---

def test_clamp_below_min():
    assert clamp_star_rating(0) == 1


def test_clamp_above_max():
    assert clamp_star_rating(6) == 5


def test_clamp_valid():
    assert clamp_star_rating(3) == 3


def test_clamp_string_numeric():
    assert clamp_star_rating("4") == 4


def test_clamp_invalid_returns_none():
    assert clamp_star_rating("bad") is None


# --- parse_rss_reviews ---

def _rss_entry(rating="4", content="Great app", title="Nice",
               updated="2024-06-01T00:00:00Z", author="Alice Smith"):
    return {
        "im:rating": {"label": rating},
        "content": {"label": content},
        "title": {"label": title},
        "updated": {"label": updated},
        "author": {"name": {"label": author}},
    }


def test_parse_rss_valid():
    data = {"feed": {"entry": [_rss_entry()]}}
    results = parse_rss_reviews(data)
    assert len(results) == 1
    r = results[0]
    assert r["star_rating"] == 4
    assert r["review_text"] == "Great app"
    assert r["platform"] == "App Store"
    assert r["reviewer_anonymized"] == "A.S."


def test_parse_rss_missing_rating_skipped():
    entry = _rss_entry()
    entry["im:rating"]["label"] = None
    entry["content"]["label"] = None
    data = {"feed": {"entry": [entry]}}
    assert parse_rss_reviews(data) == []


def test_parse_rss_missing_text_falls_back_to_title():
    entry = _rss_entry(content="", title="Awesome")
    data = {"feed": {"entry": [entry]}}
    results = parse_rss_reviews(data)
    assert len(results) == 1
    assert results[0]["review_text"] == "Awesome"


def test_parse_rss_extended_fields_include_title():
    entry = _rss_entry(content="Body text", title="A great title")
    data = {"feed": {"entry": [entry]}}
    results = parse_rss_reviews(data, extended_fields=True)
    assert results[0]["review_title"] == "A great title"


def test_parse_rss_extended_fields_title_equals_body_is_none():
    entry = _rss_entry(content="Same text", title="Same text")
    data = {"feed": {"entry": [entry]}}
    results = parse_rss_reviews(data, extended_fields=True)
    assert results[0]["review_title"] is None


# --- _text_hash deduplication ---

def test_dedup_hash_differs_on_long_similar_text():
    text_a = "A" * 100 + "different ending A"
    text_b = "A" * 100 + "different ending B"
    assert _text_hash(text_a) != _text_hash(text_b)


def test_dedup_hash_same_text_is_equal():
    text = "This is a review"
    assert _text_hash(text) == _text_hash(text)
