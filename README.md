# Powerful Web Spider - Comprehensive Page Discovery Tool

Two effective web spiders focused on discovering as many pages as possible on websites. No complex features, just powerful page discovery with simple output.

## Features

- **Comprehensive URL Discovery**:
  - Extracts links from HTML tags (href, src, action)
  - Parses JavaScript for URLs
  - Finds URLs in comments
  - Discovers common paths automatically
  - Extracts from meta tags and data attributes
- **Multi-threaded crawling** for speed
- **Simple terminal output** - prints URLs as discovered
- **Optional text file output** - one URL per line
- **Two versions**:
  - `spider.py` - Standard spider
  - `aggressive_spider.py` - More aggressive discovery techniques

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Basic Spider

```bash
# Spider a website
python spider.py https://example.com

# Limit to 100 pages
python spider.py https://example.com -m 100

# Save URLs to file
python spider.py https://example.com -o urls.txt

# Use more threads for faster crawling
python spider.py https://example.com -t 20
```

### Aggressive Spider

The aggressive spider uses more discovery techniques and can optionally crawl across domains:

```bash
# Aggressive spidering
python aggressive_spider.py https://example.com

# Allow cross-domain crawling
python aggressive_spider.py https://example.com -x

# Save with high thread count
python aggressive_spider.py https://example.com -t 30 -o found_urls.txt
```

## Command Line Options

```
positional arguments:
  url                   Starting URL to spider

optional arguments:
  -h, --help            show this help message and exit
  -m, --max-pages       Maximum number of pages to crawl
  -o, --output          Output file to save URLs (one per line)
  -t, --threads         Number of threads (default: 10 for spider.py, 20 for aggressive_spider.py)
  -x, --cross-domain    Allow cross-domain crawling (aggressive_spider.py only)
```

## Examples

Spider voldemort.ru and save all found URLs:
```bash
python aggressive_spider.py https://example.ru -o example_urls.txt
```

Spider neopets.com with maximum discovery:
```bash
python aggressive_spider.py https://example.com -m 500 -t 30 -o example_urls.txt
```

## How It Works

The spiders use multiple techniques to find URLs:

1. **HTML Parsing**: Extracts from all href, src, action attributes
2. **JavaScript Analysis**: Finds URLs in JavaScript code
3. **Path Discovery**: Automatically tries common paths like /admin, /login, /api, etc.
4. **URL Variations**: Tries different extensions (.html, .php, etc.)
5. **Comment Parsing**: Looks for URLs in HTML comments
6. **Meta Tag Analysis**: Extracts from meta refresh and other tags

## Output

- **Terminal**: Shows each discovered URL as it's found
- **Text File**: Simple list of URLs, one per line
- **Status Updates**: Shows progress every 5 seconds

## Tips for Maximum Discovery

1. Use the aggressive spider for better results
2. Increase thread count for faster crawling (but be respectful)
3. Don't set max_pages too low - let it discover
4. For large sites, be prepared to wait - thorough discovery takes time
5. Use `-x` flag carefully - it can spider the entire internet!

## Comparison

- `spider.py`: Good for standard websites, respects domain boundaries
- `aggressive_spider.py`: Better discovery, more techniques, optional cross-domain
