# Async Web Spider

An effective async web spider with:

- Robots.txt compliance (configurable)
- Optional sitemap seeding from robots.txt
- URL normalization and deduplication
- Concurrency with per-host politeness delay
- HTML parsing for links, title, meta description, and canonical
- JSONL output; optional HTML body persistence

## Quickstart

- Create a virtual environment and install dependencies:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

- Run the spider:

```bash
python -m spider https://example.com --max-pages 100 --max-depth 2 --output out.jsonl
```

## CLI Options

- `start_urls`: One or more starting URLs
- `--allowed-domains`: Limit crawl to specific domain(s). Defaults to the domains of the start URLs
- `--include-subdomains`: Allow subdomains of allowed domains
- `--max-pages`: Maximum pages to fetch (default 500)
- `--max-depth`: Maximum crawl depth from start URLs (default 2)
- `--concurrency`: Max concurrent requests (default 10)
- `--delay`: Per-host politeness delay in seconds (default 0.5)
- `--user-agent`: Custom User-Agent string
- `--sitemaps`: Seed URLs from sitemaps referenced in robots.txt
- `--no-robots`: Disable robots.txt checks (not recommended)
- `--output`: Output JSONL file path (default `crawl.jsonl`)
- `--save-html`: Persist fetched HTML in output rows
- `--timeout`: Request timeout (default 15s)
- `--verbose`: Verbose logging

## Output

Each line in the JSONL contains fields like:

```json
{
  "url": "https://example.com/",
  "final_url": "https://example.com/",
  "status": 200,
  "content_type": "text/html; charset=utf-8",
  "duration_ms": 123,
  "depth": 0,
  "title": "Example Domain",
  "meta_description": "...",
  "canonical_url": "https://example.com/",
  "links": ["https://example.com/more"],
  "html": "<html>..." // present if --save-html
}
```

## Notes

- The spider filters known non-HTML extensions and only follows `http/https` links.
- Concurrency and delay should be tuned for the target site(s). Be respectful.
- For very large crawls, consider streaming output to a database and persisting state.