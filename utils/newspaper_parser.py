#!/usr/bin/env python3
import newspaper
import logging
from datetime import datetime
from typing import Dict, Optional, Any
from .http import get_client
from .logger import setup_logging

logger = setup_logging('newspaper_parser')


class NewspaperParser:
    """
    Shared newspaper4k-based parser with proxy support and standardized output
    """
    
    def __init__(self, proxy_type='auto'):
        """
        Initialize the newspaper parser
        
        Args:
            proxy_type (str): Type of proxy to use: 'none', 'static', 'residential', or 'auto'
        """
        self.proxy_type = proxy_type
        self.http_client = get_client(proxy_type=proxy_type)
        
    def _get_proxies_dict(self) -> Optional[Dict[str, str]]:
        """Get proxies in the format newspaper4k expects"""
        if self.proxy_type == 'none':
            return None
            
        proxy_url = None
        if self.proxy_type == 'static':
            proxy_url = self.http_client.get_proxy_url('static')
        elif self.proxy_type == 'residential':
            proxy_url = self.http_client.get_proxy_url('residential')
        elif self.proxy_type == 'auto':
            # Try static first for auto mode
            proxy_url = self.http_client.get_proxy_url('static')
            if not proxy_url:
                proxy_url = self.http_client.get_proxy_url('residential')
        
        if proxy_url:
            return {
                'http': proxy_url,
                'https': proxy_url
            }
        return None
    
    def parse_article(self, url: str, source_name: str = None) -> Optional[Dict[str, Any]]:
        """
        Parse article using newspaper4k with proxy support
        
        Args:
            url (str): Article URL
            source_name (str, optional): Source name for the article
            
        Returns:
            dict: Extracted article data or None if parsing fails
        """
        try:
            # Get proxy configuration
            proxies = self._get_proxies_dict()
            
            if proxies:
                logger.info(f"Parsing {url} with {self.proxy_type} proxy")
                # Create article with proxies
                article = newspaper.article(url, proxies=proxies)
            else:
                logger.info(f"Parsing {url} with direct connection")
                # Create article without proxies
                article = newspaper.article(url)
            
            # Build standardized article data with all newspaper4k fields
            article_data = {
                'url': url,
                'title': article.title,
                'content': article.text,
                'authors': list(article.authors) if article.authors else [],
                'author': ', '.join(article.authors) if article.authors else '',
                'published_date': article.publish_date.isoformat() if article.publish_date else None,
                'top_image': article.top_image,
                'images': list(article.images) if article.images else [],
                'meta_data': article.meta_data,
                'summary': getattr(article, 'summary', ''),
                'keywords': list(getattr(article, 'keywords', [])),
                'meta_description': getattr(article, 'meta_description', ''),
                'meta_keywords': getattr(article, 'meta_keywords', ''),
                'canonical_link': getattr(article, 'canonical_link', ''),
                'source': source_name or self._extract_domain(url),
                'extracted_at': datetime.now().isoformat(),
                'parser_version': 'newspaper4k',
                'proxy_type': self.proxy_type
            }
            
            # Validate essential fields
            if not article_data['title'] or not article_data['content']:
                logger.warning(f"Missing essential content for {url}")
                return None
            
            # Clean content
            article_data['content'] = self._clean_content(article_data['content'])
            article_data['title'] = self._clean_title(article_data['title'])
            
            logger.info(f"Successfully parsed article: {article_data['title'][:100]}...")
            return article_data
            
        except Exception as e:
            logger.error(f"Error parsing {url}: {e}")
            return None
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain name from URL for source field"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            # Remove www. prefix
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        except Exception:
            return 'unknown'
    
    def _clean_content(self, content: str) -> str:
        """Clean and normalize article content"""
        if not content:
            return ''
        
        # Remove extra whitespace and normalize line breaks
        content = ' '.join(content.split())
        
        # Remove common footer/header text that newspaper4k might miss
        unwanted_phrases = [
            'Share this article',
            'Follow us on',
            'Subscribe to',
            'Sign up for',
            'Click here to',
            'Read more:',
            'Related articles:',
            'Advertisement'
        ]
        
        for phrase in unwanted_phrases:
            if phrase in content:
                # Remove the phrase and everything after it if it's at the end
                if content.endswith(phrase):
                    content = content[:-len(phrase)].strip()
                # Remove standalone phrases
                content = content.replace(phrase, '').strip()
        
        return content
    
    def _clean_title(self, title: str) -> str:
        """Clean and normalize article title"""
        if not title:
            return ''
        
        # Remove site name suffixes (e.g., "Article Title - Site Name")
        separators = [' - ', ' | ', ' :: ', ' — ']
        for sep in separators:
            if sep in title:
                parts = title.split(sep)
                if len(parts) > 1:
                    # Keep the first part (usually the actual title)
                    title = parts[0].strip()
                    break
        
        return title.strip()
    
    def parse_multiple(self, urls: list, source_name: str = None) -> list:
        """
        Parse multiple articles
        
        Args:
            urls (list): List of article URLs
            source_name (str, optional): Source name for all articles
            
        Returns:
            list: List of extracted article data (successful parses only)
        """
        results = []
        total = len(urls)
        
        for i, url in enumerate(urls, 1):
            logger.info(f"Parsing article {i}/{total}: {url}")
            
            article_data = self.parse_article(url, source_name)
            if article_data:
                results.append(article_data)
            else:
                logger.warning(f"Failed to parse article {i}/{total}: {url}")
        
        logger.info(f"Successfully parsed {len(results)}/{total} articles")
        return results


