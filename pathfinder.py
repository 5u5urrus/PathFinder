#!/usr/bin/env python3
import argparse
import asyncio
import logging
import random
import re
import sys
from typing import Optional, Set, Dict, Tuple

import aiohttp
from bs4 import BeautifulSoup

from urllib.parse import (
    urlparse, urlunparse, urljoin, parse_qsl, urlencode
)

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


# ----------------------------
# Config / constants
# ----------------------------

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

VALID_SCHEMES = {"http", "https"}
BAD_PREFIXES = ("mailto:", "tel:", "javascript:", "data:", "blob:")
TRACKING_KEYS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "mc_cid", "mc_eid", "ref", "ref_src"
}
BINARY_EXT = re.compile(
    r"\.(?:pdf|zip|rar|7z|tar|gz|bz2|xz|exe|dmg|iso|jpg|jpeg|png|gif|webp|svg|mp3|wav|mp4|m4v|avi|mov|wmv|ico|woff2?|ttf|eot)"
    r"(?:[?#].*)?$", re.I
)


# ----------------------------
# Helpers
# ----------------------------

def is_http_url(u: str) -> bool:
    try:
        p = urlparse(u)
    except Exception:
        return False
    return p.scheme in VALID_SCHEMES and bool(p.netloc)


def base_host(u: str) -> str:
    host = (urlparse(u).hostname or "").lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


def in_scope_host(host: str, base: str, allow_subdomains: bool) -> bool:
    host = (host or "").lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    if not allow_subdomains:
        return host == base
    return host == base or host.endswith("." + base)


def _format_netloc(scheme: str, host: str, port: Optional[int]) -> str:
    """IPv6-safe netloc builder."""
    if not host:
        return ""
    default = (scheme == "http" and port in (None, 80)) or (scheme == "https" and port in (None, 443))
    h = host
    if ":" in h and not h.startswith("["):  # IPv6 literal
        h = f"[{h}]"
    return h if default else f"{h}:{port}"


def _collapse_index(path: str) -> str:
    if path.lower().endswith(("/index.html", "/index.htm", "/index.php", "/index.asp", "/index.aspx")):
        return "/" if path.count("/") == 1 else path[:path.rfind("/")]
    return path


def normalize_url(u: str, *, sort_query: bool = False) -> str:
    p = urlparse(u)

    scheme = p.scheme.lower()
    host = (p.hostname or "").lower().rstrip(".")
    netloc = _format_netloc(scheme, host, p.port)

    # Path: collapse // but keep percent-escapes as-is (don’t unquote)
    path = re.sub(r"//+", "/", p.path or "/")
    if path != "/":
        path = path.rstrip("/")
    path = _collapse_index(path)
    if path != "/":
        path = path.rstrip("/")

    # Query: strip tracking params; optionally sort
    qs_pairs = [(k, v) for (k, v) in parse_qsl(p.query, keep_blank_values=True) if k not in TRACKING_KEYS]
    if sort_query and qs_pairs:
        qs_pairs.sort()
    query = urlencode(qs_pairs, doseq=True)

    return urlunparse((scheme, netloc, path, "", query, ""))


def is_valid_link(href: str) -> bool:
    if not href:
        return False
    s = href.strip()
    if s.startswith(("#",)) or s.startswith(BAD_PREFIXES):
        return False
    if BINARY_EXT.search(s):
        return False
    # WordPress noise (path or query)
    low = s.lower()
    if "/wp-json" in low or "rest_route=" in low or low.endswith("/feed/") or low.endswith("/feed"):
        return False
    return True


def regex_type(pat: str):
    try:
        return re.compile(pat, re.I)
    except re.error as e:
        raise argparse.ArgumentTypeError(f"Invalid regex {pat!r}: {e}")


def _parse_retry_after(ra: Optional[str]) -> Optional[float]:
    if not ra:
        return None
    ra = ra.strip()
    if ra.isdigit():
        return float(ra)
    try:
        dt = parsedate_to_datetime(ra)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (dt - datetime.now(timezone.utc)).total_seconds())
    except Exception:
        return None


# ----------------------------
# robots.txt (simple)
# ----------------------------

