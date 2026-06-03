# Agent Guidelines

Shared guidance for AI agents invoking `reviews_scraper.py`. Referenced by both `CLAUDE.md` and `AGENTS.md`.

For the complete flag reference see [configuration.md](configuration.md). For internal architecture see [ARCHITECTURE.md](ARCHITECTURE.md).

---

> **Note:** Trustpilot support was removed in v2. DataDome bot detection reliably blocks non-browser HTTP clients. See [README.md](../README.md) for context.

## Minimum viable invocation

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

`--quiet` routes all progress output to stderr. `--json-summary` prints the structured result to stdout. This separation allows clean stdout capture.

---

## Discovering app identifiers

Before invoking the script, confirm the correct IDs for the target app:

- **App Store ID:** Find the numeric ID in the App Store URL: `apps.apple.com/app/id{ID}`
- **Google Play ID:** Find the package name in the Play Store URL: `play.google.com/store/apps/details?id={ID}`

Never pass placeholder values (`123456789`, `com.example`). The script will detect these and exit with code `1`.

---

## Validate before running

Use `--dry-run` to confirm config is valid without scraping:

```bash
python reviews_scraper.py [all flags] --dry-run
```

Exits `0` if valid, `1` if not. Output goes to stderr.

---

## Interpreting exit codes

| Code | Meaning | Recommended action |
|------|---------|-------------------|
| `0` | Success — all platforms returned data | Read the files listed in `files_written` |
| `1` | Config error — bad or placeholder value | Fix the flagged identifier and retry |
| `2` | Partial — some platforms returned data, some returned nothing | Check which platform failed in `platforms_failed`; retry that platform separately if needed |
| `3` | Total failure — no reviews collected from any platform | Check network access; verify the IDs are correct; check if the app has reviews on those platforms |
| `130` | Interrupted by signal | Partial data may have been saved; check `files_written` in the JSON summary |

---

## Parsing the JSON summary

When `--json-summary` is passed, stdout contains exactly one JSON object after the run completes. Capture stdout and parse it:

```python
import subprocess, json

result = subprocess.run(
    ["python", "reviews_scraper.py", "--app-name", "myapp", "--json-summary", "--quiet", ...],
    capture_output=True, text=True
)
summary = json.loads(result.stdout)
files = summary["files_written"]
status = summary["status"]   # "success" | "partial" | "failed" | "interrupted"
```

---

## Handling partial failures

If `status == "partial"`, `platforms_failed` lists which platforms returned nothing. Typical causes:

- **App Store:** App has no reviews in the scraped country storefronts. Try adding more countries via `--countries`.
- **Google Play:** App isn't listed on Google Play, or the package name is wrong.

A partial result is still useful — the files that were written contain real data.

---

## Rate limiting

If a platform returns 0 reviews unexpectedly (and `status == "partial"` or `"failed"`):

1. Wait 10–15 minutes before retrying
2. Add `--sleep 0.6` to slow down requests
3. Reduce `--max-workers 2` to lower concurrency
4. Scrape one platform at a time using `--platform`

---

## Scraping a subset of platforms

```bash
# App Store only
python reviews_scraper.py --platform app-store [other flags]

# Google Play only
python reviews_scraper.py --platform google-play [other flags]
```

---

## Expected runtime

On a typical internet connection with default settings:

| Platform | Reviews/second | Time for ~500 reviews |
|----------|---------------|----------------------|
| App Store (US only) | 2–5 | ~1–3 min |
| Google Play | 10–20 | ~30 sec |

Both platforms combined: typically **2–4 minutes** for 500–1000 total reviews.

---

## Chaining with downstream analysis

The CSV output is ready to upload directly to Claude or other AI tools:

```python
# After running the scraper, the analysis CSV can be read and passed to Claude
import pandas as pd
df = pd.read_csv(summary["files_written"][0])
reviews_text = df.to_csv(index=False)
# Pass reviews_text to Claude for pattern analysis
```

---

## Multi-country App Store

Default is US only (`--countries us`). For global apps, add relevant markets:

```bash
--countries us gb ca au in
```

See [configuration.md](configuration.md) for country codes and rate limit tradeoffs.
