#!/usr/bin/env python3
"""
Example usage scripts for the Web Spider
"""

from spider import WebSpider
from spider_advanced import AdvancedWebSpider


def example_basic_crawl():
    """Basic website crawl example."""
    print("Example 1: Basic website crawl")
    print("-" * 50)
    
    spider = WebSpider(
        start_urls=["https://example.com"],
        max_depth=2,
        max_pages=20,
        delay=1.0,
        same_domain=True,
        output_dir="example_basic_output"
    )
    
    spider.run()


def example_multi_domain_crawl():
    """Crawl multiple domains example."""
    print("\nExample 2: Multi-domain crawl")
    print("-" * 50)
    
    spider = WebSpider(
        start_urls=[
            "https://example.com",
            "https://example.org",
            "https://example.net"
        ],
        max_depth=1,
        max_pages=30,
        delay=0.5,
        same_domain=False,  # Allow cross-domain crawling
        output_dir="example_multi_domain_output"
    )
    
    spider.run()


def example_filtered_crawl():
    """Crawl with specific file extensions."""
    print("\nExample 3: Filtered crawl (HTML only)")
    print("-" * 50)
    
    spider = WebSpider(
        start_urls=["https://example.com"],
        max_depth=3,
        max_pages=50,
        delay=0.5,
        allowed_extensions={'.html', '.htm', ''},  # Only HTML pages
        output_dir="example_filtered_output"
    )
    
    spider.run()


def example_advanced_pattern_crawl():
    """Advanced crawl with URL patterns."""
    print("\nExample 4: Advanced pattern-based crawl")
    print("-" * 50)
    
    spider = AdvancedWebSpider(
        start_urls=["https://example.com"],
        max_depth=3,
        max_pages=100,
        delay=0.5,
        follow_patterns=[
            r'/blog/',      # Only follow blog URLs
            r'/articles/',  # And article URLs
            r'/posts/'      # And post URLs
        ],
        exclude_patterns=[
            r'/tag/',       # Exclude tag pages
            r'/author/',    # Exclude author pages
            r'\?print=',    # Exclude print versions
            r'\.pdf$'       # Exclude PDF files
        ],
        min_content_length=500,  # Only save pages with 500+ chars
        output_dir="example_pattern_output"
    )
    
    spider.run()


def example_sitemap_crawl():
    """Crawl using sitemap discovery."""
    print("\nExample 5: Sitemap-based crawl")
    print("-" * 50)
    
    spider = AdvancedWebSpider(
        start_urls=["https://example.com"],
        max_depth=2,
        max_pages=200,
        delay=0.3,
        export_format='csv',  # Export as CSV
        output_dir="example_sitemap_output"
    )
    
    spider.run()


def example_data_export_crawl():
    """Crawl with different export formats."""
    print("\nExample 6: Data export formats")
    print("-" * 50)
    
    # JSON Lines format for streaming processing
    spider = AdvancedWebSpider(
        start_urls=["https://example.com"],
        max_depth=2,
        max_pages=50,
        export_format='jsonl',  # JSON Lines format
        output_dir="example_jsonl_output"
    )
    
    spider.run()


def example_custom_user_agent():
    """Crawl with custom user agent."""
    print("\nExample 7: Custom user agent")
    print("-" * 50)
    
    spider = WebSpider(
        start_urls=["https://example.com"],
        max_depth=2,
        max_pages=30,
        user_agent="MyCustomBot/1.0 (+https://mywebsite.com/bot-info)",
        output_dir="example_custom_ua_output"
    )
    
    spider.run()


def example_slow_respectful_crawl():
    """Respectful crawl with longer delays."""
    print("\nExample 8: Respectful slow crawl")
    print("-" * 50)
    
    spider = WebSpider(
        start_urls=["https://example.com"],
        max_depth=3,
        max_pages=100,
        delay=2.0,  # 2 second delay between requests
        output_dir="example_respectful_output"
    )
    
    spider.run()


def main():
    """Run examples based on user choice."""
    examples = {
        '1': ('Basic crawl', example_basic_crawl),
        '2': ('Multi-domain crawl', example_multi_domain_crawl),
        '3': ('Filtered crawl', example_filtered_crawl),
        '4': ('Pattern-based crawl', example_advanced_pattern_crawl),
        '5': ('Sitemap crawl', example_sitemap_crawl),
        '6': ('Export formats', example_data_export_crawl),
        '7': ('Custom user agent', example_custom_user_agent),
        '8': ('Respectful crawl', example_slow_respectful_crawl)
    }
    
    print("Web Spider Examples")
    print("=" * 50)
    print("\nAvailable examples:")
    
    for key, (name, _) in examples.items():
        print(f"{key}. {name}")
    
    print("\nNote: These examples use 'example.com' which is a valid test domain.")
    print("Replace with your target URL for actual crawling.")
    
    choice = input("\nSelect an example (1-8) or 'all' to run all examples: ").strip()
    
    if choice == 'all':
        for name, func in examples.values():
            print(f"\n{'='*70}")
            func()
            input("\nPress Enter to continue to next example...")
    elif choice in examples:
        examples[choice][1]()
    else:
        print("Invalid choice. Please select a number between 1-8 or 'all'.")


if __name__ == "__main__":
    main()