class Robots:
    def __init__(self):
        self.rules: Dict[str, bool] = {}  # prefix -> allowed?
        self.crawl_delay: Optional[float] = None
        self.sitemaps: Set[str] = set()

    def allowed(self, path: str) -> bool:
        # simple longest-prefix match, honor $ end-anchors roughly
        path = path or "/"
        verdict = True
        longest = -1
        for rule, allow in self.rules.items():
            exact_end = False
            r = rule
            if r.endswith("$"):
                exact_end = True
                r = r[:-1]
            if path.startswith(r) and len(r) > longest:
                if exact_end and len(path) != len(r):
                    continue
                longest = len(r)
                verdict = allow
        return verdict


async def fetch_robots(session: aiohttp.ClientSession, origin: str) -> Optional[Robots]:
    """
    origin like 'https://example.com' (host:port aware via caller).
    """
    url = origin.rstrip("/") + "/robots.txt"
    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None
            text = await resp.text(errors="ignore")
    except Exception:
        return None

    rb = Robots()
    current_star = False
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k = k.strip().lower()
        v = v.strip()
        if k == "user-agent":
            current_star = (v == "*" or v.lower().startswith("*"))
        elif k == "disallow" and current_star:
            rb.rules[v if v else "/"] = False
        elif k == "allow" and current_star:
            rb.rules[v if v else "/"] = True
        elif k == "crawl-delay" and current_star:
            try:
                rb.crawl_delay = float(v)
            except Exception:
                pass
        elif k == "sitemap":
            rb.sitemaps.add(v)
    return rb


# ----------------------------
# Crawler
# ----------------------------

