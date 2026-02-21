from datetime import datetime
from itemadapter import ItemAdapter

class ScrapaiPipeline:
    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        
        # Add scraped timestamp
        adapter['scraped_at'] = datetime.now().isoformat()
        
        # Add source
        adapter['source'] = spider.name
        
        return item

class DatabasePipeline:
    def __init__(self):
        from core.db import SessionLocal
        self.db = SessionLocal()
        self.buffer = []
        self.batch_size = 100
        
    def process_item(self, item, spider):
        self.buffer.append(item)
        if len(self.buffer) >= self.batch_size:
            self._flush(spider)
        return item
        
    def close_spider(self, spider):
        if self.buffer:
            self._flush(spider)
        self.db.close()
            
    def _flush(self, spider):
        from core.models import ScrapedItem
        from sqlalchemy.exc import IntegrityError
        
        if not self.buffer:
            return

        # 1. Deduplication (Batch Query)
        urls = [i['url'] for i in self.buffer]
        try:
            existing_items = self.db.query(ScrapedItem.url).filter(ScrapedItem.url.in_(urls)).all()
            existing_urls = {r[0] for r in existing_items}
        except Exception as e:
            spider.logger.error(f"Error checking duplicates: {e}")
            existing_urls = set()
        
        # 2. Filter and Create Objects
        new_objects = []
        for item in self.buffer:
            if item['url'] in existing_urls:
                spider.logger.debug(f"Item already exists: {item['url']}")
                continue
                
            db_item = ScrapedItem(
                spider_id=item['spider_id'],
                url=item['url'],
                title=item.get('title'),
                content=item.get('content'),
                published_date=item.get('published_date'),
                author=item.get('author'),
                metadata_json=item.get('metadata')
            )
            new_objects.append(db_item)
            
        # 3. Bulk Insert
        if new_objects:
            try:
                self.db.add_all(new_objects)
                self.db.commit()
                spider.logger.info(f"Saved {len(new_objects)} items to DB (Batch)")
            except Exception as e:
                self.db.rollback()
                spider.logger.error(f"Error saving batch: {e}")
        
        self.buffer = []