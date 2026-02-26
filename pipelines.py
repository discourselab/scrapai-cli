from datetime import datetime
from itemadapter import ItemAdapter


def _serialize_datetime_recursive(obj):
    """Recursively convert datetime objects to ISO strings for JSON serialization.

    Handles nested dicts and lists from nested_list extraction.
    """
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: _serialize_datetime_recursive(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_serialize_datetime_recursive(item) for item in obj]
    else:
        return obj


class ScrapaiPipeline:
    @classmethod
    def from_crawler(cls, crawler):
        """Create pipeline from crawler (Scrapy convention)."""
        pipe = cls()
        pipe.crawler = crawler
        return pipe

    def process_item(self, item):
        adapter = ItemAdapter(item)

        # Add scraped timestamp
        adapter["scraped_at"] = datetime.now().isoformat()

        # Add source (get spider name from crawler)
        spider_name = (
            self.crawler.spider.name
            if hasattr(self, "crawler") and self.crawler.spider
            else "unknown"
        )
        adapter["source"] = spider_name

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
        if not self.buffer:
            return

        # 1. Deduplication (Batch Query)
        urls = [i["url"] for i in self.buffer]
        try:
            existing_items = (
                self.db.query(ScrapedItem.url).filter(ScrapedItem.url.in_(urls)).all()
            )
            existing_urls = {r[0] for r in existing_items}
        except Exception as e:
            spider.logger.error(f"Error checking duplicates: {e}")
            existing_urls = set()

        # Standard fields that map to ScrapedItem columns
        STANDARD_FIELDS = {
            "url",
            "title",
            "content",
            "author",
            "published_date",
            "spider_id",
            "spider_name",
            "source",
            "metadata",
            "html",
            "extracted_at",
            "_callback",
            "scraped_at",
        }

        # 2. Filter and Create Objects
        new_objects = []
        for item in self.buffer:
            if item["url"] in existing_urls:
                spider.logger.debug(f"Item already exists: {item['url']}")
                continue

            # Check if this is a callback-extracted item
            if "_callback" in item:
                # Separate custom fields from standard fields
                custom_fields = {
                    k: v for k, v in item.items() if k not in STANDARD_FIELDS
                }

                # Convert datetime objects to ISO strings for JSON serialization
                for key, value in list(custom_fields.items()):
                    if isinstance(value, datetime):
                        custom_fields[key] = value.isoformat()
                    elif isinstance(value, list):
                        # Handle lists that might contain datetime objects
                        custom_fields[key] = [
                            v.isoformat() if isinstance(v, datetime) else v
                            for v in value
                        ]
                    elif isinstance(value, dict):
                        # Handle nested dicts (from nested_list extraction)
                        custom_fields[key] = _serialize_datetime_recursive(value)

                custom_fields["_callback"] = item["_callback"]
                metadata = custom_fields
            else:
                # Legacy article extraction - use existing metadata
                metadata = item.get("metadata")

            db_item = ScrapedItem(
                spider_id=item["spider_id"],
                url=item["url"],
                title=item.get("title"),
                content=item.get("content"),
                published_date=item.get("published_date"),
                author=item.get("author"),
                metadata_json=metadata,
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
