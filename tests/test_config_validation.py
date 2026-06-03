"""Tests for validate_config() and resolve_config()."""

import sys
import pytest

sys.path.insert(0, ".")
from reviews_scraper import Config, validate_config, EXIT_CONFIG_ERROR


def _valid_config(**overrides) -> Config:
    base = Config(
        app_store_id="584606479",
        google_play_id="com.intuit.quickbooks",
        platforms=["app-store", "google-play"],
        output_mode="analysis",
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def _assert_exits_with_config_error(cfg: Config):
    with pytest.raises(SystemExit) as exc_info:
        validate_config(cfg)
    assert exc_info.value.code == EXIT_CONFIG_ERROR


# --- Valid config ---

def test_valid_config_passes():
    validate_config(_valid_config())  # must not raise


def test_single_platform_app_store_valid():
    validate_config(_valid_config(platforms=["app-store"]))


def test_single_platform_google_play_valid():
    validate_config(_valid_config(platforms=["google-play"]))


# --- Placeholder detection ---

def test_placeholder_app_store_id_rejected():
    _assert_exits_with_config_error(_valid_config(app_store_id="123456789"))


def test_placeholder_google_play_id_rejected():
    _assert_exits_with_config_error(_valid_config(google_play_id="com.example"))


# --- Format validation ---

def test_invalid_app_store_id_format():
    _assert_exits_with_config_error(_valid_config(app_store_id="notanumber"))


def test_invalid_google_play_id_no_dots():
    _assert_exits_with_config_error(_valid_config(google_play_id="comexampleapp"))


def test_invalid_google_play_id_starts_with_digit():
    _assert_exits_with_config_error(_valid_config(google_play_id="1com.example.app"))


# --- Platform selection ---

def test_no_platforms_exits():
    _assert_exits_with_config_error(_valid_config(platforms=[]))


def test_skipped_platform_not_validated():
    # google_play_id placeholder is ignored when google-play is not in platforms
    cfg = _valid_config(platforms=["app-store"], google_play_id="com.example")
    validate_config(cfg)  # must not raise
