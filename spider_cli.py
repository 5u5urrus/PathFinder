#!/usr/bin/env python3
"""
Web Spider CLI - Command line interface for the web spider
"""

import click
import json
import os
from spider import WebSpider
from colorama import Fore, Style


@click.command()
@click.argument('urls', nargs=-1, required=True)
@click.option('--max-depth', '-d', default=3, help='Maximum crawl depth (default: 3)')
@click.option('--max-pages', '-p', default=100, help='Maximum pages to crawl (default: 100)')
@click.option('--delay', '-t', default=0.5, help='Delay between requests in seconds (default: 0.5)')
@click.option('--same-domain/--any-domain', default=True, help='Restrict to same domain (default: True)')
@click.option('--user-agent', '-u', default='WebSpider/1.0', help='User agent string')
@click.option('--output-dir', '-o', default='spider_output', help='Output directory (default: spider_output)')
@click.option('--allowed-extensions', '-e', multiple=True, help='Allowed file extensions (e.g., -e .html -e .htm)')
@click.option('--config', '-c', type=click.Path(exists=True), help='Load configuration from JSON file')
def crawl(urls, max_depth, max_pages, delay, same_domain, user_agent, output_dir, allowed_extensions, config):
    """
    Web Spider - An effective web crawling tool
    
    Examples:
        spider_cli.py https://example.com
        spider_cli.py https://example.com https://example.org -d 2 -p 50
        spider_cli.py https://example.com --any-domain -o my_crawl
        spider_cli.py -c config.json
    """
    
    # Load configuration from file if provided
    if config:
        with open(config, 'r') as f:
            config_data = json.load(f)
            urls = config_data.get('urls', urls)
            max_depth = config_data.get('max_depth', max_depth)
            max_pages = config_data.get('max_pages', max_pages)
            delay = config_data.get('delay', delay)
            same_domain = config_data.get('same_domain', same_domain)
            user_agent = config_data.get('user_agent', user_agent)
            output_dir = config_data.get('output_dir', output_dir)
            allowed_extensions = config_data.get('allowed_extensions', allowed_extensions)
    
    # Convert URLs tuple to list
    url_list = list(urls)
    
    if not url_list:
        click.echo(f"{Fore.RED}Error: No URLs provided{Style.RESET_ALL}")
        return
    
    # Process allowed extensions
    extensions = set(allowed_extensions) if allowed_extensions else None
    
    # Create and run spider
    spider = WebSpider(
        start_urls=url_list,
        max_depth=max_depth,
        max_pages=max_pages,
        delay=delay,
        same_domain=same_domain,
        user_agent=user_agent,
        output_dir=output_dir,
        allowed_extensions=extensions
    )
    
    try:
        spider.run()
    except KeyboardInterrupt:
        click.echo(f"\n{Fore.YELLOW}Crawling interrupted by user{Style.RESET_ALL}")
    except Exception as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")


@click.group()
def cli():
    """Web Spider - Advanced web crawling tool"""
    pass


@cli.command()
@click.option('--output', '-o', default='spider_config.json', help='Output configuration file')
def generate_config(output):
    """Generate a sample configuration file"""
    
    sample_config = {
        "urls": ["https://example.com", "https://example.org"],
        "max_depth": 3,
        "max_pages": 100,
        "delay": 0.5,
        "same_domain": True,
        "user_agent": "WebSpider/1.0",
        "output_dir": "spider_output",
        "allowed_extensions": [".html", ".htm", ".php", ".asp", ".aspx"]
    }
    
    with open(output, 'w') as f:
        json.dump(sample_config, f, indent=2)
    
    click.echo(f"{Fore.GREEN}Configuration file created: {output}{Style.RESET_ALL}")
    click.echo(f"Edit this file and run: spider_cli.py crawl -c {output}")


@cli.command()
@click.argument('output_dir', default='spider_output')
def analyze(output_dir):
    """Analyze crawled data and show statistics"""
    
    if not os.path.exists(output_dir):
        click.echo(f"{Fore.RED}Error: Output directory '{output_dir}' not found{Style.RESET_ALL}")
        return
    
    stats_file = os.path.join(output_dir, 'crawl_stats.json')
    if not os.path.exists(stats_file):
        click.echo(f"{Fore.RED}Error: Stats file not found in '{output_dir}'{Style.RESET_ALL}")
        return
    
    with open(stats_file, 'r') as f:
        stats = json.load(f)
    
    # Count JSON files
    json_files = [f for f in os.listdir(output_dir) if f.endswith('.json') and f != 'crawl_stats.json']
    
    click.echo(f"\n{Fore.CYAN}{'='*50}")
    click.echo(f"Crawl Analysis for: {output_dir}")
    click.echo(f"{'='*50}{Style.RESET_ALL}")
    click.echo(f"Pages crawled: {Fore.GREEN}{stats['pages_crawled']}{Style.RESET_ALL}")
    click.echo(f"Pages failed: {Fore.RED}{stats['pages_failed']}{Style.RESET_ALL}")
    click.echo(f"Total data: {Fore.YELLOW}{stats['total_bytes'] / 1024 / 1024:.2f} MB{Style.RESET_ALL}")
    click.echo(f"Data files: {Fore.BLUE}{len(json_files)}{Style.RESET_ALL}")
    click.echo(f"Start time: {stats['start_time']}")
    click.echo(f"End time: {stats['end_time']}")
    
    # Analyze content
    total_images = 0
    total_links = 0
    domains = set()
    
    for json_file in json_files[:10]:  # Sample first 10 files
        with open(os.path.join(output_dir, json_file), 'r') as f:
            data = json.load(f)
            total_images += len(data.get('images', []))
            domains.add(data['url'].split('/')[2])
    
    if json_files:
        avg_images = total_images / min(len(json_files), 10)
        click.echo(f"\nAverage images per page: {Fore.MAGENTA}{avg_images:.1f}{Style.RESET_ALL}")
        click.echo(f"Unique domains: {Fore.CYAN}{len(domains)}{Style.RESET_ALL}")


# Update the main cli to use subcommands
cli.add_command(crawl)

if __name__ == '__main__':
    cli()