import yaml
import os
from pathlib import Path
from typing import Dict, Any


class ConfigLoader:
    """Handles loading and merging project configurations"""
    
    def __init__(self, projects_dir: str = "projects"):
        self.projects_dir = Path(projects_dir)
    
    def load_project_config(self, project_name: str) -> Dict[str, Any]:
        """Load project configuration from YAML file"""
        config_path = self.projects_dir / project_name / "config.yaml"
        
        if not config_path.exists():
            raise FileNotFoundError(f"Project config not found: {config_path}")
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Validate required fields
        required_fields = ['project_name', 'spiders']
        for field in required_fields:
            if field not in config:
                raise ValueError(f"Missing required field '{field}' in project config")
        
        return config
    
    def get_spider_settings(self, project_name: str, spider_name: str) -> Dict[str, Any]:
        """Get Scrapy settings for a specific spider in a project"""
        config = self.load_project_config(project_name)
        
        # Start with default settings
        settings = {
            'BOT_NAME': 'scrapai',
            'SPIDER_MODULES': ['spiders'],
            'NEWSPIDER_MODULE': 'spiders',
            'ROBOTSTXT_OBEY': True,
            'USER_AGENT': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'DOWNLOAD_DELAY': 1,
            'CONCURRENT_REQUESTS': 4,
            'CONCURRENT_REQUESTS_PER_DOMAIN': 2,
            'AUTOTHROTTLE_ENABLED': True,
            'AUTOTHROTTLE_START_DELAY': 1,
            'AUTOTHROTTLE_MAX_DELAY': 10,
            'AUTOTHROTTLE_TARGET_CONCURRENCY': 2.0,
            'HTTPCACHE_ENABLED': True,
            'HTTPCACHE_EXPIRATION_SECS': 3600,
            'ITEM_PIPELINES': {
                'scrapers.pipelines.ScrapaiPipeline': 300,
            }
        }
        
        # Override with project-specific settings
        project_settings = config.get('settings', {})
        settings.update(project_settings)
        
        # Set output path
        output_format = config.get('output_format', 'json')
        timestamp = '%(time)s'
        
        settings['FEEDS'] = {
            f'projects/{project_name}/outputs/{spider_name}/{timestamp}.{output_format}': {
                'format': output_format,
                'overwrite': False,
            }
        }
        
        # Set log file path
        settings['LOG_FILE'] = f'projects/{project_name}/logs/{spider_name}.log'
        
        return settings
    
    def validate_spider_for_project(self, project_name: str, spider_name: str) -> bool:
        """Check if a spider is configured for a project"""
        config = self.load_project_config(project_name)
        configured_spiders = config.get('spiders', [])
        
        if spider_name not in configured_spiders:
            return False
        
        # Check if spider file exists
        spider_file = Path(f"spiders/{spider_name}.py")
        if not spider_file.exists():
            return False
        
        return True
    
    def get_project_spiders(self, project_name: str) -> list:
        """Get list of spiders configured for a project"""
        config = self.load_project_config(project_name)
        return config.get('spiders', [])
    
    def create_scrapy_settings_file(self, project_name: str, spider_name: str) -> str:
        """Create a temporary settings file for Scrapy"""
        settings = self.get_spider_settings(project_name, spider_name)
        
        # Create temporary settings file
        temp_dir = Path("temp")
        temp_dir.mkdir(exist_ok=True)
        
        settings_file = temp_dir / f"settings_{project_name}_{spider_name}.py"
        
        with open(settings_file, 'w') as f:
            f.write("# Auto-generated settings file\n")
            for key, value in settings.items():
                f.write(f"{key} = {repr(value)}\n")
        
        return str(settings_file)