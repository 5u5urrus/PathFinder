# PathFinder - Fast Web Spider in Go

[![Go Version](https://img.shields.io/badge/go-1.19%2B-blue.svg)](https://golang.org/dl/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Windows%20%7C%20macOS-lightgrey.svg)]()

<p align="center">
  <img src="pathfinder.png" width="100%" alt="PathFinder Banner">
</p>

PathFinder is a high-performance web crawler written in Go, designed for security researchers, penetration testers, and bug bounty hunters. It efficiently discovers URLs, JavaScript files, API endpoints, and hidden paths through intelligent crawling and JavaScript analysis.

## Table of Contents
- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Command Reference](#command-reference)
- [Advanced Usage](#advanced-usage)
- [Discovery Features](#discovery-features)
- [Output Filtering](#output-filtering)
- [Third-Party Sources](#third-party-sources)
- [Headless Rendering](#headless-rendering)
- [Performance Tuning](#performance-tuning)
- [Output Formats](#output-formats)
- [Use Cases](#use-cases)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## Features

### 🚀 High-Performance Crawling
- **Concurrent Architecture**: Fast async crawling with configurable parallelism
- **Smart Scope Management**: Automatic subdomain detection for bare domains
- **Intelligent Deduplication**: URL canonicalization prevents redundant requests
- **Memory Optimized**: Efficient handling of large sites with 4MB body size limits

### 🔍 Advanced Discovery
- **JavaScript Analysis**: Built-in LinkFinder extracts endpoints from JS files
- **HTML Parsing**: Discovers links, forms, upload forms, and script sources
- **Subdomain Extraction**: Finds subdomains mentioned in page content
- **AWS S3 Detection**: Identifies S3 bucket URLs and endpoints
- **Source Maps**: Automatically tries to fetch `.js.map` files

### 🌐 Multiple Data Sources
- **Wayback Machine**: Historical URL discovery with latest snapshots
- **CommonCrawl**: Automatically queries most recent web crawl indices
- **VirusTotal**: Integration for known malicious/interesting URLs
- **AlienVault OTX**: Threat intelligence URL discovery

### 🎭 Optional Headless Rendering
- **SPA Support**: Renders JavaScript-heavy single-page applications
- **Network Monitoring**: Captures XHR/Fetch requests from dynamic content
- **Resource Blocking**: Blocks images/CSS/fonts for faster rendering
- **Budget Control**: Configurable page limits to control resource usage

### 🎯 Flexible Filtering
- **Output Type Selection**: Choose which discoveries to emit (URLs, JS, forms, etc.)
- **Regex Patterns**: Whitelist/blacklist URLs with powerful regex filters
- **Length Filtering**: Ignore responses with specific body lengths
- **Scope Control**: Include/exclude subdomains with granular control

### 🛠️ Professional Features
- **robots.txt Parsing**: Discovers additional paths from robots.txt
- **Sitemap Crawling**: Extracts URLs from XML sitemaps
- **Custom Headers**: Set cookies, user-agents, and custom headers
- **Burp Integration**: Import headers from Burp Suite raw requests
- **Proxy Support**: Route traffic through HTTP/SOCKS proxies

## Installation

### Prerequisites
- Go 1.19 or higher
- For headless rendering: Chrome/Chromium installed

### Install from Source
```bash
git clone https://github.com/5u5urrus/PathFinder.git
cd PathFinder
go build -o pathfinder
```

### Build with Headless Support
```bash
# Build with Chrome rendering capabilities
go build -tags headless -o pathfinder
```

### Build without Headless (smaller binary)
```bash
# Standard build (no Chrome dependency)
go build -o pathfinder
```

## Quick Start

### Basic Site Crawling
```bash
# Crawl a full URL (exact domain only)
./pathfinder -s https://example.com -d 2

# Crawl a bare domain (auto-includes subdomains)
./pathfinder -s example.com -d 2
```

### Security Research Mode
```bash
# Comprehensive discovery with third-party sources
./pathfinder -s target.com -d 3 --other-source --sitemap --js -o output/
```

### Quick URL Extraction
```bash
# Quiet mode - URLs only
./pathfinder -s https://example.com -d 2 -q
```

### With Headless Rendering
```bash
# Enable JavaScript rendering for SPAs
./pathfinder -s https://app.example.com -d 2 --render --render-budget 10
```

## Command Reference

```bash
pathfinder -s <target> [options]
```

### Target Input
| Flag | Description | Example |
|------|-------------|---------|
| `-s, --site URL` | Single target URL or domain | `-s example.com` |
| `-S, --sites FILE` | File with multiple targets | `-S targets.txt` |
| stdin | Pipe targets from stdin | `echo "example.com" \| pathfinder` |

### Crawling Control
| Flag | Description | Default |
|------|-------------|---------|
| `-d, --depth N` | Maximum crawl depth (0 = infinite) | 1 |
| `-c, --concurrent N` | Concurrent requests per domain | 5 |
| `-t, --threads N` | Number of parallel target threads | 1 |
| `--subs` | Include subdomains (auto for bare domains) | false |
| `-k, --delay SECS` | Fixed delay between requests | 0 |
| `-K, --random-delay SECS` | Random delay (0-N seconds) | 0 |

### Discovery Options
| Flag | Description | Default |
|------|-------------|---------|
| `--js` | Enable LinkFinder for JavaScript | true |
| `--sitemap` | Crawl sitemap.xml | false |
| `--robots` | Parse robots.txt | true |
| `-a, --other-source` | Query Wayback/CommonCrawl/VT/OTX | false |
| `-w, --include-subs` | Include subs in 3rd-party queries | false |
| `-r, --include-other-source` | Print 3rd-party URLs | false |
| `-B, --base` | Disable sitemap/robots/JS/3rd-party | false |

### Headless Rendering
| Flag | Description | Default |
|------|-------------|---------|
| `--render` | Enable headless Chrome rendering | false |
| `--render-budget N` | Max pages to render per domain | 6 |
| `--render-timeout SECS` | Timeout per rendered page | 8 |

### Filtering & Scope
| Flag | Description | Example |
|------|-------------|---------|
| `--whitelist REGEX` | Only crawl matching URLs | `--whitelist "\.example\.com"` |
| `--blacklist REGEX` | Exclude matching URLs | `--blacklist "/(admin\|api)/"` |
| `--whitelist-domain DOMAIN` | Override auto-scope | `--whitelist-domain example.com` |
| `-L, --filter-length CSV` | Ignore specific body lengths | `-L "0,1234,5678"` |

### Output Control
| Flag | Description | Example |
|------|-------------|---------|
| `-o, --output DIR` | Save results to directory | `-o results/` |
| `-q, --quiet` | Only print URLs | `-q` |
| `--json` | JSON output format | `--json` |
| `-l, --length` | Include response lengths | `-l` |
| `-R, --raw` | Print raw response bodies | `-R` |
| `--types CSV` | Only emit specific types | `--types url,javascript` |
| `--exclude-types CSV` | Suppress specific types | `--exclude-types form,upload-form` |

### Authentication & Headers
| Flag | Description | Example |
|------|-------------|---------|
| `--cookie STRING` | Set cookies | `--cookie "session=abc123"` |
| `-H, --header KEY:VAL` | Custom headers (multiple allowed) | `-H "Authorization: Bearer token"` |
| `--burp FILE` | Load headers from Burp raw request | `--burp request.txt` |
| `-u, --user-agent TYPE` | UA (web/mobi/custom) | `-u mobi` |

### Network Options
| Flag | Description | Default |
|------|-------------|---------|
| `-p, --proxy URL` | HTTP/SOCKS proxy | none |
| `-m, --timeout SECS` | Request timeout | 10 |
| `--no-redirect` | Block off-scope redirects | false |

### Debugging
| Flag | Description | Default |
|------|-------------|---------|
| `-v, --verbose` | Verbose logging | false |
| `--debug` | Debug logging | false |
| `--version` | Print version | - |

## Advanced Usage

### Targeted Discovery
```bash
# Focus on API endpoints
pathfinder -s api.example.com -d 2 --whitelist "/api/v[0-9]" --types url,javascript

# Exclude administrative paths
pathfinder -s example.com -d 3 --blacklist "/(admin|wp-admin|login)" -q

# JavaScript-heavy applications
pathfinder -s app.example.com -d 2 --render --render-budget 15 --types url,network,render
```

### Authentication Scenarios
```bash
# Cookie-based authentication
pathfinder -s https://example.com -d 2 --cookie "session=xyz123; token=abc"

# Custom headers
pathfinder -s https://api.example.com -d 2 \
  -H "Authorization: Bearer token123" \
  -H "X-API-Key: secret"

# Import from Burp Suite
pathfinder -s https://example.com -d 2 --burp authenticated-request.txt
```

### Third-Party Intelligence
```bash
# Historical URL discovery
pathfinder -s example.com --other-source --include-other-source -q > historical_urls.txt

# Include subdomains in archive search
pathfinder -s example.com --other-source --include-subs -d 2

# With VirusTotal (requires VT_API_KEY env var)
export VT_API_KEY="your-api-key"
pathfinder -s example.com --other-source -d 1
```

### Output Filtering
```bash
# Only JavaScript files
pathfinder -s example.com -d 2 --types javascript -q

# URLs and network requests from rendering
pathfinder -s example.com -d 2 --render --types url,network,render

# Everything except forms
pathfinder -s example.com -d 3 --exclude-types form,upload-form

# Available types: url, href, javascript, linkfinder, form, upload-form, 
#                  robots, sitemap, subdomains, aws, render, network
```

### Performance Optimization
```bash
# High-speed crawling (use carefully)
pathfinder -s example.com -d 2 -c 50 -K 0.1 -m 5

# Respectful crawling
pathfinder -s example.com -d 3 -c 5 -k 1 --robots

# Multiple targets in parallel
pathfinder -S targets.txt -t 5 -c 10 -d 2 -o results/
```

## Discovery Features

### Automatic Scope Detection
PathFinder intelligently handles scope based on input format:

**Bare Domain Input** (e.g., `example.com`):
- Automatically starts at `https://example.com`
- Includes all subdomains: `*.example.com`
- Uses eTLD+1 for scope (handles `dzo.com.ua` correctly)

**Full URL Input** (e.g., `https://www.example.com`):
- Starts at exact URL provided
- Respects `--subs` flag for subdomain inclusion
- Traditional behavior

### JavaScript Analysis
The built-in LinkFinder regex extracts:
- API endpoints from AJAX calls
- Relative and absolute URLs
- File paths and resources
- Template URLs and routes

**Noise Filtering:**
- MIME types (application/json, text/plain)
- Date patterns (MM/DD/YYYY)
- Template variables ({{var}}, /:param)
- Common false positives

### Third-Party Sources

#### Wayback Machine
- Queries the latest CDX snapshot
- Uses `matchType=domain` for bare domains
- Provides historical URL coverage

#### CommonCrawl
- Automatically fetches latest index (2024+)
- Queries most recent web crawl
- No hardcoded outdated indices

#### VirusTotal
- Requires `VT_API_KEY` environment variable
- Discovers URLs flagged in security scans

#### AlienVault OTX
- Threat intelligence URLs
- No API key required
- Limited to 10 pages per domain

## Output Filtering

### Output Types Reference

| Type | Description | Example |
|------|-------------|---------|
| `url` | All discovered URLs | `[url] - [code-200] - https://example.com/path` |
| `href` | Links from `<a>` and `<link>` tags | `[href] - https://example.com/about` |
| `javascript` | JS/JSON/XML files | `[javascript] - https://cdn.example.com/app.js` |
| `linkfinder` | URLs extracted from JS | `[linkfinder] - https://api.example.com/v1/users` |
| `form` | Form action URLs | `[form] - https://example.com/submit` |
| `upload-form` | File upload forms | `[upload-form] - https://example.com/upload` |
| `robots` | URLs from robots.txt | `[robots] - https://example.com/admin` |
| `sitemap` | URLs from sitemap.xml | `[sitemap] - https://example.com/post/123` |
| `subdomains` | Discovered subdomains | `[subdomains] - https://api.example.com` |
| `aws` | AWS S3 buckets | `[aws-s3] - bucket.s3.amazonaws.com` |
| `render` | Pages rendered with Chrome | `[render] - https://app.example.com` |
| `network` | XHR/Fetch from rendering | `[network] - https://api.example.com/data` |

### Filtering Examples
```bash
# Only show discovered endpoints (no JS files)
pathfinder -s example.com --types url,linkfinder,network -q

# JavaScript files only
pathfinder -s example.com --types javascript -q > js_files.txt

# Everything except subdomains
pathfinder -s example.com --exclude-types subdomains

# API endpoints from rendering
pathfinder -s app.example.com --render --types network,linkfinder
```

## Headless Rendering

### When to Use Rendering

**Enable `--render` for:**
- Single-Page Applications (React, Vue, Angular)
- Heavily JavaScript-driven sites
- Sites with lazy-loaded content
- AJAX-heavy applications

**Skip rendering for:**
- Static HTML sites
- Server-rendered pages
- Performance-critical scans
- Large-scale crawls

### Rendering Behavior

PathFinder selectively renders pages using these heuristics:
1. **Start URL**: Always rendered
2. **Small HTML responses**: Pages <60KB (likely SPA shells)
3. **Budget limit**: Stops after N pages (default: 6)

**What gets blocked during rendering:**
- Images (PNG, JPG, GIF, etc.)
- Stylesheets (CSS)
- Fonts (WOFF, TTF, etc.)
- Media files (video, audio)

**What gets captured:**
- XHR requests (AJAX calls)
- Fetch API calls
- Dynamically loaded scripts
- Client-side routing

### Rendering Examples
```bash
# Basic SPA crawling
pathfinder -s https://app.example.com --render

# Aggressive rendering (more pages)
pathfinder -s https://app.example.com --render --render-budget 20 --render-timeout 12

# Render + traditional crawling
pathfinder -s https://app.example.com -d 3 --render --js --sitemap
```

## Performance Tuning

### Concurrency Guidelines

**Site Size Recommendations:**
- Small sites (<100 pages): `-c 5`
- Medium sites (100-1000 pages): `-c 10-20`
- Large sites (>1000 pages): `-c 30-50`
- Multiple targets: `-t 3-10` with `-c 10`

### Memory Management
PathFinder includes automatic memory protection:
- 4MB soft cap on response body scanning
- Streaming for large responses
- Efficient URL deduplication with sync.Map
- Automatic garbage collection

### Rate Limiting
```bash
# Conservative (recommended for unknown sites)
pathfinder -s example.com -c 5 -k 1 --robots

# Balanced (default)
pathfinder -s example.com -c 10 -K 0.2

# Aggressive (own sites only)
pathfinder -s example.com -c 50 -K 0.05 -m 5
```

### Optimizing for Large Crawls
```bash
# Disable heavy features
pathfinder -s example.com -d 3 -B -c 30

# Filter noise early
pathfinder -s example.com -d 2 --blacklist "\.(jpg|png|css|woff)" -c 25

# JSON output for processing
pathfinder -s example.com -d 2 --json -o results/ -c 20
```

## Output Formats

### Standard Output
```
INFO: Start crawling: https://example.com
[url] - [code-200] - https://example.com
[href] - https://example.com/about
[javascript] - https://cdn.example.com/app.js
[linkfinder] - https://api.example.com/v1/users
INFO: Done.
```

### Quiet Mode (`-q`)
```
https://example.com
https://example.com/about
https://api.example.com/v1/users
https://cdn.example.com/app.js
```

### JSON Output (`--json`)
```json
{"input":"https://example.com","source":"body","type":"url","output":"https://example.com","status":200,"length":15234}
{"input":"https://example.com","source":"body","type":"href","output":"https://example.com/about","status":0,"length":0}
{"input":"https://example.com","source":"body","type":"javascript","output":"https://cdn.example.com/app.js","status":0,"length":0}
```

### File Output
Results are saved to `output_dir/<hostname>.txt`:
```bash
pathfinder -s example.com -d 2 -o results/
# Creates: results/example_com.txt
```

Multiple targets create separate files:
```bash
pathfinder -S targets.txt -o results/
# Creates: results/example_com.txt, results/target_org.txt, etc.
```

## Use Cases

### Bug Bounty Hunting
```bash
# Comprehensive asset discovery
pathfinder -s target.com -d 3 --other-source --sitemap --js \
  --types url,javascript,subdomains -o recon/

# Find hidden API endpoints
pathfinder -s app.target.com --render --types network,linkfinder -q

# Historical endpoint discovery
pathfinder -s target.com --other-source --include-subs --include-other-source \
  | grep -i "api\|v1\|v2\|admin"
```

### Penetration Testing
```bash
# Full site mapping
pathfinder -s https://target.com -d 4 --robots --sitemap -o pentest/ -l

# Authenticated crawling
pathfinder -s https://target.com -d 2 --burp authenticated.txt -o authed/

# Find upload forms and admin paths
pathfinder -s target.com -d 3 --types form,upload-form | grep -i admin
```

### Web Development
```bash
# Verify site structure
pathfinder -s https://staging.example.com -d 3 --no-redirect -q > sitemap.txt

# Find broken internal links
pathfinder -s https://example.com -d 2 | grep "404\|500"

# Extract all JavaScript files
pathfinder -s https://example.com -d 2 --types javascript -q > js_inventory.txt
```

### Security Research
```bash
# Subdomain enumeration
pathfinder -s example.com -d 1 --types subdomains --other-source --include-subs

# S3 bucket discovery
pathfinder -s example.com -d 2 --types aws -q

# Technology fingerprinting
pathfinder -s example.com -d 2 --types javascript | grep -E "\.(min\.js|bundle\.js)"
```

## Troubleshooting

### Common Issues

#### No URLs Discovered
**Possible Causes:**
- Site uses JavaScript rendering (use `--render`)
- Filters too restrictive (check `--whitelist`/`--blacklist`)
- Depth too shallow (increase `-d`)
- Site blocks crawler UA (try `-u mobi` or custom UA)

**Solutions:**
```bash
# Try with rendering
pathfinder -s example.com --render -d 2

# Increase depth
pathfinder -s example.com -d 4

# Use mobile UA
pathfinder -s example.com -u mobi -d 2
```

#### Third-Party Sources Failing
**Symptoms:** No results from Wayback/CommonCrawl

**Solutions:**
```bash
# Enable debug logging
pathfinder -s example.com --other-source --debug

# Test connectivity
curl "https://web.archive.org/cdx/search/cdx?url=example.com&output=json&limit=10"

# Check if domain exists in archives
pathfinder -s example.com --other-source --include-other-source -q | head -20
```

#### Rate Limiting / 429 Errors
**Solutions:**
```bash
# Reduce concurrency
pathfinder -s example.com -c 3 -k 2

# Add random delays
pathfinder -s example.com -c 5 -K 1

# Respect robots.txt
pathfinder -s example.com --robots -c 5
```

#### SSL/Certificate Errors on Windows
**Solutions:**
```bash
# Update Go and rebuild
go get -u all
go build -o pathfinder.exe

# Check system certificates
certutil -store root

# For testing only (not recommended)
# Modify code to set InsecureSkipVerify: true
```

### Debug Mode
```bash
# Enable verbose logging
pathfinder -s example.com --debug -d 2

# Test single URL
pathfinder -s https://example.com/specific-page --debug

# Monitor with limited pages
pathfinder -s example.com --debug --max-pages 50
```

### Environment Variables
```bash
# VirusTotal API
export VT_API_KEY="your-virustotal-api-key"

# Set log level
export PATHFINDER_LOG=DEBUG

# Proxy (alternative to --proxy flag)
export HTTP_PROXY="http://localhost:8080"
export HTTPS_PROXY="http://localhost:8080"
```

## Contributing

Contributions are welcome! Here's how to get started:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes with clear commit messages
4. Test thoroughly on Linux, Windows, and macOS
5. Submit a pull request

### Development Setup
```bash
git clone https://github.com/5u5urrus/PathFinder.git
cd PathFinder
go mod download
go build -o pathfinder
```

### Running Tests
```bash
go test ./...
```

### Code Style
- Follow standard Go conventions
- Use `gofmt` for formatting
- Add comments for exported functions
- Keep functions focused and testable

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

PathFinder was inspired by the famous gospider - an excellent fast web crawling tool.

## Author

Created by **Vahe Demirkhanyan**  
Email: vahe@hackvector.io  
GitHub: [@5u5urrus](https://github.com/5u5urrus)

---

**⚠️ Responsible Use Disclaimer**

PathFinder is designed for legitimate security research, penetration testing, and web development purposes. Users must:

- Only crawl websites they own or have explicit permission to test
- Comply with applicable laws and terms of service
- Use appropriate rate limiting to avoid service disruption

The author assumes no responsibility for misuse of this software. Users are solely responsible for their actions.
