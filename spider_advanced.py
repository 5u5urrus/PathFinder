#!/usr/bin/env python3
"""
Advanced Spider Features - Sitemap support, export formats, and filters
"""

import xml.etree.ElementTree as ET
import csv
import asyncio
import aiohttp
from typing import List, Dict, Optional, Set
from urllib.parse import urlparse
import gzip
from io import BytesIO

from spider import WebSpider


class AdvancedWebSpider(WebSpider):
    """
    Extended spider with advanced features:
    - Sitemap.xml support
    - Multiple export formats (CSV, JSON Lines)
    - Content filtering
    - Link following patterns
    """
    
    def __init__(self, *args, follow_patterns: Optional[List[str]] = None, 
                 exclude_patterns: Optional[List[str]] = None,
                 min_content_length: int = 100,
                 export_format: str = 'json', **kwargs):
        """
        Initialize advanced spider with additional options.
        
        Args:
            follow_patterns: List of regex patterns for URLs to follow
            exclude_patterns: List of regex patterns for URLs to exclude
            min_content_length: Minimum content length to save page
            export_format: Export format ('json', 'csv', 'jsonl')
        """
        super().__init__(*args, **kwargs)
        
        self.follow_patterns = follow_patterns or []
        self.exclude_patterns = exclude_patterns or []
        self.min_content_length = min_content_length
        self.export_format = export_format
        
        # Compile regex patterns
        import re
        self.follow_regex = [re.compile(p) for p in self.follow_patterns]
        self.exclude_regex = [re.compile(p) for p in self.exclude_patterns]
        
        # CSV writer setup
        if self.export_format == 'csv':
            self.csv_file = open(f"{self.output_dir}/crawled_data.csv", 'w', newline='', encoding='utf-8')
            self.csv_writer = csv.DictWriter(
                self.csv_file,
                fieldnames=['url', 'title', 'meta_description', 'content_length', 'timestamp']
            )
            self.csv_writer.writeheader()
    
    async def discover_sitemaps(self, base_url: str) -> List[str]:
        """Discover and parse sitemap URLs from robots.txt and common locations."""
        sitemap_urls = []
        parsed = urlparse(base_url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        
        # Check robots.txt for sitemap
        robots_parser = await self.get_robots_parser(base_url)
        if robots_parser and hasattr(robots_parser, 'site_maps'):
            sitemap_urls.extend(robots_parser.site_maps() or [])
        
        # Check common sitemap locations
        common_sitemaps = [
            f"{base}/sitemap.xml",
            f"{base}/sitemap.xml.gz",
            f"{base}/sitemap_index.xml",
            f"{base}/sitemap-index.xml"
        ]
        
        for sitemap_url in common_sitemaps:
            if await self.check_sitemap_exists(sitemap_url):
                sitemap_urls.append(sitemap_url)
        
        return list(set(sitemap_urls))
    
    async def check_sitemap_exists(self, url: str) -> bool:
        """Check if a sitemap URL exists."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(url, timeout=10) as response:
                    return response.status == 200
        except:
            return False
    
    async def parse_sitemap(self, sitemap_url: str) -> List[str]:
        """Parse a sitemap and extract URLs."""
        urls = []
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(sitemap_url, timeout=30) as response:
                    if response.status == 200:
                        content = await response.read()
                        
                        # Handle gzipped sitemaps
                        if sitemap_url.endswith('.gz'):
                            content = gzip.decompress(content)
                        
                        # Parse XML
                        root = ET.fromstring(content)
                        
                        # Handle sitemap index
                        if 'sitemapindex' in root.tag:
                            # This is a sitemap index, recursively parse child sitemaps
                            for sitemap in root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}loc'):
                                child_urls = await self.parse_sitemap(sitemap.text)
                                urls.extend(child_urls)
                        else:
                            # Regular sitemap with URLs
                            for url in root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}loc'):
                                if url.text:
                                    urls.append(url.text)
                        
                        self.logger.info(f"Found {len(urls)} URLs in sitemap: {sitemap_url}")
                        
        except Exception as e:
            self.logger.error(f"Error parsing sitemap {sitemap_url}: {e}")
        
        return urls
    
    def should_follow_url(self, url: str) -> bool:
        """Check if URL matches follow/exclude patterns."""
        # First check parent class validation
        if not super().is_valid_url(url):
            return False
        
        # Check exclude patterns
        for pattern in self.exclude_regex:
            if pattern.search(url):
                return False
        
        # If follow patterns are specified, URL must match at least one
        if self.follow_regex:
            return any(pattern.search(url) for pattern in self.follow_regex)
        
        return True
    
    def is_valid_url(self, url: str) -> bool:
        """Override to use pattern matching."""
        return self.should_follow_url(url)
    
    def should_save_content(self, content: Dict) -> bool:
        """Determine if content should be saved based on filters."""
        # Check minimum content length
        if len(content.get('text', '')) < self.min_content_length:
            return False
        
        return True
    
    def save_content(self, content: Dict, url: str):
        """Save content in specified format."""
        if not self.should_save_content(content):
            return
        
        if self.export_format == 'json':
            super().save_content(content, url)
        elif self.export_format == 'csv':
            # Save to CSV
            row = {
                'url': content['url'],
                'title': content['title'],
                'meta_description': content['meta_description'],
                'content_length': len(content['text']),
                'timestamp': content['timestamp']
            }
            self.csv_writer.writerow(row)
        elif self.export_format == 'jsonl':
            # JSON Lines format
            import json
            jsonl_file = f"{self.output_dir}/crawled_data.jsonl"
            with open(jsonl_file, 'a', encoding='utf-8') as f:
                json.dump(content, f, ensure_ascii=False)
                f.write('\n')
    
    async def crawl(self) -> None:
        """Extended crawl method with sitemap support."""
        self.stats['start_time'] = datetime.now()
        
        # Discover and parse sitemaps
        all_sitemap_urls = []
        for start_url in self.start_urls:
            sitemap_urls = await self.discover_sitemaps(start_url)
            for sitemap_url in sitemap_urls:
                urls = await self.parse_sitemap(sitemap_url)
                all_sitemap_urls.extend(urls)
        
        # Add sitemap URLs to queue with priority
        for url in all_sitemap_urls:
            normalized_url = self.normalize_url(url)
            if self.should_follow_url(normalized_url) and normalized_url not in self.visited_urls:
                self.url_queue.appendleft(normalized_url)  # Add to front of queue
                self.url_depths[normalized_url] = 1
        
        # Continue with normal crawling
        await super().crawl()
        
        # Close CSV file if used
        if self.export_format == 'csv' and hasattr(self, 'csv_file'):
            self.csv_file.close()
    
    def extract_structured_data(self, html: str, url: str) -> Dict:
        """Extract structured data (JSON-LD, microdata) from HTML."""
        from bs4 import BeautifulSoup
        import json
        
        soup = BeautifulSoup(html, 'lxml')
        structured_data = {
            'json_ld': [],
            'microdata': {}
        }
        
        # Extract JSON-LD
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                structured_data['json_ld'].append(data)
            except:
                pass
        
        # Extract basic microdata
        for item in soup.find_all(attrs={'itemscope': True}):
            item_type = item.get('itemtype', 'Unknown')
            props = {}
            for prop in item.find_all(attrs={'itemprop': True}):
                prop_name = prop.get('itemprop')
                prop_value = prop.get('content') or prop.get_text(strip=True)
                props[prop_name] = prop_value
            structured_data['microdata'][item_type] = props
        
        return structured_data
    
    def extract_content(self, html: str, url: str) -> Dict:
        """Extended content extraction with structured data."""
        content = super().extract_content(html, url)
        
        # Add structured data
        content['structured_data'] = self.extract_structured_data(html, url)
        
        return content


# Import datetime for the crawl method
from datetime import datetime


if __name__ == "__main__":
    # Example with advanced features
    spider = AdvancedWebSpider(
        start_urls=["https://example.com"],
        max_depth=3,
        max_pages=100,
        follow_patterns=[r'/blog/', r'/news/'],
        exclude_patterns=[r'/tag/', r'/category/'],
        min_content_length=500,
        export_format='csv'
    )
    spider.run()