#!/usr/bin/env python3
"""
Effective Web Spider - Focused on comprehensive page discovery
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs, unquote
import re
import sys
import time
from collections import deque
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

class PowerfulSpider:
    def __init__(self, start_url, max_pages=None, output_file=None, threads=10):
        self.start_url = start_url
        self.domain = urlparse(start_url).netloc
        self.max_pages = max_pages
        self.output_file = output_file
        self.threads = threads
        
        self.visited = set()
        self.to_visit = deque([start_url])
        self.found_urls = set([start_url])
        self.lock = threading.Lock()
        
        # Headers to avoid being blocked
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
    def normalize_url(self, url):
        """Normalize URL to avoid duplicates"""
        # Remove fragment
        url = url.split('#')[0]
        # Remove trailing slash
        if url.endswith('/') and url.count('/') > 3:
            url = url[:-1]
        # Convert to lowercase
        parsed = urlparse(url.lower())
        # Rebuild URL
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        
    def extract_urls_from_html(self, html, base_url):
        """Extract all possible URLs from HTML"""
        urls = set()
        soup = BeautifulSoup(html, 'html.parser')
        
        # 1. Regular links
        for tag in soup.find_all(['a', 'area']):
            href = tag.get('href')
            if href:
                url = urljoin(base_url, href)
                urls.add(url)
        
        # 2. Forms
        for form in soup.find_all('form'):
            action = form.get('action')
            if action:
                url = urljoin(base_url, action)
                urls.add(url)
        
        # 3. JavaScript URLs
        # Look for URLs in JavaScript
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string:
                # Find URLs in JavaScript
                js_urls = re.findall(r'["\']([^"\']*?\.(?:html|htm|php|asp|aspx|jsp|do|action|cgi|pl|shtml|cfm)(?:\?[^"\']*)?)["\']', script.string)
                for js_url in js_urls:
                    url = urljoin(base_url, js_url)
                    urls.add(url)
                
                # Find paths in JavaScript
                paths = re.findall(r'["\']/((?:[^"\']*?/)*[^"\']+)["\']', script.string)
                for path in paths:
                    if not path.endswith(('.js', '.css', '.jpg', '.png', '.gif', '.ico', '.svg', '.json', '.xml')):
                        url = urljoin(base_url, '/' + path)
                        urls.add(url)
        
        # 4. Meta refresh
        meta_refresh = soup.find('meta', attrs={'http-equiv': 'refresh'})
        if meta_refresh:
            content = meta_refresh.get('content', '')
            match = re.search(r'url=(.+)', content, re.IGNORECASE)
            if match:
                url = urljoin(base_url, match.group(1))
                urls.add(url)
        
        # 5. Look for URLs in onclick, onload, etc.
        for tag in soup.find_all(True):
            for attr in ['onclick', 'onload', 'onchange', 'onsubmit']:
                value = tag.get(attr)
                if value:
                    url_matches = re.findall(r'["\']([^"\']+)["\']', value)
                    for match in url_matches:
                        if '/' in match or '.htm' in match or '.php' in match:
                            url = urljoin(base_url, match)
                            urls.add(url)
        
        # 6. Image maps
        for area in soup.find_all('area'):
            href = area.get('href')
            if href:
                url = urljoin(base_url, href)
                urls.add(url)
        
        # 7. Base tag
        base_tag = soup.find('base')
        if base_tag and base_tag.get('href'):
            base_href = base_tag['href']
            # Re-process all relative URLs with new base
            for tag in soup.find_all(['a', 'area']):
                href = tag.get('href')
                if href and not href.startswith(('http://', 'https://', '//')):
                    url = urljoin(base_href, href)
                    urls.add(url)
        
        return urls
    
    def extract_urls_from_text(self, text, base_url):
        """Extract URLs from plain text content"""
        urls = set()
        
        # Find full URLs
        url_pattern = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')
        for match in url_pattern.finditer(text):
            url = match.group(0).rstrip('.,;:!?)')
            urls.add(url)
        
        # Find relative paths that look like URLs
        path_pattern = re.compile(r'(?:^|[\s"])(/[a-zA-Z0-9_\-./]+(?:\.html?|\.php|\.asp|\.jsp)?(?:\?[^\s"]*)?)')
        for match in path_pattern.finditer(text):
            path = match.group(1)
            url = urljoin(base_url, path)
            urls.add(url)
        
        return urls
    
    def discover_common_paths(self, base_url):
        """Try common paths that might exist"""
        common_paths = [
            '/index.html', '/index.php', '/index.asp', '/index.jsp',
            '/home', '/home.html', '/home.php',
            '/about', '/about.html', '/about.php', '/about-us',
            '/contact', '/contact.html', '/contact.php', '/contact-us',
            '/products', '/services', '/portfolio', '/gallery',
            '/news', '/blog', '/articles', '/posts',
            '/login', '/signin', '/register', '/signup',
            '/admin', '/administrator', '/wp-admin',
            '/search', '/sitemap', '/sitemap.xml', '/sitemap.html',
            '/privacy', '/privacy-policy', '/terms', '/terms-of-service',
            '/faq', '/help', '/support',
            '/api', '/api/v1', '/api/v2',
            '/users', '/members', '/profile',
            '/forum', '/forums', '/community',
            '/shop', '/store', '/cart', '/checkout',
            '/download', '/downloads', '/files',
            '/documentation', '/docs', '/manual',
            '/robots.txt', '/humans.txt',
        ]
        
        discovered = set()
        for path in common_paths:
            url = urljoin(base_url, path)
            discovered.add(url)
        
        return discovered
    
    def is_valid_url(self, url):
        """Check if URL should be crawled"""
        parsed = urlparse(url)
        
        # Skip non-HTTP URLs
        if parsed.scheme not in ['http', 'https']:
            return False
        
        # Skip different domains (for now, can be made optional)
        if parsed.netloc != self.domain:
            return False
        
        # Skip certain file types
        skip_extensions = {
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.ico',
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
            '.zip', '.rar', '.7z', '.tar', '.gz',
            '.mp3', '.mp4', '.avi', '.mov', '.wmv',
            '.css', '.js', '.woff', '.woff2', '.ttf', '.eot'
        }
        
        path_lower = parsed.path.lower()
        for ext in skip_extensions:
            if path_lower.endswith(ext):
                return False
        
        return True
    
    def crawl_page(self, url):
        """Crawl a single page and extract URLs"""
        try:
            response = self.session.get(url, timeout=10, allow_redirects=True)
            response.raise_for_status()
            
            # Get final URL after redirects
            final_url = response.url
            
            # Extract URLs from HTML
            urls = self.extract_urls_from_html(response.text, final_url)
            
            # Extract URLs from text content
            urls.update(self.extract_urls_from_text(response.text, final_url))
            
            # Try to discover common paths from this base
            base = f"{urlparse(final_url).scheme}://{urlparse(final_url).netloc}"
            urls.update(self.discover_common_paths(base))
            
            # Filter and normalize URLs
            valid_urls = set()
            for url in urls:
                normalized = self.normalize_url(url)
                if self.is_valid_url(normalized):
                    valid_urls.add(normalized)
            
            return valid_urls
            
        except Exception as e:
            return set()
    
    def spider(self):
        """Main spidering function"""
        print(f"Starting spider on {self.start_url}")
        print(f"Domain: {self.domain}")
        print(f"Max pages: {self.max_pages if self.max_pages else 'unlimited'}")
        print(f"Threads: {self.threads}")
        print("-" * 80)
        
        pages_crawled = 0
        
        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            futures = {}
            
            while self.to_visit or futures:
                # Submit new URLs for crawling
                while self.to_visit and len(futures) < self.threads:
                    with self.lock:
                        if not self.to_visit:
                            break
                        url = self.to_visit.popleft()
                        
                        if url in self.visited:
                            continue
                        
                        if self.max_pages and pages_crawled >= self.max_pages:
                            break
                        
                        self.visited.add(url)
                        future = executor.submit(self.crawl_page, url)
                        futures[future] = url
                
                # Process completed futures
                if futures:
                    done, pending = as_completed(futures), set()
                    for future in done:
                        url = futures[future]
                        del futures[future]
                        
                        pages_crawled += 1
                        
                        try:
                            discovered_urls = future.result()
                            new_urls = 0
                            
                            with self.lock:
                                for discovered_url in discovered_urls:
                                    if discovered_url not in self.found_urls:
                                        self.found_urls.add(discovered_url)
                                        self.to_visit.append(discovered_url)
                                        new_urls += 1
                                        print(f"[{pages_crawled}] {discovered_url}")
                            
                            if new_urls == 0:
                                sys.stdout.write(f"\r[{pages_crawled}] Crawled: {url} (no new URLs)")
                                sys.stdout.flush()
                            
                        except Exception as e:
                            print(f"[{pages_crawled}] Error crawling {url}: {e}")
                        
                        if self.max_pages and pages_crawled >= self.max_pages:
                            break
                
                if self.max_pages and pages_crawled >= self.max_pages:
                    break
        
        print(f"\n\nSpider complete!")
        print(f"Pages crawled: {pages_crawled}")
        print(f"Total URLs found: {len(self.found_urls)}")
        
        # Save results if requested
        if self.output_file:
            with open(self.output_file, 'w') as f:
                for url in sorted(self.found_urls):
                    f.write(url + '\n')
            print(f"URLs saved to: {self.output_file}")
        
        return self.found_urls


def main():
    parser = argparse.ArgumentParser(description='Powerful Web Spider - Comprehensive Page Discovery')
    parser.add_argument('url', help='Starting URL to spider')
    parser.add_argument('-m', '--max-pages', type=int, help='Maximum number of pages to crawl')
    parser.add_argument('-o', '--output', help='Output file to save URLs (one per line)')
    parser.add_argument('-t', '--threads', type=int, default=10, help='Number of threads (default: 10)')
    
    args = parser.parse_args()
    
    spider = PowerfulSpider(
        start_url=args.url,
        max_pages=args.max_pages,
        output_file=args.output,
        threads=args.threads
    )
    
    spider.spider()


if __name__ == '__main__':
    main()