# Convenience functions for backward compatibility and ease of use
def parse_article(url: str, source_name: str = None, proxy_type: str = 'auto') -> Optional[Dict[str, Any]]:
    """
    Quick function to parse a single article using simplified newspaper4k API
    
    Args:
        url (str): Article URL
        source_name (str, optional): Source name for the article
        proxy_type (str): Type of proxy to use
        
    Returns:
        dict: Extracted article data or None if parsing fails
    """
    try:
        # Get proxy configuration if needed
        if proxy_type != 'none':
            http_client = get_client(proxy_type=proxy_type)
            proxy_url = None
            
            if proxy_type == 'static':
                proxy_url = http_client.get_proxy_url('static')
            elif proxy_type == 'residential':
                proxy_url = http_client.get_proxy_url('residential')
            elif proxy_type == 'auto':
                proxy_url = http_client.get_proxy_url('static')
                if not proxy_url:
                    proxy_url = http_client.get_proxy_url('residential')
            
            if proxy_url:
                proxies = {'http': proxy_url, 'https': proxy_url}
                logger.info(f"Parsing {url} with {proxy_type} proxy")
                article = newspaper.article(url, proxies=proxies)
            else:
                logger.info(f"Parsing {url} with direct connection (proxy config incomplete)")
                article = newspaper.article(url)
        else:
            logger.info(f"Parsing {url} with direct connection")
            article = newspaper.article(url)
        
        # Extract domain for source if not provided
        if not source_name:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            source_name = parsed.netloc.lower()
            if source_name.startswith('www.'):
                source_name = source_name[4:]
        
        # Build article data with all available fields
        article_data = {
            'url': url,
            'title': article.title,
            'content': article.text,
            'authors': list(article.authors) if article.authors else [],
            'author': ', '.join(article.authors) if article.authors else '',
            'published_date': article.publish_date.isoformat() if article.publish_date else None,
            'top_image': article.top_image,
            'images': list(article.images) if article.images else [],
            'meta_data': article.meta_data,
            'summary': getattr(article, 'summary', ''),
            'keywords': list(getattr(article, 'keywords', [])),
            'meta_description': getattr(article, 'meta_description', ''),
            'meta_keywords': getattr(article, 'meta_keywords', ''),
            'canonical_link': getattr(article, 'canonical_link', ''),
            'source': source_name,
            'extracted_at': datetime.now().isoformat(),
            'parser_version': 'newspaper4k',
            'proxy_type': proxy_type
        }
        
        # Validate essential fields
        if not article_data['title'] or not article_data['content']:
            logger.warning(f"Missing essential content for {url}")
            return None
        
        logger.info(f"Successfully parsed: {article_data['title'][:100]}...")
        return article_data
        
    except Exception as e:
        logger.error(f"Error parsing {url}: {e}")
        return None


def parse_multiple_articles(urls: list, source_name: str = None, proxy_type: str = 'auto') -> list:
    """
    Quick function to parse multiple articles
    
    Args:
        urls (list): List of article URLs
        source_name (str, optional): Source name for all articles
        proxy_type (str): Type of proxy to use
        
    Returns:
        list: List of extracted article data (successful parses only)
    """
    parser = NewspaperParser(proxy_type=proxy_type)
    return parser.parse_multiple(urls, source_name)


if __name__ == "__main__":
    # Test the parser
    import argparse
    
    parser_args = argparse.ArgumentParser(description='Test newspaper parser')
    parser_args.add_argument('url', help='URL to parse')
    parser_args.add_argument('--proxy-type', choices=['none', 'static', 'residential', 'auto'], 
                           default='auto', help='Proxy type to use')
    parser_args.add_argument('--source', help='Source name for the article')
    
    args = parser_args.parse_args()
    
    result = parse_article(args.url, args.source, args.proxy_type)
    
    if result:
        print(f"✅ Successfully parsed: {result['title']}")
        print(f"📄 Content length: {len(result['content'])} characters")
        print(f"👤 Authors: {result['author']}")
        print(f"📅 Published: {result['published_date']}")
    else:
        print("❌ Failed to parse article")