class Crawler:
    def __init__(
        self,
        start_url: str,
        max_depth: int,
        *,
        allow_subdomains: bool = True,
        max_pages: Optional[int] = None,
        concurrency: int = 20,
        timeout: float = 15.0,
        jitter: Tuple[float, float] = (0.05, 0.15),
        respect_robots: bool = False,
        max_body_bytes: int = 5_000_000,
        include: Optional[re.Pattern] = None,
        exclude: Optional[re.Pattern] = None,
        https_only: bool = False,
        insecure: bool = False,
    ):
        self.start_url = normalize_url(start_url)
        self.max_depth = max_depth
        self.allow_subdomains = allow_subdomains
        self.max_pages = max_pages
        self.concurrency = max(1, concurrency)
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.jitter = jitter
        self.respect_robots = respect_robots
        self.max_body_bytes = max(256, max_body_bytes)  # clamp silly caps
        self.include = include
        self.exclude = exclude
        self.https_only = https_only
        self.insecure = insecure

        self.start_base = base_host(self.start_url)

        # state
        self.visited: Set[str] = set()
        self.scheduled: Set[str] = set()
        self.errors = 0

        self._lock = asyncio.Lock()
        self._frontier: "asyncio.Queue[Tuple[str,int]]" = asyncio.Queue()

        # robots cache per-origin
        self.robots_cache: Dict[str, Optional[Robots]] = {}
        self.robots_lock = asyncio.Lock()

        # connector is created inside run() (loop must be running)
        self.connector: Optional[aiohttp.TCPConnector] = None

    async def _get_robots(self, session: aiohttp.ClientSession, scheme: str, host: str, port: Optional[int]) -> Optional[Robots]:
        host = (host or "").rstrip(".").lower()
        origin = f"{scheme}://{_format_netloc(scheme, host, port)}"
        async with self.robots_lock:
            if origin in self.robots_cache:
                return self.robots_cache[origin]
        rb = await fetch_robots(session, origin)
        async with self.robots_lock:
            self.robots_cache[origin] = rb
        return rb

    async def run(self) -> None:
        self.connector = aiohttp.TCPConnector(
            limit=self.concurrency,
            limit_per_host=min(8, self.concurrency),
            ttl_dns_cache=300,
            ssl=False if self.insecure else None,
        )
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        async with aiohttp.ClientSession(
            timeout=self.timeout,
            connector=self.connector,
            headers=headers,
        ) as session:
            # seed frontier
            norm = self.start_url
            async with self._lock:
                if self.max_pages is None or (len(self.visited) + len(self.scheduled)) < self.max_pages:
                    self.scheduled.add(norm)
                    await self._frontier.put((norm, 0))

            # workers
            workers = [asyncio.create_task(self._worker(session)) for _ in range(self.concurrency)]
            await self._frontier.join()
            for w in workers:
                w.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

        logging.info("Crawl finished. Visited=%d", len(self.visited))

    async def _worker(self, session: aiohttp.ClientSession) -> None:
        try:
            while True:
                url, depth = await self._frontier.get()
                try:
                    await self._crawl(session, url, depth)
                finally:
                    self._frontier.task_done()
        except asyncio.CancelledError:
            return

    async def _crawl(self, session: aiohttp.ClientSession, url: str, depth: int) -> None:
        norm = normalize_url(url)

        # include/exclude on current URL
        if self.include and not self.include.search(norm):
            async with self._lock:
                self.scheduled.discard(norm)
            return
        if self.exclude and self.exclude.search(norm):
            async with self._lock:
                self.scheduled.discard(norm)
            return

        # scope / scheme guards
        pu = urlparse(norm)
        if pu.scheme not in VALID_SCHEMES or not pu.netloc:
            async with self._lock:
                self.scheduled.discard(norm)
            return
        if self.https_only and pu.scheme != "https":
            async with self._lock:
                self.scheduled.discard(norm)
            return
        if not in_scope_host(pu.hostname or "", self.start_base, self.allow_subdomains):
            async with self._lock:
                self.scheduled.discard(norm)
            return

        # budget dedupe
        async with self._lock:
            if norm in self.visited:
                self.scheduled.discard(norm)
                return
            # do not overschedule; we're consuming one scheduled now
            if self.max_pages is not None and len(self.visited) >= self.max_pages:
                self.scheduled.discard(norm)
                return

        logging.info("Visiting (%d): %s", depth, norm)

        # politeness jitter and optional robots crawl-delay (pre)
        if self.respect_robots:
            rb_pre = await self._get_robots(session, pu.scheme, pu.hostname or "", pu.port)
            if rb_pre and rb_pre.crawl_delay:
                await asyncio.sleep(rb_pre.crawl_delay)
            if rb_pre and not rb_pre.allowed(pu.path or "/"):
                logging.debug("Blocked by robots.txt (pre): %s", norm)
                async with self._lock:
                    self.scheduled.discard(norm)
                return

        await asyncio.sleep(random.uniform(*self.jitter))

        html: Optional[str] = None
        final = None

        # fetch with retry/backoff for 429/5xx + Retry-After
        for attempt in range(3):
            try:
                per_req_headers = {"User-Agent": random.choice(USER_AGENTS)}
                async with session.get(norm, headers=per_req_headers) as resp:
                    status = resp.status

                    # redirect final URL
                    final = resp.url

                    # scope after redirects
                    fhost = (final.host or "")
                    if not in_scope_host(fhost, self.start_base, self.allow_subdomains):
                        async with self._lock:
                            self.scheduled.discard(norm)
                        return
                    if self.https_only and final.scheme.lower() != "https":
                        async with self._lock:
                            self.scheduled.discard(norm)
                        return

                    # retry on 429/5xx
                    if status == 429 or 500 <= status <= 599:
                        if attempt < 2:
                            ra = _parse_retry_after(resp.headers.get("Retry-After"))
                            delay = ra if ra is not None else (0.25 * (2 ** attempt) + random.uniform(0, 0.1))
                            logging.info("HTTP %s for %s, retrying in %.2fs", status, norm, delay)
                            await asyncio.sleep(delay)
                            continue
                        logging.warning("HTTP %s for %s", status, norm)
                        async with self._lock:
                            self.scheduled.discard(norm)
                        return

                    if not (200 <= status < 300):
                        async with self._lock:
                            self.scheduled.discard(norm)
                        return

                    # optional header robots nofollow (header)
                    xrt = (resp.headers.get("X-Robots-Tag") or "").lower()
                    nofollow_hdr = ("nofollow" in xrt) or ("none" in xrt)

                    # body size cap
                    cap = self.max_body_bytes
                    cl = resp.headers.get("Content-Length")
                    if cl and cl.isdigit() and int(cl) > cap:
                        logging.debug("Skipping large body (> %d): %s", cap, str(final))
                        async with self._lock:
                            self.scheduled.discard(norm)
                        return

                    ctype = (resp.headers.get("Content-Type") or "").lower()
                    if ("text/html" in ctype) or ("application/xhtml+xml" in ctype):
                        data = await resp.content.read(cap + 1)
                        if len(data) > cap:
                            logging.debug("Skipping large HTML (> %d): %s", cap, str(final))
                            async with self._lock:
                                self.scheduled.discard(norm)
                            return
                        enc = resp.charset or "utf-8"
                        html = data.decode(enc, errors="ignore")
                    else:
                        # Fallback sniff for mislabelled HTML
                        head = await resp.content.read(min(512, cap + 1))
                        sig = head.lstrip().lower()
                        if not (sig.startswith(b"<!doctype") or b"<html" in sig):
                            async with self._lock:
                                self.scheduled.discard(norm)
                            return
                        if len(head) > cap:
                            logging.debug("Skipping large HTML (> %d): %s", cap, str(final))
                            async with self._lock:
                                self.scheduled.discard(norm)
                            return
                        rest_bytes = max(0, cap - len(head) + 1)
                        rest = await resp.content.read(rest_bytes)
                        data = head + rest
                        if len(data) > cap:
                            logging.debug("Skipping large HTML (> %d): %s", cap, str(final))
                            async with self._lock:
                                self.scheduled.discard(norm)
                            return
                        enc = resp.charset or "utf-8"
                        html = data.decode(enc, errors="ignore")

                    # robots after redirects (host:port aware)
                    if self.respect_robots:
                        rb_post = await self._get_robots(session, final.scheme, final.host or "", final.port)
                        if rb_post and not rb_post.allowed(final.path or "/"):
                            logging.debug("Blocked by robots.txt: %s", str(final))
                            async with self._lock:
                                self.scheduled.discard(norm)
                            return

                    # Mark both requested and final as visited (after success)
                    final_norm = normalize_url(str(final))
                    async with self._lock:
                        self.visited.add(norm)
                        self.visited.add(final_norm)
                        # free any pre-scheduled redirected target
                        self.scheduled.discard(final_norm)
                        self.scheduled.discard(norm)

                    # If include/exclude fails on final, do not expand children
                    if (self.include and not self.include.search(final_norm)) or (self.exclude and self.exclude.search(final_norm)):
                        return

                    # If header says nofollow and we're being polite, don't expand
                    if self.respect_robots and nofollow_hdr:
                        logging.debug("X-Robots-Tag nofollow: %s", str(final))
                        return

                    # Parse HTML
                    try:
                        soup = BeautifulSoup(html, "lxml")
                    except Exception:
                        soup = BeautifulSoup(html, "html.parser")

                    # meta robots nofollow
                    nofollow_meta = False
                    m = soup.find("meta", attrs={"name": re.compile(r"^\s*robots\s*$", re.I)})
                    if m and m.get("content") and re.search(r"(?:^|,|\s)(nofollow|none)(?:$|,|\s)", m["content"].lower()):
                        nofollow_meta = True
                        if self.respect_robots:
                            return  # polite: don’t follow children

                    # Respect <base href> for joining
                    base_for_join = str(final)
                    base_tag = soup.find("base", href=True)
                    if base_tag:
                        try:
                            base_for_join = urljoin(base_for_join, base_tag["href"])
                        except Exception:
                            pass

                    # Canonical de-dupe (don’t schedule based on this, just mark)
                    canon = soup.find("link", rel=re.compile(r"\bcanonical\b", re.I), href=True)
                    if canon:
                        try:
                            canon_norm = normalize_url(urljoin(base_for_join, canon["href"]))
                            fhost2 = (urlparse(canon_norm).hostname or "")
                            if in_scope_host(fhost2, self.start_base, self.allow_subdomains):
                                async with self._lock:
                                    self.visited.add(canon_norm)
                        except Exception:
                            pass

                    if depth >= self.max_depth:
                        return

                    # Collect links
                    child_links: Set[str] = set()

                    # hrefs (includes <a>, <area>, <link>, etc.)
                    for el in soup.find_all(href=True):
                        # skip per-link rel="nofollow" if respecting robots
                        if self.respect_robots:
                            rel = el.get("rel")
                            if rel:
                                vals = rel if isinstance(rel, list) else re.split(r"\s+", str(rel))
                                if any(str(r).lower() == "nofollow" for r in vals):
                                    continue
                        href = el.get("href")
                        if is_valid_link(href):
                            child_links.add(urljoin(base_for_join, href))

                    # srcset (images/sources)
                    for el in soup.find_all(attrs={"srcset": True}):
                        for cand in el["srcset"].split(","):
                            u2 = cand.strip().split(" ")[0]
                            if is_valid_link(u2):
                                child_links.add(urljoin(base_for_join, u2))

                    # meta refresh
                    refresh = soup.find("meta", attrs={"http-equiv": re.compile(r"refresh", re.I)}, content=True)
                    if refresh:
                        mm = re.search(r'url\s*=\s*([^;]+)', refresh["content"], re.I)
                        if mm:
                            child_links.add(urljoin(base_for_join, mm.group(1).strip()))

                    # Schedule children
                    for link in child_links:
                        if not is_http_url(link):
                            continue
                        norm_child = normalize_url(link)

                        # https-only pre-schedule
                        if self.https_only and urlparse(norm_child).scheme != "https":
                            continue

                        # in-scope host
                        chost = (urlparse(norm_child).hostname or "")
                        if not in_scope_host(chost, self.start_base, self.allow_subdomains):
                            continue

                        # include/exclude (child)
                        if (self.include and not self.include.search(norm_child)) or (self.exclude and self.exclude.search(norm_child)):
                            continue

                        # budget check & dedupe
                        async with self._lock:
                            if self.max_pages is not None and (len(self.visited) + len(self.scheduled)) >= self.max_pages:
                                break
                            if norm_child in self.visited or norm_child in self.scheduled:
                                continue
                            self.scheduled.add(norm_child)
                        await self._frontier.put((norm_child, depth + 1))

                    break  # success, exit retry loop

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt == 2:
                    self.errors += 1
                    logging.debug("Fetch failed %s (%s)", norm, type(e).__name__)
                    async with self._lock:
                        self.scheduled.discard(norm)
                    return
                await asyncio.sleep(0.25 * (2 ** attempt) + random.uniform(0, 0.1))


