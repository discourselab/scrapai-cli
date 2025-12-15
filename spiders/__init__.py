# Shared spiders package
"""
Dynamically generates spider classes from database.
This allows Scrapyd and other tools to discover spiders via 'scrapy list'.
"""
from .database_spider import DatabaseSpider

def _load_spiders_from_db():
    """Create a spider class for each spider in the database"""
    try:
        from core.db import get_db
        from core.models import Spider

        db = next(get_db())
        spiders = db.query(Spider).filter(Spider.active == True).all()

        for spider in spiders:
            # Dynamically create a class for each DB spider
            # This makes 'scrapy list' show all spiders individually
            spider_class = type(
                spider.name,  # Class name (e.g., 'instituteforliberty_org')
                (DatabaseSpider,),  # Inherit from DatabaseSpider
                {
                    'name': spider.name,  # Spider name for Scrapy
                    '_spider_name': spider.name,  # Store for __init__
                }
            )
            # Add to module globals so Scrapy can discover it
            globals()[spider.name] = spider_class

    except Exception as e:
        # During initial setup or if DB is unavailable, fail silently
        # The generic database_spider will still be available
        import logging
        logging.warning(f"Could not load spiders from database: {e}")

# Load spiders when module is imported
_load_spiders_from_db()