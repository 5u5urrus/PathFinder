# Web Spider - Effective Web Crawling Tool

A powerful, asynchronous web spider built with Python that respects robots.txt, implements intelligent crawling strategies, and provides comprehensive data extraction capabilities.

## Features

- **Asynchronous Crawling**: High-performance concurrent crawling using `aiohttp`
- **Robots.txt Compliance**: Automatically fetches and respects robots.txt rules
- **Intelligent URL Management**: 
  - URL normalization to avoid duplicates
  - Depth-based crawling control
  - Domain restriction options
- **Content Extraction**:
  - Page title and text content
  - Meta descriptions and keywords
  - Headers (H1-H6) extraction
  - Image URLs with alt text
- **Rate Limiting**: Configurable delays between requests
- **Progress Tracking**: Real-time crawling statistics and colored output
- **Flexible Configuration**: CLI options and JSON config file support
- **Data Storage**: Saves crawled content as structured JSON files

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd web-spider
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Basic Usage

Crawl a single website:
```bash
python spider_cli.py crawl https://example.com
```

Crawl multiple websites:
```bash
python spider_cli.py crawl https://example.com https://example.org
```

### Command Line Options

```bash
python spider_cli.py crawl [URLs] [OPTIONS]

Options:
  -d, --max-depth INTEGER       Maximum crawl depth (default: 3)
  -p, --max-pages INTEGER       Maximum pages to crawl (default: 100)
  -t, --delay FLOAT            Delay between requests in seconds (default: 0.5)
  --same-domain / --any-domain  Restrict to same domain (default: True)
  -u, --user-agent TEXT        User agent string
  -o, --output-dir TEXT        Output directory (default: spider_output)
  -e, --allowed-extensions TEXT Allowed file extensions (can use multiple times)
  -c, --config PATH            Load configuration from JSON file
  --help                       Show this message and exit
```

### Examples

1. **Crawl with custom depth and page limit**:
```bash
python spider_cli.py crawl https://example.com -d 2 -p 50
```

2. **Crawl across domains**:
```bash
python spider_cli.py crawl https://example.com --any-domain -p 100
```

3. **Specify allowed file extensions**:
```bash
python spider_cli.py crawl https://example.com -e .html -e .htm -e .php
```

4. **Use custom output directory**:
```bash
python spider_cli.py crawl https://example.com -o my_crawl_data
```

### Using Configuration Files

1. **Generate a sample configuration**:
```bash
python spider_cli.py generate-config -o my_config.json
```

2. **Edit the configuration file** (my_config.json):
```json
{
  "urls": ["https://example.com", "https://example.org"],
  "max_depth": 3,
  "max_pages": 100,
  "delay": 0.5,
  "same_domain": true,
  "user_agent": "WebSpider/1.0",
  "output_dir": "spider_output",
  "allowed_extensions": [".html", ".htm", ".php", ".asp", ".aspx"]
}
```

3. **Run with configuration**:
```bash
python spider_cli.py crawl -c my_config.json
```

### Analyzing Crawled Data

View statistics about your crawl:
```bash
python spider_cli.py analyze spider_output
```

## Output Format

Each crawled page is saved as a JSON file with the following structure:

```json
{
  "url": "https://example.com/page",
  "title": "Page Title",
  "text": "Full text content of the page...",
  "meta_description": "Page meta description",
  "meta_keywords": "keyword1, keyword2",
  "headers": {
    "h1": ["Main Heading"],
    "h2": ["Subheading 1", "Subheading 2"]
  },
  "images": [
    {
      "src": "https://example.com/image.jpg",
      "alt": "Image description",
      "title": "Image title"
    }
  ],
  "timestamp": "2024-01-20T10:30:00"
}
```

## Direct Python Usage

You can also use the spider directly in Python:

```python
from spider import WebSpider

# Create spider instance
spider = WebSpider(
    start_urls=["https://example.com"],
    max_depth=3,
    max_pages=100,
    delay=0.5,
    same_domain=True,
    user_agent="MyBot/1.0",
    output_dir="my_output"
)

# Run the spider
spider.run()
```

## Advanced Features

### Custom User Agent
Set a custom user agent to identify your crawler:
```bash
python spider_cli.py crawl https://example.com -u "MyBot/1.0 (+https://mysite.com/bot)"
```

### Rate Limiting
Adjust the delay between requests to be respectful to servers:
```bash
python spider_cli.py crawl https://example.com -t 2.0  # 2 second delay
```

### Domain Restrictions
- `--same-domain` (default): Only crawl pages on the same domain as start URLs
- `--any-domain`: Follow links to any domain (be careful with this!)

## Best Practices

1. **Respect robots.txt**: The spider automatically checks robots.txt files
2. **Use appropriate delays**: Don't overwhelm servers with rapid requests
3. **Limit crawl scope**: Use max_depth and max_pages to control crawl size
4. **Check your user agent**: Identify your bot properly
5. **Monitor output size**: Large crawls can generate significant data

## Troubleshooting

### Common Issues

1. **"Connection refused" errors**: 
   - The website may be blocking automated requests
   - Try using a different user agent
   - Increase the delay between requests

2. **"Too many open files" error**:
   - The spider limits concurrent connections, but you may need to increase system limits
   - On Linux/Mac: `ulimit -n 4096`

3. **Memory usage with large crawls**:
   - Use smaller max_pages values
   - Process data in batches

## Contributing

Feel free to submit issues, fork the repository, and create pull requests for any improvements.

## License

This project is open source and available under the MIT License.