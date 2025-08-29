# PathFinder - Advanced Web Spidering Tool

[![Python Version](https://img.shields.io/badge/python-3.7%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![asyncio](https://img.shields.io/badge/async-asyncio-brightgreen.svg)](https://docs.python.org/3/library/asyncio.html)

PathFinder is a nice tool - a web crawler - designed for security researchers, penetration testers, and developers. It crawls the given site and finds links.

## Table of Contents
- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Command Reference](#command-reference)
- [Advanced Usage](#advanced-usage)
- [Crawling Intelligence](#crawling-intelligence)
- [Performance Optimization](#performance-optimization)
- [Use Cases](#use-cases)
- [Output and Integration](#output-and-integration)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)
- [Responsible Use](#responsible-use)

## Features

### Advanced Discovery
- **Intelligent Link Detection**: Extracts links from href attributes, srcset, and meta refresh tags
- **Smart URL Normalization**: Handles redirects, canonical URLs, and parameter normalization
- **Content-Aware Filtering**: Automatically identifies and processes HTML while filtering binary content
- **Base Tag Support**: Respects HTML `<base>` tags for proper link resolution

### Professional Crawling
- **Asynchronous Architecture**: High-performance async I/O with configurable worker pools
- **Connection Management**: Intelligent connection pooling and HTTP/2 support
- **Retry Logic**: Exponential backoff with Retry-After header compliance
- **Memory Protection**: Configurable body size limits and streaming for large responses

### Compliance & Ethics
- **robots.txt Integration**: Full robots.txt parsing with per-host caching
- **Crawl Delay Respect**: Honors crawl-delay directives from robots.txt
- **Nofollow Support**: Respects meta robots, X-Robots-Tag headers, and rel="nofollow"
- **Politeness Controls**: Built-in jitter and rate limiting

### Advanced Filtering
- **Regex Pattern Matching**: Powerful include/exclude URL filtering
- **Scope Management**: Domain and subdomain-aware crawling boundaries  
- **Content Type Validation**: MIME type checking and HTML detection
- **Path Intelligence**: Automatic filtering of feeds, APIs, and admin paths

### Security Features
- **HTTPS Enforcement**: Optional HTTPS-only crawling mode
- **Certificate Validation**: Configurable SSL verification
- **Header Rotation**: User-Agent randomization and header management
- **Resource Limits**: Protection against resource exhaustion attacks

## Installation

### Prerequisites
- Python 3.7 or higher
- Required packages: `aiohttp`, `beautifulsoup4`, `lxml`

### Setup
```bash
git clone https://github.com/5u5urrus/PathFinder.git
cd PathFinder
pip install aiohttp beautifulsoup4 lxml
```

### Optional Performance Boost
```bash
pip install aiohttp[speedups] lxml
```

## Quick Start

### Basic Website Mapping
```bash
python pathfinder.py https://example.com 2
```
Maps example.com to depth 2, including subdomains.

### Security Assessment Mode
```bash
python pathfinder.py https://target.com 3 --respect-robots --max-pages 500 --out discovered_paths.txt
```

### Development Site Crawling  
```bash
python pathfinder.py https://dev.example.com 2 --no-subdomains --https-only
```

## Command Reference

```bash
python pathfinder.py <url> <max_depth> [options]
```

### Required Arguments
- `url` - Target URL to begin crawling
- `max_depth` - Maximum link depth to follow (0 = start page only)

### Scope Control
| Option | Description | Default |
|--------|-------------|---------|
| `--no-subdomains` | Restrict crawling to exact domain match | False |
| `--max-pages N` | Stop after discovering N pages | Unlimited |
| `--https-only` | Only follow HTTPS URLs and redirects | False |

### Performance Tuning
| Option | Description | Default |
|--------|-------------|---------|
| `--concurrency N` | Number of concurrent workers | 20 |
| `--timeout SECS` | Per-request timeout in seconds | 15.0 |
| `--max-body-bytes N` | Maximum HTML size to process | 5MB |

### Filtering Options
| Option | Description | Default |
|--------|-------------|---------|
| `--include REGEX` | Only crawl URLs matching this pattern | None |
| `--exclude REGEX` | Skip URLs matching this pattern | None |

### Politeness Controls
| Option | Description | Default |
|--------|-------------|---------|
| `--respect-robots` | Honor robots.txt and nofollow directives | False |
| `--jitter MIN MAX` | Random delay range between requests | 0.05 0.15 |

### Technical Options
| Option | Description | Default |
|--------|-------------|---------|
| `--insecure` | Skip SSL certificate verification | False |
| `--out FILE` | Save discovered URLs to file | Console only |
| `--log LEVEL` | Set logging verbosity (DEBUG/INFO/WARNING) | INFO |

## Advanced Usage

### Targeted Discovery
```bash
# Focus on specific content types
python pathfinder.py https://blog.example.com 3 --include "/(post|article|blog)/" --max-pages 200

# Exclude administrative areas
python pathfinder.py https://example.com 2 --exclude "/(admin|wp-admin|api)/" --respect-robots

# Development environment discovery
python pathfinder.py https://staging.example.com 2 --include "(test|dev|staging)" --https-only
```

### Performance Optimization
```bash
# High-speed discovery (use carefully)
python pathfinder.py https://example.com 2 --concurrency 50 --timeout 8 --jitter 0.01 0.03

# Resource-constrained environments  
python pathfinder.py https://example.com 3 --concurrency 8 --max-body-bytes 1000000

# Respectful long-term crawling
python pathfinder.py https://example.com 4 --respect-robots --concurrency 5 --jitter 1.0 2.0
```

### Security Research Applications
```bash
# Comprehensive site mapping
python pathfinder.py https://target.com 3 --max-pages 1000 --out sitemap.txt --log INFO

# SSL-only endpoint discovery
python pathfinder.py https://secure.example.com 2 --https-only --respect-robots

# Subdomain enumeration
python pathfinder.py https://example.com 1 --include "^https://[^/]*\.example\.com" --max-pages 100
```

## Crawling Intelligence

### URL Normalization Process
PathFinder implements sophisticated URL normalization to prevent duplicate crawling:

1. **Parameter Cleaning**: Removes tracking parameters (`utm_*`, `fbclid`, `gclid`)
2. **Index File Handling**: Normalizes `/index.html`, `/index.php` to base paths
3. **Case Normalization**: Standardizes scheme and hostname casing
4. **Query Sorting**: Sorts parameters for consistent deduplication
5. **Fragment Removal**: Strips URL fragments for cleaner results

### Scope Management
The crawler maintains intelligent scope boundaries:

**With Subdomains (Default):**
- `example.com` ✓
- `www.example.com` ✓  
- `blog.example.com` ✓
- `api.example.com` ✓

**Without Subdomains (`--no-subdomains`):**
- `example.com` ✓
- `www.example.com` ✓ (www is treated as equivalent)
- `blog.example.com` ✗

### Content Detection & Filtering
Automatic content type detection prevents crawling non-HTML resources:

**Filtered Content:**
- Binary files (PDF, images, archives, executables)
- API endpoints (JSON/XML without HTML structure)
- Feed URLs (RSS, Atom, WordPress feeds)
- Media files (videos, audio, fonts)

**Processed Content:**
- HTML pages with proper MIME types
- XHTML and XML with HTML-like structure
- Misidentified HTML (detected by content sniffing)

### robots.txt Compliance
When `--respect-robots` is enabled, PathFinder implements full robots.txt support:

1. **Per-Origin Caching**: Fetches robots.txt once per hostname:port
2. **Rule Processing**: Handles Disallow/Allow directives with wildcard matching
3. **Crawl-Delay Honor**: Implements delay directives between requests
4. **User-Agent Matching**: Processes rules for `*` user-agent
5. **Sitemap Discovery**: Extracts sitemap URLs for potential integration

## Performance Optimization

### Concurrency Guidelines

**Site Size Recommendations:**
- **Small sites** (<500 pages): `--concurrency 5-10`
- **Medium sites** (500-5000 pages): `--concurrency 15-30`  
- **Large sites** (>5000 pages): `--concurrency 30-75`
- **Respectful mode**: `--concurrency 3-8` with `--respect-robots`

### Memory Management
PathFinder includes multiple memory protection mechanisms:

- **Streaming Downloads**: Large responses are processed in chunks
- **Size Limits**: Configurable maximum body size (default 5MB)
- **Connection Pooling**: Reuses connections efficiently
- **Automatic Cleanup**: Garbage collection of processed content

### Rate Limiting Strategies
```bash
# Conservative approach (recommended for unknown sites)
--concurrency 10 --jitter 0.5 1.0 --respect-robots

# Balanced performance (default settings)
--concurrency 20 --jitter 0.05 0.15

# Aggressive discovery (own sites only)
--concurrency 50 --jitter 0.01 0.05 --timeout 10
```

## Use Cases

### Security Research
- **Asset Discovery**: Map all accessible endpoints and resources
- **Attack Surface Analysis**: Identify potential entry points
- **Subdomain Enumeration**: Discover additional subdomains through links
- **Technology Fingerprinting**: Analyze URL patterns and structures

### Web Development  
- **Site Auditing**: Verify all pages are properly linked
- **SEO Analysis**: Check internal link structure and organization
- **Migration Planning**: Map existing site structure before changes
- **Performance Testing**: Identify pages for load testing

### Content Analysis
- **Information Architecture**: Understand site organization
- **Content Inventory**: Catalog all discoverable pages
- **Link Analysis**: Study internal linking patterns
- **Accessibility Auditing**: Find all user-accessible content

## Output and Integration

### Console Output
```
INFO: Visiting (0): https://example.com
INFO: Visiting (1): https://example.com/about  
INFO: Visiting (1): https://example.com/products
INFO: Visiting (2): https://example.com/products/software
INFO: Crawl finished. Visited=347
```

### File Output Format
When using `--out filename.txt`, URLs are saved one per line, sorted alphabetically:
```
https://example.com
https://example.com/about
https://example.com/contact
https://example.com/products
https://example.com/products/software
```

### Programmatic Integration
```python
from pathfinder import Crawler
import asyncio

async def main():
    crawler = Crawler(
        start_url="https://example.com",
        max_depth=2,
        max_pages=500,
        respect_robots=True,
        concurrency=10
    )
    
    await crawler.run()
    
    print(f"Discovered {len(crawler.visited)} unique URLs")
    for url in sorted(crawler.visited):
        print(url)

if __name__ == "__main__":
    asyncio.run(main())
```

## Troubleshooting

### Common Issues and Solutions

#### Memory Usage Growth
**Problem**: High memory consumption during large crawls  
**Solutions**:
- Reduce `--max-body-bytes` (try 2000000 for 2MB limit)
- Lower `--concurrency` to reduce simultaneous processing
- Use `--max-pages` to limit total discovery

#### Rate Limiting (HTTP 429)
**Problem**: Target server returning "Too Many Requests"  
**Solutions**:
- Reduce `--concurrency` (try 5-10)
- Increase `--jitter` delays (try 0.5 1.0)
- Enable `--respect-robots` for server-specified delays

#### SSL/TLS Errors
**Problem**: Certificate verification failures  
**Solutions**:
- Use `--insecure` for testing (not recommended for production)
- Check target site's SSL configuration
- Update system certificate store

#### Limited Discovery Results
**Problem**: Fewer URLs found than expected  
**Diagnosis Steps**:
- Verify `--include`/`--exclude` patterns aren't too restrictive
- Check if `--https-only` is filtering HTTP links
- Increase `--max-depth` parameter
- Review target site's link structure manually

### Debug Mode
Enable verbose logging for detailed troubleshooting:
```bash
python pathfinder.py https://example.com 2 --log DEBUG --max-pages 50
```

### Performance Monitoring
Track crawler performance and resource usage:
```bash
# Monitor execution time
time python pathfinder.py https://example.com 2 --max-pages 1000

# Watch resource usage (Linux/macOS)
watch -n 2 'ps aux | grep pathfinder | head -5'
```

## Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Write tests for new functionality
4. Ensure code follows PEP 8 style guidelines
5. Submit a pull request with clear description

### Development Setup
```bash
git clone https://github.com/5u5urrus/PathFinder.git
cd PathFinder
pip install aiohttp beautifulsoup4 lxml pytest pytest-asyncio flake8
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Responsible Use

PathFinder is designed for legitimate security research, web development, and analysis purposes. Users must:

- **Obtain Authorization**: Only crawl websites you own or have explicit permission to test
- **Respect Server Resources**: Use appropriate rate limiting and concurrency settings
- **Follow robots.txt**: Use `--respect-robots` when crawling third-party sites
- **Comply with Terms of Service**: Respect website terms of use and legal requirements
- **Use Ethical Practices**: Do not use this tool for unauthorized access or malicious activities

**Disclaimer**: The authors assume no responsibility for misuse of this software. Users are solely responsible for ensuring their activities comply with applicable laws and regulations.
