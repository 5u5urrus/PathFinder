import asyncio
import contextlib
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Iterable, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse, urlunparse, urlsplit, urlunsplit, quote, unquote, parse_qsl, urlencode

import httpx
from bs4 import BeautifulSoup
from urllib import robotparser
import xml.etree.ElementTree as ET
import gzip


_HTML_MIME_RE = re.compile(r"text/html|application/xhtml\+xml", re.IGNORECASE)
_NON_HTML_EXTENSIONS = set(
	[
		".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico",
		".css", ".js", ".mjs", ".ts",
		".pdf", ".zip", ".gz", ".rar", ".7z",
		".mp3", ".mp4", ".avi", ".mov", ".mkv",
		".woff", ".woff2", ".ttf", ".otf",
	]
)


@dataclass
class CrawlConfig:
	start_urls: Iterable[str]
	allowed_domains: Optional[Iterable[str]] = None
	include_subdomains: bool = True
	max_pages: int = 500
	max_depth: int = 2
	concurrency: int = 10
	delay: float = 0.5
	user_agent: str = "SpiderBot/0.1 (+https://example.org/spider)"
	respect_robots: bool = True
	use_sitemaps: bool = False
	output_path: str = "crawl.jsonl"
	save_html: bool = False
	timeout: float = 15.0
	verbose: bool = False


class RobotsManager:
	def __init__(self, client: httpx.AsyncClient, user_agent: str) -> None:
		self._client = client
		self._user_agent = user_agent
		self._parsers: dict[str, robotparser.RobotFileParser] = {}
		self._locks: dict[str, asyncio.Lock] = {}

	def _robots_url(self, url: str) -> str:
		parts = urlparse(url)
		return f"{parts.scheme}://{parts.netloc}/robots.txt"

	async def _ensure_parser(self, url: str) -> robotparser.RobotFileParser:
		parts = urlparse(url)
		origin = f"{parts.scheme}://{parts.netloc}"
		if origin in self._parsers:
			return self._parsers[origin]
		lock = self._locks.setdefault(origin, asyncio.Lock())
		async with lock:
			if origin in self._parsers:
				return self._parsers[origin]
			robots_url = f"{origin}/robots.txt"
			parser = robotparser.RobotFileParser()
			try:
				resp = await self._client.get(robots_url, headers={"User-Agent": self._user_agent}, follow_redirects=True)
				if resp.status_code == 200 and resp.text:
					parser.parse(resp.text.splitlines())
				else:
					parser.parse([])
			except Exception:
				parser.parse([])
			self._parsers[origin] = parser
			return parser

	async def is_allowed(self, url: str) -> bool:
		parser = await self._ensure_parser(url)
		return parser.can_fetch(self._user_agent, url)

	async def get_sitemaps(self, url: str) -> list[str]:
		parts = urlparse(url)
		origin = f"{parts.scheme}://{parts.netloc}"
		robots_url = f"{origin}/robots.txt"
		try:
			resp = await self._client.get(robots_url, headers={"User-Agent": self._user_agent}, follow_redirects=True)
			if resp.status_code != 200:
				return []
			lines = resp.text.splitlines()
			sitemaps: list[str] = []
			for line in lines:
				line = line.strip()
				if not line or line.startswith("#"):
					continue
				if line.lower().startswith("sitemap:"):
					value = line.split(":", 1)[1].strip()
					if value:
						sitemaps.append(value)
			return sitemaps
		except Exception:
			return []


