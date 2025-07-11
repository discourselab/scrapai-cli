import scrapy
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import CrawlSpider, Rule
import re
from datetime import datetime


class BaseSpider(CrawlSpider):
    """Base spider with common functionality for all spiders"""
    
    def __init__(self, project_name=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.project_name = project_name
        
        # Set project-specific settings if provided
        if project_name:
            self.custom_settings = self.get_project_settings(project_name)
    
    def get_project_settings(self, project_name):
        """Override with project-specific settings"""
        return {
            'FEEDS': {
                f'projects/{project_name}/outputs/%(spider)s/%(time)s.json': {
                    'format': 'json',
                    'overwrite': False,
                }
            },
            'LOG_FILE': f'projects/{project_name}/logs/%(spider)s.log',
        }
    
    def parse_date(self, date_text):
        """Parse various date formats - common utility"""
        if not date_text:
            return None
        
        # Clean up the date text
        date_text = date_text.strip()
        
        # Common date patterns
        date_patterns = [
            r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}',  # ISO format
            r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
            r'\w+ \d{1,2}, \d{4}',  # Month DD, YYYY
            r'\d{1,2}/\d{1,2}/\d{4}',  # MM/DD/YYYY
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, date_text)
            if match:
                return match.group(0)
        
        return date_text
    
    def create_item(self, response, **kwargs):
        """Create standardized item structure"""
        return {
            'url': response.url,
            'title': kwargs.get('title', ''),
            'content': kwargs.get('content', ''),
            'published_date': kwargs.get('published_date'),
            'author': kwargs.get('author', ''),
            'source': self.name,
            'project': self.project_name,
            'scraped_at': datetime.now().isoformat(),
            **kwargs  # Allow additional fields
        }