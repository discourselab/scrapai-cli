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

# Chrome
echo -n "Chrome/Chromium: "
which chromium >/dev/null 2>&1 && echo "✅" || which google-chrome >/dev/null 2>&1 && echo "✅" || echo "❌ Install chromium"

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
