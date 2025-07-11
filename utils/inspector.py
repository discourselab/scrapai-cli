#!/usr/bin/env python3
"""
Page Inspector Utility

This tool downloads and analyzes HTML from a source URL to help with creating scrapers.
It's designed to be used as part of the scraper development process.

Usage:
    python -m utils.inspector --url https://example.com/fact-checks
"""

import os
import json
import argparse
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

from utils.http import get_client

def inspect_page(url, output_dir=None, proxy_type="auto", save_html=True):
    """
    Inspect a page and output analysis to help with creating a scraper
    
    Args:
        url (str): URL to inspect
        output_dir (str): Directory to save analysis and HTML. If None, a directory is created based on the domain
        proxy_type (str): Proxy type to use
        save_html (bool): Whether to save the full HTML
    
    Returns:
        dict: Analysis results
    """
    print(f"Inspecting: {url}")
    
    # Extract domain for folder name if output_dir is not specified
    if output_dir is None:
        domain = urlparse(url).netloc.replace("www.", "")
        # Map domain to source_id
        source_id_mapping = {
            "politifact.com": "politifact",
            "factcheck.org": "factcheck_org",
            "fullfact.org": "full_fact",
            "science.feedback.org": "science_feedback",
            "factcheck.afp.com": "afp",
            "carbonbrief.org": "carbon_brief",
            "climatefactchecks.org": "climate_fact_checks",
            "desmog.blog": "desmog"
        }
        
        source_id = source_id_mapping.get(domain, domain.replace(".", "_"))
        output_dir = f"data/{source_id}/analysis"
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Get the page
    http_client = get_client(proxy_type=proxy_type)
    response = http_client.get(url)
    
    if not response:
        print(f"Failed to fetch page: {url}")
        return None
    
    # Save the HTML if requested
    if save_html:
        html_file = os.path.join(output_dir, "page.html")
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(response.text)
        print(f"Saved HTML to: {html_file}")
    
    # Parse the HTML
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Extract useful information
    title = soup.title.text if soup.title else "No title"
    
    # Analyze potential article containers
    potential_containers = analyze_potential_containers(soup)
    
    # Analyze pagination
    pagination_info = analyze_pagination(soup, url)
    
    # Analyze date formats
    date_formats = analyze_date_formats(soup)
    
    # Compile the analysis
    analysis = {
        "url": url,
        "title": title,
        "potential_article_containers": potential_containers,
        "pagination": pagination_info,
        "date_formats": date_formats
    }
    
    # Save the analysis
    analysis_file = os.path.join(output_dir, "analysis.json")
    with open(analysis_file, 'w', encoding='utf-8') as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)
    
    print(f"Saved analysis to: {analysis_file}")
    print("\nSummary of findings:")
    print(f"Title: {title}")
    print(f"Potential article containers: {len(potential_containers)}")
    print(f"Pagination type: {pagination_info['type']}")
    
    # Print recommendations
    print("\nRecommended selectors:")
    if potential_containers:
        best_container = potential_containers[0]
        print(f"Article container: {best_container['selector']}")
        for field, selector in best_container['field_selectors'].items():
            if selector:
                print(f"  {field}: {selector}")
    
    return analysis

def analyze_potential_containers(soup):
    """
    Analyze the page to find potential article containers
    
    Args:
        soup (BeautifulSoup): Parsed HTML
    
    Returns:
        list: Potential article containers with their selectors
    """
    potential_containers = []
    
    # Common article container class patterns
    container_patterns = [
        # General patterns
        '.article', '.post', '.entry', '.item', '.card',
        
        # List patterns
        'ul.articles li', '.article-list .article', '.post-list .post',
        'li.post-item', 'div.post-item', '.posts-list > li', '.posts-list > div',
        
        # Grid patterns
        '.grid .article', '.grid-item', '.article-grid .article',
        
        # Specific class patterns that often indicate article containers
        '[class*=article]', '[class*=post]', '[class*=entry]', '[class*=item]',
        '[class*=card]', '[class*=fact]', '[class*=check]',
        
        # Common div patterns
        'div.post', 'div[class*=post-]', 'div[class*=article-]',
        'div.factcheck', 'div[class*=fact-check]',
        
        # Additional patterns for common article structures
        '.content-list > li', '.content-list > div',
        '.list-item', '.blog-item', '.news-item'
    ]
    
    for pattern in container_patterns:
        elements = soup.select(pattern)
        if elements:
            # Analyze the first few elements
            for element in elements[:3]:
                # Get all classes
                classes = element.get('class', [])
                selector = f"{element.name}.{'.'.join(classes)}" if classes else element.name
                
                # Look for common fields within this container
                field_selectors = {
                    'title': find_title_selector(element),
                    'link': find_link_selector(element),
                    'date': find_date_selector(element),
                    'topic': find_topic_selector(element)
                }
                
                potential_containers.append({
                    'selector': selector,
                    'field_selectors': field_selectors,
                    'sample_text': element.get_text(strip=True)[:100] + '...' if len(element.get_text(strip=True)) > 100 else element.get_text(strip=True)
                })
    
    # Sort by completeness (how many fields we found)
    potential_containers.sort(key=lambda x: sum(1 for v in x['field_selectors'].values() if v), reverse=True)
    
    return potential_containers

