from urllib.parse import urljoin, urlparse, urlunparse, unquote
import re
import asyncio
import aiohttp
from bs4 import BeautifulSoup
import sys
import random

if len(sys.argv) != 3:
    print("Usage: python pathfinder.py <URL> <Max Depth>")
    sys.exit(1)

start_url = sys.argv[1]
visited_urls = set()

# List of user-agent strings to rotate through
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; WOW64; Trident/7.0; rv:11.0) like Gecko",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:88.0) Gecko/20100101 Firefox/88.0",
    "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.182 Mobile Safari/537.36"
]

def getDomainName(url):
    domain = urlparse(url).netloc
    if domain.startswith('www.'):
        domain = domain[4:]
    return domain

start_domain = getDomainName(start_url)

def normalizeUrl(url):
    parsed_url = urlparse(url)
    path_parts = parsed_url.path.split('/')
    if re.match(r'^\d+\.html$', path_parts[-1]):
        path_parts[-1] = 'numeric-placeholder.html'
    normalized_path = '/'.join(path_parts)
    normalized_url = urlunparse(parsed_url._replace(path=normalized_path, query='', fragment=''))
    return normalized_url

def isValidUrl(url):
    if url.endswith('/feed/') or 'wp-json' in url:
        return False
    return True

def cleanUrl(url):
    return unquote(url)

async def getLinks(session, url, depth=0, max_depth=int(sys.argv[2])):
    if depth > max_depth or not urlparse(url).scheme:
        return

    url = cleanUrl(url)
    normalized_url = normalizeUrl(url)
    if normalized_url in visited_urls or getDomainName(url) != start_domain or not isValidUrl(normalized_url):
        return

    print(f"Visiting ({depth}): {url}")
    visited_urls.add(normalized_url)

    headers = {
        'User-Agent': random.choice(USER_AGENTS)
    }

    try:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                text = await response.text()
                soup = BeautifulSoup(text, 'html.parser')
                elements_with_href = soup.find_all(href=True)
                tasks = []
                for element in elements_with_href:
                    href = element.get('href')
                    if href and not href.startswith('#') and isValidUrl(href):
                        absolute_url = urljoin(url, cleanUrl(href))
                        task = asyncio.create_task(getLinks(session, absolute_url, depth + 1, max_depth))
                        tasks.append(task)
                await asyncio.gather(*tasks)
    except Exception as e:
        pass

async def main(start_url):
    async with aiohttp.ClientSession() as session:
        await getLinks(session, start_url, 0, int(sys.argv[2]))

if __name__ == "__main__":
    asyncio.run(main(start_url))
