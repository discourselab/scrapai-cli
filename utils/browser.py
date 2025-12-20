#!/usr/bin/env python3
import os
import logging
import asyncio
from typing import List, Dict, Any, Optional, Callable
from playwright.async_api import async_playwright, Page, Browser

# Use centralized logging
from utils.logger import get_logger
logger = get_logger('browser_client')

class BrowserClient:
    """
    Headless browser client for handling JavaScript-based pagination and dynamic content.
    Uses Playwright to interact with websites that require JavaScript for pagination.
    """
    
    def __init__(self, headless: bool = True, proxy: Dict[str, str] = None):
        """
        Initialize the browser client
        
        Args:
            headless (bool): Whether to run the browser in headless mode
            proxy (Dict[str, str]): Proxy configuration with keys: server, username, password
        """
        self.headless = headless
        self.proxy = proxy
        self.browser = None
        self.context = None
        self.page = None
        
    async def __aenter__(self):
        """Set up the browser when used as a context manager"""
        await self.start()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up browser resources when exiting context manager"""
        await self.close()
        
    async def start(self):
        """Start the browser"""
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=[
                    '--no-first-run',
                    '--no-default-browser-check',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor'
                ]
            )
            context_options = {
                "viewport": {"width": 1366, "height": 768},
                "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "extra_http_headers": {
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Cache-Control': 'no-cache',
                    'Sec-CH-UA': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                    'Sec-CH-UA-Mobile': '?0',
                    'Sec-CH-UA-Platform': '"macOS"',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1'
                },
                "java_script_enabled": True,
                "locale": 'en-US'
            }
            
            if self.proxy:
                context_options["proxy"] = self.proxy
                logger.info(f"Using proxy: {self.proxy['server']}")
            
            self.context = await self.browser.new_context(**context_options)
            self.page = await self.context.new_page()
            
            # Add stealth measures to avoid bot detection
            await self.page.add_init_script("""
                // Override webdriver property
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                });
                
                // Override plugins
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });
                
                // Override languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en'],
                });
            """)
            logger.info("Browser started successfully")
        except Exception as e:
            logger.error(f"Error starting browser: {e}")
            raise
            
    async def close(self):
        """Close the browser and clean up resources"""
        try:
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if hasattr(self, 'playwright'):
                await self.playwright.stop()
            logger.info("Browser closed successfully")
        except Exception as e:
            logger.error(f"Error closing browser: {e}")
            
    async def goto(self, url: str, wait_for_selector: str = None, additional_delay: float = 0,
                   enable_scroll: bool = False, max_scrolls: int = 5, scroll_delay: float = 1.0) -> bool:
        """
        Navigate to a URL with optional wait conditions and infinite scroll support

        Args:
            url (str): URL to navigate to
            wait_for_selector (str, optional): CSS selector to wait for after navigation
            additional_delay (float, optional): Additional seconds to wait after page load
            enable_scroll (bool, optional): Whether to perform infinite scroll after loading
            max_scrolls (int, optional): Maximum number of scrolls to perform
            scroll_delay (float, optional): Delay between scrolls in seconds

        Returns:
            bool: True if navigation was successful
        """
        try:
            await self.page.goto(url, wait_until="networkidle", timeout=60000)
            logger.info(f"Navigated to {url}")

            # Wait for specific selector if provided
            if wait_for_selector:
                try:
                    await self.page.wait_for_selector(wait_for_selector, timeout=30000)
                    logger.info(f"Selector '{wait_for_selector}' found on {url}")
                except Exception as e:
                    logger.warning(f"Timeout waiting for selector '{wait_for_selector}' on {url}: {e}")

            # Additional delay for JS that runs after network idle
            if additional_delay > 0:
                logger.info(f"Waiting additional {additional_delay} seconds for JS to complete")
                await asyncio.sleep(additional_delay)

            # Perform infinite scroll if enabled
            if enable_scroll:
                logger.info(f"Starting infinite scroll: {max_scrolls} scrolls with {scroll_delay}s delay")
                for i in range(max_scrolls):
                    try:
                        # Get current page height
                        prev_height = await self.page.evaluate("document.body.scrollHeight")

                        # Scroll to bottom
                        await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        logger.info(f"Scroll {i+1}/{max_scrolls} completed")

                        # Wait for content to load
                        await asyncio.sleep(scroll_delay)

                        # Check if new content loaded (page height increased)
                        new_height = await self.page.evaluate("document.body.scrollHeight")
                        if new_height == prev_height:
                            logger.info(f"No new content loaded after scroll {i+1}, stopping")
                            break

                    except Exception as e:
                        logger.warning(f"Error during scroll {i+1}: {e}")
                        break

                logger.info(f"Infinite scroll completed")

            return True
        except Exception as e:
            logger.error(f"Error navigating to {url}: {e}")
            return False
            
    async def get_html(self) -> str:
        """
        Get the current page HTML
        
        Returns:
            str: HTML content of the page
        """
        try:
            return await self.page.content()
        except Exception as e:
            logger.error(f"Error getting page HTML: {e}")
            return ""
            
    async def paginate_by_click(self, selector: str, max_clicks: int = 5, 
                                wait_for_selector: str = None, 
                                wait_time: float = 2.0) -> List[str]:
        """
        Handle pagination by clicking on elements and collecting HTML after each click
        
        Args:
            selector (str): CSS selector for the pagination element to click
            max_clicks (int): Maximum number of times to click
            wait_for_selector (str, optional): Selector to wait for after clicking
            wait_time (float): Time to wait after clicking (in seconds)
            
        Returns:
            List[str]: List of HTML content from each page
        """
        html_pages = [await self.get_html()]  # Start with current page
        
        for i in range(max_clicks):
            try:
                # Check if the pagination element exists
                element = await self.page.query_selector(selector)
                if not element:
                    logger.info(f"No more pagination elements found. Stopping after {i} clicks.")
                    break
                    
                # Click the element
                await element.click()
                logger.info(f"Clicked pagination element ({i+1}/{max_clicks})")
                
                # Wait for content to load
                if wait_for_selector:
                    try:
                        await self.page.wait_for_selector(wait_for_selector, timeout=10000)
                    except Exception as e:
                        logger.warning(f"Timeout waiting for selector after click {i+1}: {e}")
                
                # Additional wait to ensure dynamic content loads
                await asyncio.sleep(wait_time)
                
                # Get the updated HTML
                html_pages.append(await self.get_html())
                
            except Exception as e:
                logger.error(f"Error during pagination click {i+1}: {e}")
                break
                
        return html_pages
        
    async def paginate_by_scroll(self, max_scrolls: int = 5, 
                                scroll_delay: float = 1.0, 
                                scroll_amount: int = 1000) -> List[str]:
        """
        Handle pagination by scrolling and collecting HTML after each scroll
        
        Args:
            max_scrolls (int): Maximum number of times to scroll
            scroll_delay (float): Time to wait after scrolling (in seconds)
            scroll_amount (int): Pixels to scroll each time
            
        Returns:
            List[str]: List of HTML content from each scroll
        """
        html_pages = [await self.get_html()]  # Start with current page
        
        for i in range(max_scrolls):
            try:
                # Scroll down
                await self.page.evaluate(f"window.scrollBy(0, {scroll_amount})")
                logger.info(f"Scrolled down ({i+1}/{max_scrolls})")
                
                # Wait for content to load
                await asyncio.sleep(scroll_delay)
                
                # Get the updated HTML
                html_pages.append(await self.get_html())
                
            except Exception as e:
                logger.error(f"Error during pagination scroll {i+1}: {e}")
                break
                
        return html_pages
        
    async def paginate_by_load_more(self, selector: str, max_clicks: int = 5, 
                                   wait_time: float = 2.0,
                                   content_selector: str = None) -> List[str]:
        """
        Handle pagination by clicking 'Load More' buttons
        
        Args:
            selector (str): CSS selector for the 'Load More' button
            max_clicks (int): Maximum number of times to click
            wait_time (float): Time to wait after clicking (in seconds)
            content_selector (str, optional): Selector for content container to check for new content
            
        Returns:
            List[str]: List of HTML content from each page
        """
        html_pages = [await self.get_html()]  # Start with current page
        
        for i in range(max_clicks):
            try:
                # Check if the Load More button exists
                element = await self.page.query_selector(selector)
                if not element:
                    logger.info(f"No more 'Load More' buttons found. Stopping after {i} clicks.")
                    break
                
                # Check if button is visible (some sites have hidden pagination elements)
                is_visible = await element.is_visible()
                if not is_visible:
                    logger.info(f"'Load More' button is not visible. Stopping after {i} clicks.")
                    break
                    
                # Optional: Count current content items to check if new ones appear
                content_count_before = 0
                if content_selector:
                    content_items = await self.page.query_selector_all(content_selector)
                    content_count_before = len(content_items)
                
                # Click the button
                await element.click()
                logger.info(f"Clicked 'Load More' button ({i+1}/{max_clicks})")
                
                # Wait for content to load
                await asyncio.sleep(wait_time)
                
                # Optional: Check if new content was loaded
                if content_selector:
                    content_items = await self.page.query_selector_all(content_selector)
                    content_count_after = len(content_items)
                    
                    if content_count_after <= content_count_before:
                        logger.info(f"No new content loaded after click {i+1}. Stopping.")
                        break
                        
                    logger.info(f"Loaded {content_count_after - content_count_before} new items")
                
                # Get the updated HTML
                html_pages.append(await self.get_html())
                
            except Exception as e:
                logger.error(f"Error during 'Load More' click {i+1}: {e}")
                break
                
        return html_pages
        
    async def paginate_by_url(self, url_pattern: str, max_pages: int = 5, 
                             start_page: int = 2) -> List[str]:
        """
        Handle pagination by navigating to different URLs
        
        Args:
            url_pattern (str): URL pattern with {} where page number should be inserted
            max_pages (int): Maximum number of pages to navigate to
            start_page (int): Page number to start from
            
        Returns:
            List[str]: List of HTML content from each page
        """
        html_pages = [await self.get_html()]  # Start with current page
        
        for i in range(start_page, start_page + max_pages):
            try:
                # Construct the URL for this page
                page_url = url_pattern.format(i)
                
                # Navigate to the page
                success = await self.goto(page_url)
                if not success:
                    logger.warning(f"Failed to navigate to page {i}. Stopping pagination.")
                    break
                    
                logger.info(f"Navigated to page {i}")
                
                # Get the HTML from this page
                html_pages.append(await self.get_html())
                
            except Exception as e:
                logger.error(f"Error during URL pagination to page {i}: {e}")
                break
                
        return html_pages
        
# Convenience function to run browser operations
async def run_browser_task(task_func, *args, **kwargs):
    """
    Run a browser task with proper setup and teardown
    
    Args:
        task_func (callable): Async function to run with the browser
        *args, **kwargs: Arguments to pass to the task function
        
    Returns:
        Any: Result of the task function
    """
    async with BrowserClient(headless=True) as browser:
        return await task_func(browser, *args, **kwargs)

# Synchronous wrapper for browser pagination
def paginate_with_browser(url: str, method: str = 'click', 
                         selector: str = None, max_pages: int = 5, 
                         **kwargs) -> List[str]:
    """
    Synchronous wrapper for browser pagination
    
    Args:
        url (str): URL to navigate to
        method (str): Pagination method ('click', 'scroll', 'load_more', or 'url')
        selector (str): CSS selector for pagination elements (if applicable)
        max_pages (int): Maximum number of pages to navigate
        **kwargs: Additional arguments for specific pagination methods
        
    Returns:
        List[str]: List of HTML content from each page
    """
    async def _paginate(browser, url, method, selector, max_pages, **kwargs):
        await browser.goto(url)
        
        if method == 'click':
            return await browser.paginate_by_click(selector, max_pages, **kwargs)
        elif method == 'scroll':
            return await browser.paginate_by_scroll(max_pages, **kwargs)
        elif method == 'load_more':
            return await browser.paginate_by_load_more(selector, max_pages, **kwargs)
        elif method == 'url':
            url_pattern = kwargs.get('url_pattern', url + '?page={}')
            return await browser.paginate_by_url(url_pattern, max_pages, **kwargs)
        else:
            logger.error(f"Unknown pagination method: {method}")
            return [await browser.get_html()]
    
    # Run the async function in a new event loop
    return asyncio.run(_paginate(
        browser=None,  # Will be created by the context manager
        url=url, 
        method=method, 
        selector=selector, 
        max_pages=max_pages, 
        **kwargs
    ))

