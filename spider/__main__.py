import argparse
import asyncio
from .crawler import Crawler, CrawlConfig


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="An effective async web spider with robots.txt, sitemap seeding, and JSONL output"
	)
	parser.add_argument("start_urls", nargs="*", help="Start URL(s)")
	parser.add_argument("--allowed-domains", nargs="*", default=None, help="Limit crawl to these domain(s). Example: example.com www.example.com")
	parser.add_argument("--include-subdomains", action="store_true", help="Allow subdomains of allowed domains")
	parser.add_argument("--max-pages", type=int, default=500, help="Maximum number of pages to fetch")
	parser.add_argument("--max-depth", type=int, default=2, help="Maximum crawl depth from start URLs")
	parser.add_argument("--concurrency", type=int, default=10, help="Max concurrent requests")
	parser.add_argument("--delay", type=float, default=0.5, help="Per-host politeness delay in seconds")
	parser.add_argument("--user-agent", default="SpiderBot/0.1 (+https://example.org/spider)", help="User-Agent header")
	parser.add_argument("--sitemaps", action="store_true", help="Seed from sitemap(s) declared in robots.txt of start URL hosts")
	parser.add_argument("--no-robots", action="store_true", help="Do not respect robots.txt (not recommended)")
	parser.add_argument("--output", default="crawl.jsonl", help="Output JSONL file path")
	parser.add_argument("--save-html", action="store_true", help="Also save HTML in the JSONL (increases size)")
	parser.add_argument("--timeout", type=float, default=15.0, help="Request timeout in seconds")
	parser.add_argument("--verbose", action="store_true", help="Verbose logging")
	return parser.parse_args()


def main() -> None:
	args = parse_args()
	if not args.start_urls:
		print("Provide at least one start URL. Example: spider https://example.com")
		return

	config = CrawlConfig(
		start_urls=args.start_urls,
		allowed_domains=args.allowed_domains,
		include_subdomains=args.include_subdomains,
		max_pages=args.max_pages,
		max_depth=args.max_depth,
		concurrency=args.concurrency,
		delay=args.delay,
		user_agent=args.user_agent,
		respect_robots=not args.no_robots,
		use_sitemaps=args.sitemaps,
		output_path=args.output,
		save_html=args.save_html,
		timeout=args.timeout,
		verbose=args.verbose,
	)

	asyncio.run(Crawler(config).run())


if __name__ == "__main__":
	main()