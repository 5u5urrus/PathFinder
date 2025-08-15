#!/usr/bin/env python3
"""
Web Spider - A comprehensive web crawling tool
"""

import asyncio
import aiohttp
import time
import logging
import json
import os
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser
from collections import deque
from typing import Set, Dict, List, Optional, Tuple
from datetime import datetime
import hashlib

from bs4 import BeautifulSoup
import validators
import tldextract
from colorama import Fore, Style, init

# Initialize colorama for colored output
init(autoreset=True)

class WebSpider:
    """
    An effective web spider with features including:
    - Asynchronous crawling for speed
    - Robots.txt compliance
    - URL deduplication
    - Content extraction
    - Rate limiting
    - Depth control
    - Domain restriction options
    """
    
    def __init__(self, 
                 start_urls: List[str],
                 max_depth: int = 3,
                 max_pages: int = 1000,
                 delay: float = 0.5,
                 same_domain: bool = True,
                 user_agent: str = "WebSpider/1.0",
                 output_dir: str = "spider_output",
                 allowed_extensions: Optional[Set[str]] = None):
        """
        Initialize the web spider.
        
        Args:
            start_urls: List of URLs to start crawling from
            max_depth: Maximum crawl depth
            max_pages: Maximum number of pages to crawl
            delay: Delay between requests (seconds)
            same_domain: Whether to restrict crawling to same domain
            user_agent: User agent string
            output_dir: Directory to save crawled data
            allowed_extensions: Set of allowed file extensions (e.g., {'.html', '.htm'})
        """
        self.start_urls = start_urls
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.delay = delay
        self.same_domain = same_domain
        self.user_agent = user_agent
        self.output_dir = output_dir
        self.allowed_extensions = allowed_extensions or {'.html', '.htm', '.php', '.asp', '.aspx', ''}
        
        # URL management
        self.visited_urls: Set[str] = set()
        self.url_queue: deque = deque()
        self.url_depths: Dict[str, int] = {}
        
        # Domain management
        self.allowed_domains: Set[str] = set()
        if self.same_domain:
            for url in start_urls:
                parsed = urlparse(url)
                self.allowed_domains.add(parsed.netloc)
        
        # Robots.txt parsers
        self.robots_parsers: Dict[str, RobotFileParser] = {}
        
        # Statistics
        self.stats = {
            'pages_crawled': 0,
            'pages_failed': 0,
            'total_bytes': 0,
            'start_time': None,
            'end_time': None
        }
        
        # Setup logging
        self.setup_logging()
        
        # Create output directory
        os.makedirs(self.output_dir, exist_ok=True)
        
    def setup_logging(self):
        """Setup logging configuration."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('spider.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger('WebSpider')
        
    def normalize_url(self, url: str) -> str:
        """Normalize URL to avoid duplicates."""
        parsed = urlparse(url.lower())
        # Remove fragment
        parsed = parsed._replace(fragment='')
        # Remove trailing slash from path
        if parsed.path.endswith('/') and len(parsed.path) > 1:
            parsed = parsed._replace(path=parsed.path.rstrip('/'))
        # Sort query parameters
        if parsed.query:
            query_params = sorted(parsed.query.split('&'))
            parsed = parsed._replace(query='&'.join(query_params))
        return urlunparse(parsed)
        
    def is_valid_url(self, url: str) -> bool:
        """Check if URL is valid for crawling."""
        if not validators.url(url):
            return False
            
        parsed = urlparse(url)
        
        # Check domain restriction
        if self.same_domain and parsed.netloc not in self.allowed_domains:
            return False
            
        # Check file extension
        path = parsed.path.lower()
        if path:
            # Get file extension
            ext = os.path.splitext(path)[1]
            if ext and ext not in self.allowed_extensions:
                return False
                
        # Skip certain URL patterns
        skip_patterns = ['mailto:', 'javascript:', 'tel:', '#']
        if any(url.startswith(pattern) for pattern in skip_patterns):
            return False
            
        return True
        
    async def get_robots_parser(self, base_url: str) -> Optional[RobotFileParser]:
        """Get or create robots.txt parser for a domain."""
        parsed = urlparse(base_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        
        if robots_url in self.robots_parsers:
            return self.robots_parsers[robots_url]
            
        parser = RobotFileParser()
        parser.set_url(robots_url)
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(robots_url, timeout=10) as response:
                    if response.status == 200:
                        content = await response.text()
                        parser.parse(content.splitlines())
                        self.robots_parsers[robots_url] = parser
                        return parser
        except Exception as e:
            self.logger.warning(f"Failed to fetch robots.txt from {robots_url}: {e}")
            
        return None
        
    def can_fetch(self, url: str, robots_parser: Optional[RobotFileParser]) -> bool:
        """Check if URL can be fetched according to robots.txt."""
        if not robots_parser:
            return True
        try:
            return robots_parser.can_fetch(self.user_agent, url)
        except:
            return True
            
    def extract_links(self, html: str, base_url: str) -> List[str]:
        """Extract all links from HTML content."""
        soup = BeautifulSoup(html, 'lxml')
        links = []
        
        for tag in soup.find_all(['a', 'link']):
            href = tag.get('href')
            if href:
                # Convert relative URLs to absolute
                absolute_url = urljoin(base_url, href)
                normalized_url = self.normalize_url(absolute_url)
                if self.is_valid_url(normalized_url):
                    links.append(normalized_url)
                    
        return links
        
    def extract_content(self, html: str, url: str) -> Dict:
        """Extract useful content from HTML."""
        soup = BeautifulSoup(html, 'lxml')
        
        # Remove script and style elements
        for script in soup(['script', 'style']):
            script.decompose()
            
        content = {
            'url': url,
            'title': soup.title.string if soup.title else '',
            'text': soup.get_text(separator=' ', strip=True),
            'meta_description': '',
            'meta_keywords': '',
            'headers': {},
            'images': [],
            'timestamp': datetime.now().isoformat()
        }
        
        # Extract meta tags
        for meta in soup.find_all('meta'):
            if meta.get('name') == 'description':
                content['meta_description'] = meta.get('content', '')
            elif meta.get('name') == 'keywords':
                content['meta_keywords'] = meta.get('content', '')
                
        # Extract headers
        for i in range(1, 7):
            headers = soup.find_all(f'h{i}')
            if headers:
                content['headers'][f'h{i}'] = [h.get_text(strip=True) for h in headers]
                
        # Extract images
        for img in soup.find_all('img'):
            img_data = {
                'src': urljoin(url, img.get('src', '')),
                'alt': img.get('alt', ''),
                'title': img.get('title', '')
            }
            content['images'].append(img_data)
            
        return content
        
    def save_content(self, content: Dict, url: str):
        """Save extracted content to file."""
        # Create filename from URL
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        parsed = urlparse(url)
        filename = f"{parsed.netloc}_{url_hash}.json"
        filepath = os.path.join(self.output_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(content, f, indent=2, ensure_ascii=False)
            
    async def crawl_page(self, session: aiohttp.ClientSession, url: str, depth: int) -> None:
        """Crawl a single page."""
        if url in self.visited_urls or self.stats['pages_crawled'] >= self.max_pages:
            return
            
        self.visited_urls.add(url)
        self.stats['pages_crawled'] += 1
        
        # Log progress
        print(f"{Fore.GREEN}[{self.stats['pages_crawled']}/{self.max_pages}] Crawling: {url} (depth: {depth}){Style.RESET_ALL}")
        
        try:
            # Check robots.txt
            robots_parser = await self.get_robots_parser(url)
            if not self.can_fetch(url, robots_parser):
                self.logger.info(f"Robots.txt disallows: {url}")
                return
                
            # Fetch the page
            headers = {'User-Agent': self.user_agent}
            async with session.get(url, headers=headers, timeout=30) as response:
                if response.status == 200:
                    html = await response.text()
                    self.stats['total_bytes'] += len(html.encode())
                    
                    # Extract and save content
                    content = self.extract_content(html, url)
                    self.save_content(content, url)
                    
                    # Extract links and add to queue
                    if depth < self.max_depth:
                        links = self.extract_links(html, url)
                        for link in links:
                            if link not in self.visited_urls and link not in self.url_depths:
                                self.url_queue.append(link)
                                self.url_depths[link] = depth + 1
                                
                else:
                    self.logger.warning(f"HTTP {response.status} for {url}")
                    self.stats['pages_failed'] += 1
                    
        except asyncio.TimeoutError:
            self.logger.error(f"Timeout while crawling {url}")
            self.stats['pages_failed'] += 1
        except Exception as e:
            self.logger.error(f"Error crawling {url}: {e}")
            self.stats['pages_failed'] += 1
            
        # Rate limiting
        await asyncio.sleep(self.delay)
        
    async def crawl(self) -> None:
        """Main crawling loop."""
        self.stats['start_time'] = datetime.now()
        
        # Initialize queue with start URLs
        for url in self.start_urls:
            normalized_url = self.normalize_url(url)
            if self.is_valid_url(normalized_url):
                self.url_queue.append(normalized_url)
                self.url_depths[normalized_url] = 0
                
        # Create session with connection pooling
        connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
        timeout = aiohttp.ClientTimeout(total=300)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            while self.url_queue and self.stats['pages_crawled'] < self.max_pages:
                # Process URLs in batches
                batch_size = min(5, len(self.url_queue))
                tasks = []
                
                for _ in range(batch_size):
                    if self.url_queue:
                        url = self.url_queue.popleft()
                        depth = self.url_depths.get(url, 0)
                        task = self.crawl_page(session, url, depth)
                        tasks.append(task)
                        
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                    
        self.stats['end_time'] = datetime.now()
        
    def print_statistics(self):
        """Print crawling statistics."""
        duration = (self.stats['end_time'] - self.stats['start_time']).total_seconds()
        
        print(f"\n{Fore.CYAN}{'='*50}")
        print(f"Crawling Statistics")
        print(f"{'='*50}{Style.RESET_ALL}")
        print(f"Pages crawled: {Fore.GREEN}{self.stats['pages_crawled']}{Style.RESET_ALL}")
        print(f"Pages failed: {Fore.RED}{self.stats['pages_failed']}{Style.RESET_ALL}")
        print(f"Total data: {Fore.YELLOW}{self.stats['total_bytes'] / 1024 / 1024:.2f} MB{Style.RESET_ALL}")
        print(f"Duration: {Fore.BLUE}{duration:.2f} seconds{Style.RESET_ALL}")
        print(f"Pages/second: {Fore.MAGENTA}{self.stats['pages_crawled'] / duration:.2f}{Style.RESET_ALL}")
        print(f"Output directory: {Fore.CYAN}{self.output_dir}{Style.RESET_ALL}")
        
    def run(self):
        """Run the spider."""
        print(f"{Fore.CYAN}Starting web spider...{Style.RESET_ALL}")
        print(f"Start URLs: {self.start_urls}")
        print(f"Max depth: {self.max_depth}")
        print(f"Max pages: {self.max_pages}")
        print(f"Same domain only: {self.same_domain}")
        print(f"{'='*50}{Style.RESET_ALL}\n")
        
        asyncio.run(self.crawl())
        self.print_statistics()
        
        # Save statistics
        stats_file = os.path.join(self.output_dir, 'crawl_stats.json')
        with open(stats_file, 'w') as f:
            stats_copy = self.stats.copy()
            stats_copy['start_time'] = self.stats['start_time'].isoformat()
            stats_copy['end_time'] = self.stats['end_time'].isoformat()
            json.dump(stats_copy, f, indent=2)


if __name__ == "__main__":
    # Example usage
    spider = WebSpider(
        start_urls=["https://example.com"],
        max_depth=2,
        max_pages=50,
        delay=0.5,
        same_domain=True
    )
    spider.run()