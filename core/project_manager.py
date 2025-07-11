import os
import yaml
from pathlib import Path
from typing import List, Dict, Optional


class ProjectManager:
    """Manages project creation, configuration, and operations"""
    
    def __init__(self, projects_dir: str = "projects"):
        self.projects_dir = Path(projects_dir)
        self.projects_dir.mkdir(exist_ok=True)
    
    def create_project(self, name: str, spiders: List[str], settings: Dict = None) -> bool:
        """Create a new project with configuration"""
        project_path = self.projects_dir / name
        
        if project_path.exists():
            print(f"Project '{name}' already exists!")
            return False
        
        # Create project directories
        project_path.mkdir(parents=True)
        (project_path / "outputs").mkdir()
        (project_path / "logs").mkdir()
        
        # Create config file
        config = {
            'project_name': name,
            'spiders': spiders,
            'settings': settings or {
                'download_delay': 1,
                'concurrent_requests': 4,
                'concurrent_requests_per_domain': 2
            },
            'output_format': 'json'
        }
        
        config_path = project_path / "config.yaml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, indent=2)
        
        print(f"✅ Project '{name}' created successfully!")
        print(f"📁 Location: {project_path}")
        print(f"🕷️  Spiders: {', '.join(spiders)}")
        return True
    
    def list_projects(self) -> List[str]:
        """List all existing projects"""
        projects = []
        for item in self.projects_dir.iterdir():
            if item.is_dir() and (item / "config.yaml").exists():
                projects.append(item.name)
        return sorted(projects)
    
    def get_project_config(self, name: str) -> Optional[Dict]:
        """Get project configuration"""
        config_path = self.projects_dir / name / "config.yaml"
        if not config_path.exists():
            return None
        
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    
    def project_exists(self, name: str) -> bool:
        """Check if project exists"""
        return (self.projects_dir / name).exists()
    
    def get_project_path(self, name: str) -> Path:
        """Get project directory path"""
        return self.projects_dir / name
    
    def get_project_spider_list(self, name: str) -> List[str]:
        """Get list of spiders configured for a project"""
        config = self.get_project_config(name)
        if not config:
            return []
        return config.get('spiders', [])
    
    def get_project_status(self, name: str) -> Dict:
        """Get project status information"""
        if not self.project_exists(name):
            return {'error': f"Project '{name}' not found"}
        
        project_path = self.get_project_path(name)
        config = self.get_project_config(name)
        
        # Count output files
        outputs_dir = project_path / "outputs"
        output_count = 0
        if outputs_dir.exists():
            for spider_dir in outputs_dir.iterdir():
                if spider_dir.is_dir():
                    output_count += len(list(spider_dir.glob("*.json")))
        
        # Count log files
        logs_dir = project_path / "logs"
        log_count = 0
        if logs_dir.exists():
            log_count = len(list(logs_dir.glob("*.log")))
        
        return {
            'name': name,
            'spiders': config.get('spiders', []),
            'output_files': output_count,
            'log_files': log_count,
            'settings': config.get('settings', {}),
            'path': str(project_path)
        }
    
    def delete_project(self, name: str) -> bool:
        """Delete a project (use with caution)"""
        project_path = self.get_project_path(name)
        if not project_path.exists():
            print(f"Project '{name}' not found!")
            return False
        
        import shutil
        shutil.rmtree(project_path)
        print(f"🗑️  Project '{name}' deleted!")
        return True