#!/bin/bash
# Quick requirements checker for scrapai-cli setup

echo "=== Checking Requirements ==="
echo ""

# Python
echo -n "Python 3.12+: "
python3 --version 2>/dev/null && echo "✅" || echo "❌ Install Python 3.12+"

# Virtual env
echo -n "Virtual env: "
[ -d ".venv" ] && echo "✅" || echo "⚠️  Run ./scrapai setup"

# PostgreSQL
echo -n "PostgreSQL: "
which psql >/dev/null 2>&1 && echo "✅" || echo "⚠️  Optional (can use remote DB)"

# Chrome/Playwright
echo -n "Chrome/Chromium: "
# Check for Playwright browsers first (preferred)
if [ -d ".venv" ]; then
    PLAYWRIGHT_CHECK=$(source .venv/bin/activate 2>/dev/null && python3 -c "
try:
    from playwright.sync_api import sync_playwright
    p = sync_playwright().start()
    path = p.chromium.executable_path
    p.stop()
    print(path)
except:
    print('')
" 2>/dev/null)

    if [ -n "$PLAYWRIGHT_CHECK" ] && [ -f "$PLAYWRIGHT_CHECK" ]; then
        echo "✅ (Playwright)"
    elif which chromium >/dev/null 2>&1; then
        echo "✅ (System)"
    elif which google-chrome >/dev/null 2>&1; then
        echo "✅ (System)"
    else
        echo "❌ Install: playwright install chromium"
    fi
else
    # No venv, check system browsers only
    which chromium >/dev/null 2>&1 && echo "✅ (System)" || which google-chrome >/dev/null 2>&1 && echo "✅ (System)" || echo "❌ Install chromium or playwright"
fi

# xvfb (for headless)
echo -n "xvfb: "
which xvfb-run >/dev/null 2>&1 && echo "✅" || echo "⚠️  Install for headless servers"

# Display
echo -n "Display: "
[ -n "$DISPLAY" ] && echo "✅ $DISPLAY" || echo "⚠️  Headless (needs xvfb for CF bypass)"

echo ""
echo "=== Cloudflare Bypass Detection ==="
if [ -d ".venv" ]; then
    source .venv/bin/activate 2>/dev/null
    python3 << 'PYEOF'
import sys
import os
sys.path.insert(0, os.getcwd())

try:
    from utils.display_helper import has_display, needs_xvfb, has_xvfb
    print(f"Has display: {'✅ Yes' if has_display() else '❌ No'}")
    print(f"Needs xvfb: {'✅ Yes' if needs_xvfb() else '❌ No'}")
    print(f"Has xvfb: {'✅ Yes' if has_xvfb() else '❌ No'}")

    if needs_xvfb() and not has_xvfb():
        print("\n⚠️  WARNING: Cloudflare bypass won't work without xvfb or display")
        print("   Install xvfb: sudo apt-get install xvfb")
    elif needs_xvfb() and has_xvfb():
        print("\n✅ Cloudflare bypass ready (will use xvfb)")
    else:
        print("\n✅ Cloudflare bypass ready (will use native browser)")
except ImportError:
    print("⚠️  Run ./scrapai setup first")
PYEOF
else
    echo "⚠️  Run ./scrapai setup first"
fi

echo ""
echo "=== Quick Setup ==="
echo "1. ./scrapai setup"
echo "2. source .venv/bin/activate"
echo "3. Create .env with DATABASE_URL"
echo "4. ./scrapai crawl <spider_name>"
