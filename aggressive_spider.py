#!/usr/bin/env python3
"""
Aggressive Web Spider - Maximum page discovery with multiple techniques
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
import json

class AggressiveSpider:
    def __init__(self, start_url, max_pages=None, output_file=None, threads=20, cross_domain=False):
        self.start_url = start_url
        self.start_domain = urlparse(start_url).netloc
        self.max_pages = max_pages
        self.output_file = output_file
        self.threads = threads
        self.cross_domain = cross_domain
        
        self.visited = set()
        self.to_visit = deque([start_url])
        self.found_urls = set([start_url])
        self.domains_found = {self.start_domain}
        self.lock = threading.Lock()
        
        # Multiple user agents to rotate
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
        ]
        
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0'
        })
        
    def get_headers(self):
        """Get headers with rotating user agent"""
        import random
        return {'User-Agent': random.choice(self.user_agents)}
        
    def normalize_url(self, url):
        """Aggressive URL normalization"""
        if not url:
            return None
            
        # Handle protocol-relative URLs
        if url.startswith('//'):
            url = 'http:' + url
            
        # Remove fragment
        url = url.split('#')[0]
        
        # Handle empty or invalid URLs
        if not url or url in ['/', '#', 'javascript:void(0)', 'javascript:;']:
            return None
            
        try:
            parsed = urlparse(url)
            
            # Skip non-HTTP protocols
            if parsed.scheme and parsed.scheme not in ['http', 'https']:
                return None
                
            # Remove default ports
            netloc = parsed.netloc
            if netloc.endswith(':80') and parsed.scheme == 'http':
                netloc = netloc[:-3]
            elif netloc.endswith(':443') and parsed.scheme == 'https':
                netloc = netloc[:-4]
                
            # Remove trailing slashes
            path = parsed.path
            if path.endswith('/') and len(path) > 1:
                path = path[:-1]
                
            # Rebuild URL
            return f"{parsed.scheme}://{netloc}{path}{'?' + parsed.query if parsed.query else ''}"
            
        except:
            return None
    
    def extract_urls_aggressive(self, html, base_url):
        """Aggressively extract all possible URLs"""
        urls = set()
        soup = BeautifulSoup(html, 'html.parser')
        
        # 1. All href attributes
        for tag in soup.find_all(attrs={'href': True}):
            url = urljoin(base_url, tag['href'])
            urls.add(url)
        
        # 2. All src attributes
        for tag in soup.find_all(attrs={'src': True}):
            src = tag['src']
            if not src.endswith(('.jpg', '.jpeg', '.png', '.gif', '.css', '.js', '.ico')):
                url = urljoin(base_url, src)
                urls.add(url)
        
        # 3. All action attributes (forms)
        for tag in soup.find_all(attrs={'action': True}):
            url = urljoin(base_url, tag['action'])
            urls.add(url)
        
        # 4. JavaScript analysis - more aggressive
        for script in soup.find_all('script'):
            if script.string:
                # URLs in JavaScript
                js_urls = re.findall(r'["\']([^"\']+)["\']', script.string)
                for js_url in js_urls:
                    if '/' in js_url or '.htm' in js_url or '.php' in js_url or '.asp' in js_url:
                        url = urljoin(base_url, js_url)
                        urls.add(url)
                
                # Window.location patterns
                location_patterns = [
                    r'window\.location\s*=\s*["\']([^"\']+)["\']',
                    r'location\.href\s*=\s*["\']([^"\']+)["\']',
                    r'location\.replace\s*\(["\']([^"\']+)["\']',
                    r'window\.open\s*\(["\']([^"\']+)["\']'
                ]
                for pattern in location_patterns:
                    matches = re.findall(pattern, script.string)
                    for match in matches:
                        url = urljoin(base_url, match)
                        urls.add(url)
        
        # 5. Inline JavaScript in attributes
        for tag in soup.find_all(True):
            for attr in ['onclick', 'onload', 'onchange', 'onsubmit', 'onmouseover', 'onfocus']:
                value = tag.get(attr)
                if value:
                    # Extract anything that looks like a URL
                    potential_urls = re.findall(r'["\']([^"\']+)["\']', value)
                    for p_url in potential_urls:
                        if '/' in p_url or '.htm' in p_url or '.php' in p_url:
                            url = urljoin(base_url, p_url)
                            urls.add(url)
        
        # 6. Data attributes
        for tag in soup.find_all(True):
            for attr in tag.attrs:
                if attr.startswith('data-') and isinstance(tag[attr], str):
                    if '/' in tag[attr] or 'http' in tag[attr]:
                        url = urljoin(base_url, tag[attr])
                        urls.add(url)
        
        # 7. Comments
        for comment in soup.find_all(string=lambda text: isinstance(text, str)):
            if '<!--' in str(comment):
                # Look for URLs in comments
                comment_urls = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', str(comment))
                urls.update(comment_urls)
                
                # Look for paths in comments
                comment_paths = re.findall(r'/[a-zA-Z0-9_\-./]+', str(comment))
                for path in comment_paths:
                    url = urljoin(base_url, path)
                    urls.add(url)
        
        # 8. Meta tags
        for meta in soup.find_all('meta'):
            content = meta.get('content', '')
            if 'url=' in content or 'http' in content:
                # Extract URL from content
                url_match = re.search(r'(https?://[^\s;]+)', content)
                if url_match:
                    urls.add(url_match.group(1))
        
        # 9. Link tags
        for link in soup.find_all('link'):
            href = link.get('href')
            if href and not href.endswith('.css'):
                url = urljoin(base_url, href)
                urls.add(url)
        
        # 10. Srcset attribute (responsive images might link to pages)
        for tag in soup.find_all(attrs={'srcset': True}):
            srcset = tag['srcset']
            srcs = re.findall(r'([^\s,]+)\s*\d*[wx]?', srcset)
            for src in srcs:
                if not src.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                    url = urljoin(base_url, src)
                    urls.add(url)
        
        return urls
    
    def discover_paths_aggressively(self, base_url):
        """Aggressively discover common and uncommon paths"""
        paths = [
            # Common pages
            '/', '/index', '/index.html', '/index.php', '/index.asp', '/index.jsp', '/default.asp',
            '/home', '/home.html', '/home.php', '/main', '/main.html', '/main.php',
            
            # Navigation
            '/about', '/about-us', '/about.html', '/aboutus', '/company', '/who-we-are',
            '/contact', '/contact-us', '/contact.html', '/contactus', '/get-in-touch',
            '/services', '/service', '/what-we-do', '/solutions',
            '/products', '/product', '/catalog', '/catalogue',
            '/portfolio', '/work', '/projects', '/case-studies', '/showcase',
            '/blog', '/news', '/articles', '/posts', '/insights', '/resources',
            '/team', '/staff', '/people', '/our-team', '/leadership',
            '/careers', '/jobs', '/employment', '/work-with-us', '/join-us',
            
            # User areas
            '/login', '/signin', '/sign-in', '/auth', '/authenticate',
            '/register', '/signup', '/sign-up', '/join', '/create-account',
            '/account', '/profile', '/dashboard', '/user', '/member', '/my-account',
            '/logout', '/signout', '/sign-out',
            '/forgot-password', '/reset-password', '/password-reset',
            
            # Admin areas
            '/admin', '/administrator', '/admin-panel', '/control-panel',
            '/wp-admin', '/wp-login.php', '/cms', '/backend',
            '/manage', '/management', '/cpanel', '/controlpanel',
            
            # API endpoints
            '/api', '/api/v1', '/api/v2', '/api/v3', '/rest', '/graphql',
            '/api/users', '/api/products', '/api/search', '/api/data',
            
            # Common functionality
            '/search', '/find', '/query', '/results',
            '/sitemap', '/sitemap.xml', '/sitemap.html', '/site-map',
            '/feed', '/rss', '/atom', '/feeds',
            '/print', '/pdf', '/download', '/export',
            
            # Legal/Policy
            '/privacy', '/privacy-policy', '/privacy.html', '/legal/privacy',
            '/terms', '/terms-of-service', '/terms-and-conditions', '/tos', '/legal/terms',
            '/disclaimer', '/legal', '/policy', '/policies',
            '/cookies', '/cookie-policy', '/gdpr',
            
            # Help/Support
            '/help', '/support', '/faq', '/faqs', '/knowledge-base', '/kb',
            '/documentation', '/docs', '/manual', '/guide', '/tutorial',
            
            # E-commerce
            '/shop', '/store', '/products', '/catalog', '/categories',
            '/cart', '/basket', '/checkout', '/order', '/payment',
            '/wishlist', '/favorites', '/compare',
            
            # Content sections
            '/gallery', '/photos', '/images', '/media',
            '/videos', '/multimedia', '/watch',
            '/events', '/calendar', '/schedule', '/upcoming',
            '/testimonials', '/reviews', '/feedback', '/comments',
            
            # Archives and categories
            '/archive', '/archives', '/history',
            '/category', '/categories', '/tags', '/topics',
            '/2019', '/2020', '/2021', '/2022', '/2023', '/2024',
            
            # Files and directories
            '/files', '/documents', '/downloads', '/assets', '/resources',
            '/images', '/img', '/pics', '/photos',
            '/scripts', '/js', '/javascript', '/css', '/styles',
            
            # Hidden or less common
            '/.well-known', '/.git', '/.svn', '/.htaccess',
            '/robots.txt', '/humans.txt', '/security.txt',
            '/backup', '/bak', '/old', '/new', '/temp', '/tmp',
            '/test', '/demo', '/sample', '/example',
            '/stage', '/staging', '/dev', '/development',
            '/beta', '/alpha', '/preview',
            
            # Language/locale
            '/en', '/es', '/fr', '/de', '/it', '/pt', '/ru', '/zh', '/ja', '/ko',
            '/english', '/spanish', '/french', '/german',
            
            # Mobile
            '/mobile', '/m', '/app', '/applications',
            
            # Misc
            '/go', '/link', '/redirect', '/out',
            '/share', '/social', '/follow',
            '/subscribe', '/newsletter', '/mailing-list',
            '/partner', '/partners', '/affiliates', '/sponsors'
        ]
        
        discovered = set()
        for path in paths:
            url = urljoin(base_url, path)
            discovered.add(url)
            
        # Try numbered paths
        for i in range(1, 11):
            discovered.add(urljoin(base_url, f'/page{i}'))
            discovered.add(urljoin(base_url, f'/page/{i}'))
            discovered.add(urljoin(base_url, f'/p{i}'))
            discovered.add(urljoin(base_url, f'/{i}'))
            
        return discovered
    
    def try_url_variations(self, url):
        """Generate URL variations to try"""
        variations = set()
        parsed = urlparse(url)
        path = parsed.path
        
        if path and path != '/':
            # Try without extension
            if '.' in path:
                base_path = path.rsplit('.', 1)[0]
                variations.add(f"{parsed.scheme}://{parsed.netloc}{base_path}")
                
                # Try common extensions
                for ext in ['.html', '.htm', '.php', '.asp', '.aspx', '.jsp']:
                    variations.add(f"{parsed.scheme}://{parsed.netloc}{base_path}{ext}")
            
            # Try adding/removing trailing slash
            if path.endswith('/'):
                variations.add(f"{parsed.scheme}://{parsed.netloc}{path[:-1]}")
            else:
                variations.add(f"{parsed.scheme}://{parsed.netloc}{path}/")
                
            # Try index files
            if path.endswith('/'):
                for index in ['index.html', 'index.php', 'default.asp', 'index.jsp']:
                    variations.add(f"{parsed.scheme}://{parsed.netloc}{path}{index}")
        
        return variations
    
    def is_valid_url(self, url):
        """Check if URL should be crawled"""
        if not url:
            return False
            
        parsed = urlparse(url)
        
        # Skip non-HTTP URLs
        if parsed.scheme not in ['http', 'https']:
            return False
        
        # Domain check
        if not self.cross_domain and parsed.netloc != self.start_domain:
            return False
        
        # Skip certain file types (but be less restrictive)
        skip_extensions = {
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.ico', '.webp',
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
            '.zip', '.rar', '.7z', '.tar', '.gz', '.exe', '.dmg',
            '.mp3', '.mp4', '.avi', '.mov', '.wmv', '.flv',
            '.css', '.js', '.woff', '.woff2', '.ttf', '.eot'
        }
        
        path_lower = parsed.path.lower()
        for ext in skip_extensions:
            if path_lower.endswith(ext):
                return False
        
        return True
    
    def crawl_page(self, url):
        """Crawl a single page and extract URLs"""
        discovered_urls = set()
        
        try:
            response = self.session.get(url, headers=self.get_headers(), timeout=15, allow_redirects=True)
            
            # Try to get content regardless of status code
            if response.status_code in [200, 201, 202, 203, 206, 300, 301, 302, 303, 307, 308]:
                final_url = response.url
                
                # Extract URLs from HTML
                urls = self.extract_urls_aggressive(response.text, final_url)
                discovered_urls.update(urls)
                
                # Try to discover common paths
                base = f"{urlparse(final_url).scheme}://{urlparse(final_url).netloc}"
                discovered_urls.update(self.discover_paths_aggressively(base))
                
                # Generate URL variations
                for url in list(discovered_urls)[:10]:  # Don't generate too many variations
                    discovered_urls.update(self.try_url_variations(url))
                
                # Extract URLs from headers
                if 'Location' in response.headers:
                    discovered_urls.add(urljoin(final_url, response.headers['Location']))
                if 'Content-Location' in response.headers:
                    discovered_urls.add(urljoin(final_url, response.headers['Content-Location']))
                    
        except requests.exceptions.Timeout:
            pass  # Skip timeouts silently
        except Exception as e:
            # Still try common paths even on error
            try:
                base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
                discovered_urls.update(self.discover_paths_aggressively(base))
            except:
                pass
        
        # Filter and normalize
        valid_urls = set()
        for disc_url in discovered_urls:
            normalized = self.normalize_url(disc_url)
            if normalized and self.is_valid_url(normalized):
                valid_urls.add(normalized)
                
                # Track new domains
                domain = urlparse(normalized).netloc
                if domain and domain not in self.domains_found:
                    with self.lock:
                        self.domains_found.add(domain)
                        if self.cross_domain:
                            print(f"\n[!] New domain discovered: {domain}")
        
        return valid_urls
    
    def spider(self):
        """Main spidering function"""
        print(f"Starting AGGRESSIVE spider on {self.start_url}")
        print(f"Start domain: {self.start_domain}")
        print(f"Cross-domain: {'YES' if self.cross_domain else 'NO'}")
        print(f"Max pages: {self.max_pages if self.max_pages else 'unlimited'}")
        print(f"Threads: {self.threads}")
        print("-" * 80)
        
        pages_crawled = 0
        last_report = time.time()
        
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
                    for future in as_completed(futures):
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
                            
                            # Status update every 5 seconds
                            if time.time() - last_report > 5:
                                print(f"\n--- Status: {pages_crawled} pages crawled, {len(self.found_urls)} URLs found, {len(self.to_visit)} in queue ---\n")
                                last_report = time.time()
                            
                        except Exception as e:
                            print(f"[{pages_crawled}] Error: {e}")
                        
                        if self.max_pages and pages_crawled >= self.max_pages:
                            break
                
                if self.max_pages and pages_crawled >= self.max_pages:
                    break
        
        print(f"\n\nSpider complete!")
        print(f"Pages crawled: {pages_crawled}")
        print(f"Total URLs found: {len(self.found_urls)}")
        print(f"Domains found: {len(self.domains_found)}")
        
        # Save results if requested
        if self.output_file:
            with open(self.output_file, 'w') as f:
                for url in sorted(self.found_urls):
                    f.write(url + '\n')
            print(f"\nURLs saved to: {self.output_file}")
            
            # Also save domains
            if self.cross_domain and len(self.domains_found) > 1:
                domains_file = self.output_file.replace('.txt', '_domains.txt')
                with open(domains_file, 'w') as f:
                    for domain in sorted(self.domains_found):
                        f.write(domain + '\n')
                print(f"Domains saved to: {domains_file}")
        
        return self.found_urls


def main():
    parser = argparse.ArgumentParser(description='AGGRESSIVE Web Spider - Maximum Page Discovery')
    parser.add_argument('url', help='Starting URL to spider')
    parser.add_argument('-m', '--max-pages', type=int, help='Maximum number of pages to crawl')
    parser.add_argument('-o', '--output', help='Output file to save URLs (one per line)')
    parser.add_argument('-t', '--threads', type=int, default=20, help='Number of threads (default: 20)')
    parser.add_argument('-x', '--cross-domain', action='store_true', help='Allow cross-domain crawling')
    
    args = parser.parse_args()
    
    spider = AggressiveSpider(
        start_url=args.url,
        max_pages=args.max_pages,
        output_file=args.output,
        threads=args.threads,
        cross_domain=args.cross_domain
    )
    
    try:
        spider.spider()
    except KeyboardInterrupt:
        print("\n\nSpider interrupted by user!")
        print(f"URLs found so far: {len(spider.found_urls)}")
        if args.output:
            with open(args.output, 'w') as f:
                for url in sorted(spider.found_urls):
                    f.write(url + '\n')
            print(f"Partial results saved to: {args.output}")


if __name__ == '__main__':
    main()