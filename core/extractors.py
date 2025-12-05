import logging
import asyncio
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from datetime import datetime

import newspaper
import trafilatura
from .schemas import ScrapedArticle
from utils.newspaper_parser import NewspaperParser # Reuse existing proxy logic if possible, or reimplement
from utils.browser import run_browser_task

logger = logging.getLogger(__name__)

class BaseExtractor(ABC):
    """Abstract base class for content extractors"""
    
    @abstractmethod
    def extract(self, url: str, html: str, title_hint: str = None) -> Optional[ScrapedArticle]:
        """
        Extract content from HTML.
        
        Args:
            url: The URL of the page
            html: The raw HTML content
            title_hint: Optional title extracted from other sources (e.g. metadata)
            
        Returns:
            ScrapedArticle object or None if extraction fails
        """
        pass

class NewspaperExtractor(BaseExtractor):
    """Extractor using newspaper4k"""
    
    def extract(self, url: str, html: str, title_hint: str = None) -> Optional[ScrapedArticle]:
        try:
            # newspaper4k usually fetches itself, but we can pass html
            article = newspaper.Article(url)
            article.download(input_html=html)
            article.parse()
            
            # Use hint if newspaper failed to find title
            title = article.title
            if not title and title_hint:
                title = title_hint.strip()
            
            # Basic validation before creating model
            if not title or not article.text:
                logger.warning(f"NewspaperExtractor validation failed: title='{title}', text_len={len(article.text) if article.text else 0}")
                return None
                
            return ScrapedArticle(
                url=url,
                title=title,
                content=article.text,
                author=', '.join(article.authors) if article.authors else None,
                published_date=article.publish_date,
                source='newspaper4k',
                metadata={
                    'top_image': article.top_image,
                    'keywords': article.keywords,
                    'summary': article.summary
                }
            )
        except Exception as e:
            logger.debug(f"NewspaperExtractor failed for {url}: {e}")
            return None

class TrafilaturaExtractor(BaseExtractor):
    """Extractor using trafilatura"""
    
    def extract(self, url: str, html: str, title_hint: str = None) -> Optional[ScrapedArticle]:
        try:
            # trafilatura.bare_extraction returns a Document object or dict
            extracted = trafilatura.bare_extraction(html, url=url)
            
            if not extracted:
                return None
                
            # Convert to dict if it's a Document object
            if hasattr(extracted, 'as_dict'):
                data = extracted.as_dict()
            elif isinstance(extracted, dict):
                data = extracted
            else:
                return None

            if not data.get('text'):
                return None
            
            # Use hint if trafilatura failed to find title
            title = data.get('title')
            if not title and title_hint:
                title = title_hint.strip()
                
            return ScrapedArticle(
                url=url,
                title=title or '',
                content=data.get('text'),
                author=data.get('author'),
                published_date=data.get('date'), 
                source='trafilatura',
                metadata={
                    'description': data.get('description'),
                    'sitename': data.get('sitename'),
                    'categories': data.get('categories'),
                    'tags': data.get('tags'),
                    'fingerprint': data.get('fingerprint'),
                    'license': data.get('license')
                }
            )
        except Exception as e:
            logger.debug(f"TrafilaturaExtractor failed for {url}: {e}")
            return None

class SmartExtractor:
    """
    Intelligent extractor that tries multiple strategies in order.
    Strategies:
    1. 'newspaper': Use newspaper4k on provided HTML
    2. 'trafilatura': Use trafilatura on provided HTML
    3. 'playwright': Fetch rendered HTML via browser, then try trafilatura
    """
    
    def __init__(self, strategies: List[str] = None):
        self.strategies = strategies or ['newspaper', 'trafilatura', 'playwright']
        
    def extract(self, url: str, html: str, title_hint: str = None) -> Optional[ScrapedArticle]:
        """
        Attempt extraction using configured strategies.
        """
        for strategy in self.strategies:
            try:
                result = None
                if strategy == 'newspaper':
                    result = NewspaperExtractor().extract(url, html, title_hint)
                elif strategy == 'trafilatura':
                    result = TrafilaturaExtractor().extract(url, html, title_hint)
                elif strategy == 'playwright':
                    # Only try playwright if we haven't succeeded yet
                    logger.info(f"Falling back to Playwright for {url}")
                    result = self._extract_with_playwright(url, title_hint)
                
                if result:
                    logger.info(f"Successfully extracted {url} using {strategy}")
                    return result
                    
            except Exception as e:
                logger.warning(f"Strategy {strategy} failed for {url}: {e}")
                continue
                
        logger.error(f"All extraction strategies failed for {url}")
        return None

    async def extract_async(self, url: str, html: str, title_hint: str = None) -> Optional[ScrapedArticle]:
        """
        Async version of extract method.
        """
        for strategy in self.strategies:
            logger.info(f"Trying strategy: {strategy} for {url}")
            try:
                result = None
                if strategy == 'newspaper':
                    # Run sync extractors in thread pool to avoid blocking loop
                    result = await asyncio.to_thread(NewspaperExtractor().extract, url, html, title_hint)
                elif strategy == 'trafilatura':
                    result = await asyncio.to_thread(TrafilaturaExtractor().extract, url, html, title_hint)
                elif strategy == 'playwright':
                    logger.info(f"Falling back to Playwright for {url}")
                    result = await self._extract_with_playwright_async(url, title_hint)
                
                if result:
                    logger.info(f"Successfully extracted {url} using {strategy}")
                    return result
                else:
                    logger.warning(f"Strategy {strategy} returned None for {url}")
                    
            except Exception as e:
                logger.warning(f"Strategy {strategy} failed for {url}: {e}")
                import traceback
                logger.warning(traceback.format_exc())
                continue
                
        logger.error(f"All extraction strategies failed for {url}")
        return None

    async def _extract_with_playwright_async(self, url: str, title_hint: str = None) -> Optional[ScrapedArticle]:
        """Fetch via Playwright (async) and extract using Trafilatura"""
        try:
            logger.info(f"Starting Playwright fetch for {url}")
            from utils.browser import BrowserClient
            async with BrowserClient() as browser:
                logger.info("BrowserClient started")
                if await browser.goto(url):
                    logger.info("Browser navigated")
                    html = await browser.get_html()
                    logger.info(f"Got HTML from browser: {len(html)} bytes")
                    if html:
                        # Try Trafilatura on rendered HTML
                        return await asyncio.to_thread(TrafilaturaExtractor().extract, url, html, title_hint)
                else:
                    logger.warning("Browser navigation failed")
        except Exception as e:
            logger.error(f"Playwright fetch failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
        return None

    def _extract_with_playwright(self, url: str, title_hint: str = None) -> Optional[ScrapedArticle]:
        """Fetch via Playwright and extract using Trafilatura"""
        try:
            # Define async task
            async def fetch_task(browser):
                if await browser.goto(url):
                    return await browser.get_html()
                return None
            
            # Run sync
            html = asyncio.run(run_browser_task(fetch_task))
            
            if html:
                # Try Trafilatura on rendered HTML
                return TrafilaturaExtractor().extract(url, html, title_hint)
        except Exception as e:
            logger.error(f"Playwright fetch failed: {e}")
        return None