class Crawler:
	def __init__(self, config: CrawlConfig) -> None:
		self.config = config
		self.logger = logging.getLogger("spider")
		self.logger.setLevel(logging.DEBUG if config.verbose else logging.INFO)
		handler = logging.StreamHandler()
		handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
		self.logger.handlers.clear()
		self.logger.addHandler(handler)

		limits = httpx.Limits(max_connections=max(20, config.concurrency * 2), max_keepalive_connections=max(10, config.concurrency))
		self.client = httpx.AsyncClient(
			headers={"User-Agent": config.user_agent},
			timeout=httpx.Timeout(config.timeout),
			follow_redirects=True,
			limits=limits,
			http2=True,
		)

		self.robots = RobotsManager(self.client, config.user_agent)
		self.queue: "asyncio.Queue[Tuple[str, int]]" = asyncio.Queue()
		self.seen_urls: Set[str] = set()
		self.pages_crawled: int = 0
		self.write_lock = asyncio.Lock()
		self.host_locks: dict[str, asyncio.Lock] = {}
		self.host_last_fetch: dict[str, float] = {}

		self.allowed_domains: Optional[Set[str]] = set(config.allowed_domains) if config.allowed_domains else None

	async def run(self) -> None:
		try:
			await self._seed_queue()
			workers = [asyncio.create_task(self._worker(i)) for i in range(max(1, self.config.concurrency))]
			await self.queue.join()
			for w in workers:
				w.cancel()
			with contextlib.suppress(asyncio.CancelledError):
				await asyncio.gather(*workers)
		finally:
			await self.client.aclose()

	async def _seed_queue(self) -> None:
		seed_urls = [self._normalize_url(u, None) for u in self.config.start_urls]
		# If allowed_domains not provided, default to start URL hosts
		if self.allowed_domains is None:
			self.allowed_domains = {urlparse(u).netloc for u in seed_urls}
			self.logger.info("Allowed domains: %s", ", ".join(sorted(self.allowed_domains)))
		for u in seed_urls:
			await self._enqueue(u, depth=0)

		if self.config.use_sitemaps:
			self.logger.info("Discovering sitemaps from robots.txt...")
			all_sitemaps: Set[str] = set()
			for u in seed_urls:
				sitemaps = await self.robots.get_sitemaps(u)
				all_sitemaps.update(sitemaps)
			if all_sitemaps:
				self.logger.info("Found %d sitemap(s)", len(all_sitemaps))
				urls_from_sitemaps = await self._fetch_sitemaps(all_sitemaps)
				added = 0
				for su in urls_from_sitemaps:
					norm = self._normalize_url(su, None)
					if self._is_url_allowed(norm) and norm not in self.seen_urls:
						await self._enqueue(norm, depth=0)
						added += 1
						if self.pages_crawled + self.queue.qsize() >= self.config.max_pages:
							break
				if added:
					self.logger.info("Seeded %d URL(s) from sitemaps", added)

	async def _fetch_sitemaps(self, sitemap_urls: Iterable[str]) -> Set[str]:
		urls: Set[str] = set()
		for sm_url in sitemap_urls:
			try:
				resp = await self.client.get(sm_url)
				if resp.status_code != 200:
					continue
				content = resp.content
				ct = resp.headers.get("content-type", "").lower()
				if ct.endswith("gzip") or sm_url.endswith(".gz"):
					content = gzip.decompress(content)
					ct = "application/xml"
				root = ET.fromstring(content)
				# Namespace handling: try urlset and sitemapindex
				if root.tag.endswith("urlset"):
					for url_el in root.iter():
						if url_el.tag.endswith("loc") and url_el.text:
							urls.add(url_el.text.strip())
				elif root.tag.endswith("sitemapindex"):
					child_sitemaps: list[str] = []
					for sm_el in root.iter():
						if sm_el.tag.endswith("loc") and sm_el.text:
							child_sitemaps.append(sm_el.text.strip())
					if child_sitemaps:
						urls.update(await self._fetch_sitemaps(child_sitemaps))
			except Exception:
				continue
		return urls

	async def _worker(self, worker_id: int) -> None:
		while True:
			url, depth = await self.queue.get()
			try:
				if self.pages_crawled >= self.config.max_pages:
					continue

				if self.config.respect_robots:
					allowed = await self.robots.is_allowed(url)
					if not allowed:
						self.logger.debug("Disallowed by robots.txt: %s", url)
						continue

				await self._polite_delay(url)
				start = time.perf_counter()
				resp = None
				try:
					resp = await self.client.get(url)
					duration_ms = int((time.perf_counter() - start) * 1000)
					ct = resp.headers.get("content-type", "")
					final_url = str(resp.request.url)
					status = resp.status_code
					body: Optional[str] = None
					links: Set[str] = set()
					title: Optional[str] = None
					meta_description: Optional[str] = None
					canonical_url: Optional[str] = None

					if status == 200 and _HTML_MIME_RE.search(ct):
						soup = BeautifulSoup(resp.text, "html.parser")
						# Canonical
						link_el = soup.find("link", rel=lambda v: v and "canonical" in [s.lower() for s in (v if isinstance(v, list) else [v])])
						if link_el and link_el.get("href"):
							canonical_url = self._normalize_url(link_el.get("href"), final_url)

						# Title / Meta
						if soup.title and soup.title.string:
							title = soup.title.string.strip()
						md = soup.find("meta", attrs={"name": "description"})
						if md and md.get("content"):
							meta_description = md.get("content").strip()

						# Links
						for a in soup.find_all("a", href=True):
							href = a.get("href")
							candidate = self._normalize_url(href, final_url)
							if self._is_url_allowed(candidate):
								links.add(candidate)

						if self.config.save_html:
							body = resp.text

					# Enqueue children
					if depth < self.config.max_depth:
						for link in links:
							await self._enqueue(link, depth + 1)

					# Record
					record = {
						"url": url,
						"final_url": final_url,
						"status": status,
						"content_type": ct,
						"duration_ms": duration_ms,
						"depth": depth,
						"title": title,
						"meta_description": meta_description,
						"canonical_url": canonical_url,
						"links": sorted(list(links))[:200],
					}
					if body is not None:
						record["html"] = body
					await self._write_record(record)
				finally:
					if resp is not None:
						resp.close()
			except Exception as exc:
				self.logger.debug("Error crawling %s: %s", url, exc)
			finally:
				self.queue.task_done()

	def _path_has_non_html_extension(self, path: str) -> bool:
		lower = path.lower()
		for ext in _NON_HTML_EXTENSIONS:
			if lower.endswith(ext):
				return True
		return False

	def _normalize_url(self, url: str, base: Optional[str]) -> str:
		if base:
			url = urljoin(base, url)
		parts = urlsplit(url)
		scheme = parts.scheme.lower()
		netloc = parts.netloc.lower()
		# Remove default ports
		if (scheme == "http" and netloc.endswith(":80")) or (scheme == "https" and netloc.endswith(":443")):
			netloc = netloc.rsplit(":", 1)[0]
		# Normalize path
		path = unquote(parts.path or "/")
		path = quote(path, safe="/:%@&+$,;=-._~!")
		# Remove fragment
		fragment = ""
		# Sort query parameters for stability
		query_items = parse_qsl(parts.query, keep_blank_values=True)
		query = urlencode(sorted(query_items)) if query_items else ""
		return urlunsplit((scheme, netloc, path, query, fragment))

	def _is_url_allowed(self, url: str) -> bool:
		parts = urlparse(url)
		if parts.scheme not in ("http", "https"):
			return False
		if self._path_has_non_html_extension(parts.path):
			return False
		if not self.allowed_domains:
			return True
		for domain in self.allowed_domains:
			if parts.netloc == domain:
				return True
			if self.config.include_subdomains and parts.netloc.endswith("." + domain):
				return True
		return False

	async def _enqueue(self, url: str, depth: int) -> None:
		if self.pages_crawled + self.queue.qsize() >= self.config.max_pages:
			return
		if url in self.seen_urls:
			return
		self.seen_urls.add(url)
		await self.queue.put((url, depth))

	async def _polite_delay(self, url: str) -> None:
		parts = urlparse(url)
		key = parts.netloc
		lock = self.host_locks.setdefault(key, asyncio.Lock())
		async with lock:
			last = self.host_last_fetch.get(key, 0.0)
			now = time.perf_counter()
			elapsed = now - last
			if elapsed < self.config.delay:
				await asyncio.sleep(self.config.delay - elapsed)
			self.host_last_fetch[key] = time.perf_counter()

	async def _write_record(self, data: dict) -> None:
		async with self.write_lock:
			with open(self.config.output_path, "a", encoding="utf-8") as f:
				f.write(json.dumps(data, ensure_ascii=False) + "\n")
			self.pages_crawled += 1
			if self.pages_crawled % 50 == 0 or self.config.verbose:
				self.logger.info("Crawled %d page(s)", self.pages_crawled)