# ----------------------------
# CLI
# ----------------------------

def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Polite, scoped async web spider",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("url", help="Start URL")
    p.add_argument("max_depth", type=int, help="Max crawl depth (0 = just the start page)")

    p.add_argument("--no-subdomains", action="store_true", help="Do not allow subdomains")
    p.add_argument("--max-pages", type=int, default=None, help="Maximum pages to visit")
    p.add_argument("--concurrency", type=int, default=20, help="Number of concurrent workers")
    p.add_argument("--timeout", type=float, default=15.0, help="Per-request timeout (seconds)")
    p.add_argument("--jitter", type=float, nargs=2, metavar=("MIN","MAX"), default=(0.05, 0.15), help="Random politeness delay range (seconds)")
    p.add_argument("--respect-robots", action="store_true", help="Respect robots.txt and nofollow")
    p.add_argument("--max-body-bytes", type=int, default=5_000_000, help="Max HTML bytes to read per page")
    p.add_argument("--include", type=regex_type, help="Regex; only schedule URLs matching")
    p.add_argument("--exclude", type=regex_type, help="Regex; do not schedule URLs matching")
    p.add_argument("--https-only", action="store_true", help="Only crawl https:// URLs (and redirects)")
    p.add_argument("--insecure", action="store_true", help="Do not verify TLS certs (ssl=False)")
    p.add_argument("--out", help="Write visited URLs (sorted) to file")
    p.add_argument("--log", default="INFO", help="Logging level (DEBUG, INFO, WARNING)")
    return p


def main(argv) -> int:
    args = build_argparser().parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log.upper(), logging.INFO),
        format="%(levelname)s: %(message)s"
    )

    crawler = Crawler(
        start_url=args.url,
        max_depth=args.max_depth,
        allow_subdomains=not args.no_subdomains,
        max_pages=args.max_pages,
        concurrency=args.concurrency,
        timeout=args.timeout,
        jitter=tuple(args.jitter),
        respect_robots=args.respect_robots,
        max_body_bytes=args.max_body_bytes,
        include=args.include,
        exclude=args.exclude,
        https_only=args.https_only,
        insecure=args.insecure,
    )

    try:
        asyncio.run(crawler.run())
    except KeyboardInterrupt:
        logging.warning("Interrupted by user")

    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as f:
                for u in sorted(crawler.visited):
                    f.write(u + "\n")
            logging.info("Wrote %d URLs to %s", len(crawler.visited), args.out)
        except Exception as e:
            logging.error("Failed to write output: %s", e)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
