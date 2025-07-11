#!/usr/bin/env python3
"""
Add Site - Creates a new Scrapy spider for a website

This is the main function for adding new sites to scrapai.

Process:
1. Analyzes the website structure
2. Generates appropriate spider code (CrawlSpider or SitemapSpider)
3. Saves the spider file
4. Validates it works
"""

import os
import sys
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.analyzer import analyze_website
from core.spider_templates import generate_spider_from_analysis, SpiderGenerator
from core.sitemap import discover_site_structure

def generate_spider_for_site(base_url: str, spider_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Complete workflow to generate a spider for a given website
    
    Args:
        base_url: Website URL to create spider for
        spider_name: Optional spider name (auto-generated if not provided)
    
    Returns:
        Dict with spider generation results
    """
    
    # Generate spider name if not provided
    if not spider_name:
        domain = urlparse(base_url).netloc
        spider_name = domain.replace('.', '_').replace('-', '_').lower()
        # Remove common prefixes
        if spider_name.startswith('www_'):
            spider_name = spider_name[4:]
    
    print(f"🚀 Generating spider for {base_url}")
    print(f"📝 Spider name: {spider_name}")
    
    # Step 1: Analyze the website
    print("\n📊 Step 1: Analyzing website structure...")
    try:
        analysis = analyze_website(base_url)
        print(f"✅ Analysis complete")
        
        # Print analysis summary
        print(f"   • Sitemaps found: {len(analysis.get('sitemaps', []))}")
        print(f"   • Sample articles: {len(analysis.get('sample_articles', []))}")
        print(f"   • Has robots.txt: {analysis.get('has_robots_txt', False)}")
        
    except Exception as e:
        return {
            'success': False,
            'error': f"Site analysis failed: {str(e)}",
            'spider_name': spider_name
        }
    
    # Step 2: Generate spider code
    print("\n🔧 Step 2: Generating spider code...")
    try:
        spider_code = generate_spider_from_analysis(spider_name, base_url, analysis)
        print("✅ Spider code generated")
        
    except Exception as e:
        return {
            'success': False,
            'error': f"Spider generation failed: {str(e)}",
            'spider_name': spider_name,
            'analysis': analysis
        }
    
    # Step 3: Save spider file
    print("\n💾 Step 3: Saving spider file...")
    try:
        generator = SpiderGenerator(spider_name, base_url)
        spider_path = generator.save_spider(spider_code)
        print(f"✅ Spider saved to: {spider_path}")
        
    except Exception as e:
        return {
            'success': False,
            'error': f"Spider save failed: {str(e)}",
            'spider_name': spider_name,
            'analysis': analysis,
            'spider_code': spider_code
        }
    
    # Step 4: Validate spider
    print("\n🧪 Step 4: Validating spider...")
    try:
        validation_result = validate_spider(spider_name, spider_path)
        print(f"✅ Spider validation: {validation_result['status']}")
        
    except Exception as e:
        print(f"⚠️  Spider validation failed: {str(e)}")
        validation_result = {'status': 'warning', 'message': str(e)}
    
    return {
        'success': True,
        'spider_name': spider_name,
        'spider_path': spider_path,
        'analysis': analysis,
        'validation': validation_result,
        'usage': {
            'test': f"./scrapai_cli test {spider_name}",
            'crawl': f"./scrapai_cli crawl {spider_name}",
            'crawl_with_output': f"./scrapai_cli crawl {spider_name} --output {spider_name}_articles.json"
        }
    }

def validate_spider(spider_name: str, spider_path: str) -> Dict[str, Any]:
    """
    Validate that the generated spider is syntactically correct
    """
    try:
        # Check if file exists
        if not os.path.exists(spider_path):
            return {'status': 'error', 'message': 'Spider file not found'}
        
        # Try to compile the spider code
        with open(spider_path, 'r') as f:
            spider_code = f.read()
        
        # Compile to check for syntax errors
        compile(spider_code, spider_path, 'exec')
        
        # Check if spider can be imported (basic validation)
        spider_dir = os.path.dirname(spider_path)
        spider_module = os.path.basename(spider_path)[:-3]  # Remove .py
        
        # Try importing (this is a basic check)
        import importlib.util
        spec = importlib.util.spec_from_file_location(spider_module, spider_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            return {'status': 'success', 'message': 'Spider validation passed'}
        else:
            return {'status': 'warning', 'message': 'Could not import spider module'}
            
    except SyntaxError as e:
        return {'status': 'error', 'message': f'Syntax error: {str(e)}'}
    except Exception as e:
        return {'status': 'warning', 'message': f'Validation warning: {str(e)}'}

def add_website_interactively():
    """
    Interactive function for adding websites
    This is what Claude Code calls when you ask to add a site
    """
    print("🤖 Claude Code Spider Generation")
    print("=" * 40)
    
    # Get URL from user (in real usage, this would come from the request)
    base_url = input("Enter website URL: ").strip()
    
    if not base_url:
        print("❌ No URL provided")
        return
    
    # Ensure URL has protocol
    if not base_url.startswith(('http://', 'https://')):
        base_url = 'https://' + base_url
    
    # Ask for spider name (optional)
    spider_name = input("Enter spider name (or press Enter for auto-generated): ").strip()
    
    # Generate spider
    result = generate_spider_for_site(base_url, spider_name if spider_name else None)
    
    # Display results
    print("\n" + "=" * 40)
    if result['success']:
        print("🎉 Spider generation successful!")
        print(f"📂 Spider saved: {result['spider_path']}")
        print(f"🕷️  Spider name: {result['spider_name']}")
        print("\n📋 Usage:")
        for command_name, command in result['usage'].items():
            print(f"   {command}")
        
        # Show analysis summary
        analysis = result['analysis']
        print(f"\n📊 Site Analysis Summary:")
        print(f"   • Strategy: {'Sitemap-based' if analysis.get('sitemaps') else 'Link-following'}")
        print(f"   • Sample articles found: {len(analysis.get('sample_articles', []))}")
        
        if analysis.get('sitemaps'):
            print(f"   • Sitemaps: {len(analysis['sitemaps'])}")
            for sitemap in analysis['sitemaps']:
                print(f"     - {sitemap}")
        
    else:
        print("❌ Spider generation failed!")
        print(f"Error: {result['error']}")

if __name__ == "__main__":
    add_website_interactively()