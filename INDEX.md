# Repo Index

One line per file/folder. Start here if you're orienting to the repo.

| Path | What it is | When to use it |
|------|-----------|----------------|
| `reviews_scraper.py` | The scraper script | Run this to extract reviews |
| `requirements.txt` | Python dependencies | `pip install -r requirements.txt` on first setup |
| `CLAUDE.md` | Claude Code entry point | Claude reads this automatically |
| `AGENTS.md` | Generic agent entry point | Other agents start here |
| `README.md` | Human-facing overview | What this tool does and why |
| `examples/` | QuickBooks example output and config | Reference for expected output format |
| `tests/` | Unit tests | `pytest tests/` to verify parser and config logic |
| `docs/getting-started.md` | Setup, usage examples, troubleshooting, tips | Developer setup and first-run guide |
| `docs/configuration.md` | All CLI flags, env vars, defaults, output schema | Look here for any flag or setting question |
| `docs/agent-guidelines.md` | Agent invocation patterns, exit codes, rate limiting | Agent-specific runtime guidance |
| `docs/ARCHITECTURE.md` | Internal scraping flow, dedup, sentiment pipeline | Look here to understand how the script works internally |
