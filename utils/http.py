#!/usr/bin/env python3
import os
import time
import random
import requests
import logging
from dotenv import load_dotenv

# Use our centralized logging
from utils.logger import get_logger, setup_logging
logger = setup_logging('http_client', log_format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Load environment variables
load_dotenv()

class HttpClient:
    """
    Centralized HTTP client for making requests with proxy support,
    retry logic, and rotation.
    """
    def __init__(self, proxy_type='none', retry_count=4, timeout=30):
        """
        Initialize the HTTP client
        
        Args:
            proxy_type (str): Type of proxy to use: 'none', 'static', 'residential', or 'auto'
                              'auto' starts with no proxy, then tries static, then residential
            retry_count (int): Number of retries for failed requests
            timeout (int): Request timeout in seconds
        """
        self.session = requests.Session()
        self.retry_count = retry_count
        self.timeout = timeout
        self.proxy_type = proxy_type
        
        # Load static proxy settings
        self.static_proxy_username = os.getenv('STATIC_PROXY_USERNAME')
        self.static_proxy_password = os.getenv('STATIC_PROXY_PASSWORD')
        self.static_proxy_host = os.getenv('STATIC_PROXY_HOST')
        self.static_proxy_port = os.getenv('STATIC_PROXY_PORT')
        
        # Load residential proxy settings
        self.residential_proxy_username = os.getenv('RESIDENTIAL_PROXY_USERNAME')
        self.residential_proxy_password = os.getenv('RESIDENTIAL_PROXY_PASSWORD')
        self.residential_proxy_host = os.getenv('RESIDENTIAL_PROXY_HOST')
        self.residential_proxy_port = os.getenv('RESIDENTIAL_PROXY_PORT')
        
        # Validate proxy settings
        if proxy_type in ['static', 'auto'] and (not self.static_proxy_username or not self.static_proxy_password 
                          or not self.static_proxy_host or not self.static_proxy_port):
            logger.warning("Static proxy settings incomplete.")
            if proxy_type == 'static':
                logger.warning("Falling back to direct connections.")
                self.proxy_type = 'none'
        
        if proxy_type in ['residential', 'auto'] and (not self.residential_proxy_username or not self.residential_proxy_password 
                          or not self.residential_proxy_host or not self.residential_proxy_port):
            logger.warning("Residential proxy settings incomplete.")
            if proxy_type == 'residential':
                logger.warning("Falling back to direct connections.")
                self.proxy_type = 'none'
    
    def _get_random_user_agent(self):
        """Get a random user agent string"""
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:132.0) Gecko/20100101 Firefox/132.0"
        ]
        return random.choice(user_agents)
    
    def get_proxy_url(self, proxy_type):
        """
        Build proxy URL from environment settings
        
        Args:
            proxy_type (str): Type of proxy to use: 'static' or 'residential'
            
        Returns:
            str: Proxy URL
        """
        if proxy_type == 'static':
            return f"http://{self.static_proxy_username}:{self.static_proxy_password}@{self.static_proxy_host}:{self.static_proxy_port}"
        elif proxy_type == 'residential':
            return f"http://{self.residential_proxy_username}:{self.residential_proxy_password}@{self.residential_proxy_host}:{self.residential_proxy_port}"
        else:
            return None
    
    def _request(self, method, url, headers=None, data=None, json=None):
        """
        Make a request with retry logic and tiered proxy support
        
        Args:
            method (str): HTTP method (GET, POST, etc.)
            url (str): URL to request
            headers (dict, optional): Headers to use for the request
            data (dict, optional): Form data for POST requests
            json (dict, optional): JSON data for POST requests
            
        Returns:
            requests.Response or None: Response object if successful, None if all retries failed
        """
        # Default headers to make requests look more like a browser
        default_headers = {
            "User-Agent": self._get_random_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Sec-CH-UA": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": "\"macOS\"",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "DNT": "1",
            "Connection": "keep-alive"
        }
        
        # Merge with custom headers if provided
        request_headers = default_headers.copy()
        if headers:
            request_headers.update(headers)
            
        for attempt in range(self.retry_count):
            # Determine which proxy to use for this attempt
            current_proxy_type = 'none'
            
            # Auto proxy selection strategy
            if self.proxy_type == 'auto':
                if attempt == 0:
                    # First attempt: no proxy
                    current_proxy_type = 'none'
                elif attempt < 3:  
                    # Next attempts: static proxy
                    current_proxy_type = 'static'
                else:
                    # Last resort: residential proxy
                    current_proxy_type = 'residential'
                    logger.warning("Using expensive residential proxy as last resort")
            else:
                # Use the configured proxy type
                current_proxy_type = self.proxy_type
            
            try:
                # Configure proxy if needed
                proxies = None
                if current_proxy_type != 'none':
                    proxy_url = self.get_proxy_url(current_proxy_type)
                    if proxy_url:
                        proxies = {
                            'http': proxy_url,
                            'https': proxy_url
                        }
                        logger.info(f"Using {current_proxy_type} proxy for {method} request (attempt {attempt+1})")
                    else:
                        logger.warning(f"{current_proxy_type} proxy configuration is incomplete")
                else:
                    logger.info(f"Using direct connection (no proxy) for {method} attempt {attempt+1}")
                
                # Randomize the user agent slightly to avoid fingerprinting
                if "User-Agent" in request_headers and attempt > 0:
                    ua = request_headers["User-Agent"]
                    # Add a random comment to the user agent
                    comment_val = str(random.randint(1, 1000))
                    if "Chrome/" in ua and not "Chrome/Mobile" in ua:
                        request_headers["User-Agent"] = ua.replace("Chrome/", f"Chrome/Mobile Safari/{comment_val} ")
                
                # Make the request based on the method
                if method.upper() == 'GET':
                    response = self.session.get(
                        url, 
                        headers=request_headers,
                        proxies=proxies,
                        timeout=self.timeout
                    )
                elif method.upper() == 'POST':
                    response = self.session.post(
                        url, 
                        headers=request_headers,
                        data=data,
                        json=json,
                        proxies=proxies,
                        timeout=self.timeout
                    )
                else:
                    logger.error(f"Unsupported HTTP method: {method}")
                    return None
                
                # Check if successful
                if response.status_code == 200:
                    return response
                
                # Handle rate limiting
                if response.status_code == 429:
                    wait_time = min(2 ** attempt, 60)  # Exponential backoff
                    logger.warning(f"Rate limited (429). Waiting {wait_time}s before retry.")
                    time.sleep(wait_time)
                    continue
                
                # Log other errors
                logger.warning(f"{method} request failed with status code {response.status_code}")
                
            except Exception as e:
                logger.error(f"{method} request failed (attempt {attempt+1}/{self.retry_count}): {e}")
            
            # Exponential backoff with jitter for retries
            base_delay = min(2 ** (attempt + 1), 30)  # Cap at 30 seconds
            jitter = random.uniform(0.2, 0.8 * base_delay)  # Add 20-80% jitter for more human-like timing
            retry_delay = base_delay + jitter
            
            logger.info(f"Retrying in {retry_delay:.2f}s (attempt {attempt+1}/{self.retry_count})")
            time.sleep(retry_delay)
        
        logger.error(f"All {self.retry_count} attempts failed for {method} URL: {url}")
        return None
        
    def get(self, url, headers=None):
        """
        Make a GET request with retry logic and tiered proxy support
        
        Args:
            url (str): URL to request
            headers (dict, optional): Headers to use for the request
            
        Returns:
            requests.Response or None: Response object if successful, None if all retries failed
        """
        return self._request('GET', url, headers=headers)
        
    def post(self, url, headers=None, data=None, json=None):
        """
        Make a POST request with retry logic and tiered proxy support
        
        Args:
            url (str): URL to request
            headers (dict, optional): Headers to use for the request
            data (dict, optional): Form data for POST requests
            json (dict, optional): JSON data for POST requests
            
        Returns:
            requests.Response or None: Response object if successful, None if all retries failed
        """
        return self._request('POST', url, headers=headers, data=data, json=json)
    
    def check_proxy(self, proxy_type=None):
        """
        Test if the proxy is working by checking the IP
        
        Args:
            proxy_type (str, optional): Specify a proxy type to check, or None to use the current setting
            
        Returns:
            bool: True if proxy is working, False otherwise
        """
        try:
            # Save current proxy type
            original_proxy_type = self.proxy_type
            
            # Temporarily set proxy type if specified
            if proxy_type:
                self.proxy_type = proxy_type
            
            url = 'https://ip.decodo.com/json'
            response = self.get(url)
            
            # Restore original proxy type
            self.proxy_type = original_proxy_type
            
            if response and response.status_code == 200:
                ip_data = response.json()
                logger.info(f"Proxy check successful. IP: {ip_data.get('ip')}")
                return True
            
            return False
        except Exception as e:
            logger.error(f"Proxy check failed: {e}")
            return False


# Convenience function to get a client instance
def get_client(proxy_type='auto'):
    """
    Get a configured HTTP client instance
    
    Args:
        proxy_type (str): Type of proxy to use: 'none', 'static', 'residential', or 'auto'
                          'auto' starts with no proxy, then tries static, then residential
        
    Returns:
        HttpClient: Configured client instance
    """
    return HttpClient(proxy_type=proxy_type)


# Test the proxy if this script is run directly
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Test proxy configuration')
    parser.add_argument('--proxy-type', choices=['none', 'static', 'residential', 'auto'], 
                        default='auto', help='Proxy type to use')
    args = parser.parse_args()
    
    client = get_client(proxy_type=args.proxy_type)
    
    if args.proxy_type == 'auto':
        print("Testing all proxy types...")
        print("Direct connection:", client.check_proxy('none'))
        print("Static proxy:", client.check_proxy('static'))
        print("Residential proxy:", client.check_proxy('residential'))
    else:
        if client.check_proxy():
            print(f"✅ {args.proxy_type.capitalize()} proxy is working correctly")
        else:
            print(f"❌ {args.proxy_type.capitalize()} proxy check failed")