def find_title_selector(container):
    """Find a selector for the title within a container"""
    title_patterns = ['h1', 'h2', 'h3', 'h4', '.title', '.headline', '[class*=title]', '[class*=headline]', 'a']
    
    for pattern in title_patterns:
        elements = container.select(pattern)
        if elements:
            classes = elements[0].get('class', [])
            return f"{elements[0].name}.{'.'.join(classes)}" if classes else elements[0].name
    
    return None

def find_link_selector(container):
    """Find a selector for the link within a container"""
    links = container.find_all('a', href=True)
    if links:
        classes = links[0].get('class', [])
        return f"a.{'.'.join(classes)}" if classes else 'a'
    
    return None

def find_date_selector(container):
    """Find a selector for the date within a container"""
    date_patterns = [
        'time', '.date', '.time', '.published', '.datetime',
        '[class*=date]', '[class*=time]', '[class*=publish]',
        '[datetime]', '[class*=meta]'
    ]
    
    for pattern in date_patterns:
        elements = container.select(pattern)
        if elements:
            classes = elements[0].get('class', [])
            return f"{elements[0].name}.{'.'.join(classes)}" if classes else elements[0].name
    
    return None

def find_topic_selector(container):
    """Find a selector for the topic/category within a container"""
    topic_patterns = [
        '.category', '.tag', '.topic', '.section',
        '[class*=category]', '[class*=tag]', '[class*=topic]', '[class*=section]'
    ]
    
    for pattern in topic_patterns:
        elements = container.select(pattern)
        if elements:
            classes = elements[0].get('class', [])
            return f"{elements[0].name}.{'.'.join(classes)}" if classes else elements[0].name
    
    return None

def analyze_pagination(soup, url):
    """
    Analyze pagination mechanisms on the page
    
    Args:
        soup (BeautifulSoup): Parsed HTML
        url (str): URL of the page
    
    Returns:
        dict: Pagination information
    """
    pagination_info = {
        "type": "unknown",
        "selectors": [],
        "examples": []
    }
    
    # Check for standard pagination links
    pagination_patterns = [
        '.pagination', '.pager', '.pages', 'ul.page-numbers',
        '[class*=pagination]', '[class*=pager]', '[class*=pages]'
    ]
    
    for pattern in pagination_patterns:
        pagination = soup.select(pattern)
        if pagination:
            pagination_info["type"] = "standard_links"
            pagination_info["selectors"].append(pattern)
            
            # Find next page link
            next_links = soup.select('.next, .next-page, [class*=next], [rel=next]')
            if next_links:
                for link in next_links:
                    if link.name == 'a' and link.get('href'):
                        pagination_info["selectors"].append(f"{link.name}.{'.'.join(link.get('class', []))}")
                        pagination_info["examples"].append(urljoin(url, link['href']))
            
            break
    
    # Check for load more button
    if pagination_info["type"] == "unknown":
        load_more_patterns = [
            'button:contains("Load More")', 'a:contains("Load More")',
            '[class*=load-more]', '[id*=load-more]',
            'button:contains("Show More")', 'a:contains("Show More")'
        ]
        
        for pattern in load_more_patterns:
            elements = soup.select(pattern)
            if elements:
                pagination_info["type"] = "load_more"
                pagination_info["selectors"].append(pattern)
                
                # Look for data attributes
                for element in elements:
                    for attr, value in element.attrs.items():
                        if 'data' in attr:
                            pagination_info["examples"].append(f"{attr}: {value}")
                
                break
    
    # Check for infinite scroll (look for script patterns)
    if pagination_info["type"] == "unknown":
        scripts = soup.find_all('script')
        for script in scripts:
            script_text = script.string if script.string else ""
            if script_text and any(term in script_text.lower() for term in ['infinite', 'scroll', 'loadmore', 'ajax']):
                pagination_info["type"] = "infinite_scroll"
                pagination_info["examples"].append("Found script with infinite scroll related terms")
                break
    
    return pagination_info

def analyze_date_formats(soup):
    """
    Analyze potential date formats on the page
    
    Args:
        soup (BeautifulSoup): Parsed HTML
    
    Returns:
        list: Potential date formats
    """
    date_formats = []
    
    # Find elements that might contain dates
    date_elements = soup.select('time, [datetime], .date, .published, [class*=date], [class*=time], [class*=publish]')
    
    for element in date_elements[:5]:  # Look at first 5 only
        date_text = element.get_text(strip=True)
        date_attr = element.get('datetime', '')
        
        date_formats.append({
            'selector': f"{element.name}.{'.'.join(element.get('class', []))}" if element.get('class') else element.name,
            'text': date_text,
            'datetime_attr': date_attr
        })
    
    return date_formats

def main():
    parser = argparse.ArgumentParser(description='Inspect a page to help with creating a scraper')
    parser.add_argument('--url', type=str, required=True, help='URL to inspect')
    parser.add_argument('--output-dir', type=str, default=None, help='Directory to save analysis')
    parser.add_argument('--proxy-type', choices=['none', 'static', 'residential', 'auto'], 
                        default='auto', help='Proxy type to use')
    parser.add_argument('--no-save-html', action='store_true', help='Do not save the full HTML')
    
    args = parser.parse_args()
    
    inspect_page(args.url, args.output_dir, args.proxy_type, not args.no_save_html)

if __name__ == "__main__":
    main()