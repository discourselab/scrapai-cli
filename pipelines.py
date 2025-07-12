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