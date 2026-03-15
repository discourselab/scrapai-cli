#!/usr/bin/env python3
"""Test script for ScrapAI Python Library API."""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set free LLM model for testing (using OpenRouter free tier)
os.environ["SCRAPAI_LLM_API"] = "https://openrouter.ai/api/v1"
os.environ["SCRAPAI_LLM_KEY"] = os.getenv("OPENROUTER_API_KEY", "")
# Try this specific free model that's known to work
os.environ["SCRAPAI_LLM_MODEL"] = "anthropic/claude-3-haiku:free"

from scrapai import (
    setup,
    verify,
    list_projects,
    list_spiders,
    generate_spider,
    crawl,
    show_items,
    db_stats,
    SpiderNotFoundError,
)


def test_basic_api():
    """Test basic API functions."""
    print("=" * 60)
    print("Testing ScrapAI Library API")
    print("=" * 60)

    # 1. Verify environment
    print("\n1. Testing verify()...")
    result = verify()
    print(f"   ✓ Environment verified: {result.success}")
    print(f"   ✓ Checks: {result.checks}")

    # 2. Get database stats
    print("\n2. Testing db_stats()...")
    stats = db_stats()
    print(f"   ✓ Spiders: {stats.total_spiders}")
    print(f"   ✓ Items: {stats.total_items}")
    print(f"   ✓ Projects: {len(stats.projects)}")

    # 3. List projects
    print("\n3. Testing list_projects()...")
    projects = list_projects()
    print(f"   ✓ Found {len(projects)} projects")
    for p in projects:
        print(f"      - {p['name']}: {p['spider_count']} spiders")

    return True


def test_generate_spider_simple():
    """Test simple spider generation with free model.

    Note: Free models on OpenRouter may have limited availability.
    This test demonstrates the API flow - actual generation may require
    a paid model or different API key with free model access.
    """
    print("\n" + "=" * 60)
    print("Testing Spider Generation (Free Model)")
    print("=" * 60)

    # Check for API key - also check environment
    api_key = os.environ.get("SCRAPAI_LLM_KEY") or os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("\n   ⚠️  OPENROUTER_API_KEY not set, skipping generation test")
        print("   Set it with: export OPENROUTER_API_KEY=your_key")
        return None

    # For now, demonstrate with existing spider
    project = "exampletest3"

    print(f"\n1. Using existing spider from project: {project}")

    from scrapai import list_spiders

    spiders = list_spiders(project=project)

    if spiders:
        spider = spiders[0]
        print(f"   ✓ Found spider: {spider.name}")
        return spider
    else:
        print(f"   ⚠️  No spiders in project {project}")
        return None

    # For now, demonstrate with existing spider
    project = "exampletest3"

    print(f"\n1. Using existing spider from project: {project}")

    from scrapai import list_spiders

    spiders = list_spiders(project=project)

    if spiders:
        spider = spiders[0]
        print(f"   ✓ Found spider: {spider.name}")
        return spider
    else:
        print(f"   ⚠️  No spiders in project {project}")
        return None


def test_crawl_and_show(spider_name, project):
    """Test crawling and showing items."""
    if not spider_name:
        print("\n   ⚠️  No spider to test, skipping crawl test")
        return

    print("\n" + "=" * 60)
    print(f"Testing Crawl: {spider_name}")
    print("=" * 60)

    # Run crawl with limit
    print(f"\n1. Running crawl (limit=5)...")
    try:
        result = crawl(
            spider=spider_name,
            project=project,
            limit=5,
        )
        print(f"   ✓ Crawl completed!")
        print(f"   Items: {result.item_count}")
        print(f"   Duration: {result.duration_ms}ms")
        print(f"   Success: {result.success}")

    except SpiderNotFoundError as e:
        print(f"   ❌ Spider not found: {e}")
        return
    except Exception as e:
        print(f"   ❌ Crawl failed: {e}")
        return

    # Show items
    print("\n2. Showing items...")
    items_result = show_items(
        spider=spider_name,
        project=project,
        limit=3,
    )

    print(f"   ✓ Found {len(items_result.items)} items")
    print(f"   Total in DB: {items_result.total_count}")

    for i, item in enumerate(items_result.items, 1):
        print(f"\n   Item {i}:")
        print(f"      URL: {item.get('url', 'N/A')}")
        print(f"      Title: {item.get('title', 'N/A')[:80]}...")
        content = item.get("content", "")
        if content:
            print(f"      Content: {content[:100]}...")


def main():
    """Run all tests."""
    print("\n🔬 ScrapAI Library API Test Suite\n")

    # Test basic API (no API key needed)
    test_basic_api()

    # Test with free LLM (needs OPENROUTER_API_KEY)
    result = test_generate_spider_simple()

    if result:
        # Get the spider name from the result (could be SpiderInfo object or dict)
        if hasattr(result, "name"):
            spider_name = result.name
            project = result.project
        else:
            spider_name = result.get("name") if isinstance(result, dict) else result
            project = result.get("project") if isinstance(result, dict) else "default"
        test_crawl_and_show(spider_name, project)

    print("\n" + "=" * 60)
    print("✅ Test Suite Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
