#!/bin/bash
# Simple parallel crawler with auto-capacity detection
# Usage:
#   ./parallel_crawl.sh brown_v2                    # All spiders in project
#   ./parallel_crawl.sh brown_v2 spider1 spider2    # Selected spiders

set -euo pipefail

# Check arguments
if [ $# -eq 0 ]; then
    echo "Usage: $0 <project> [spider1 spider2 ...]"
    echo ""
    echo "Examples:"
    echo "  $0 brown_v2                    # Run all spiders in project"
    echo "  $0 brown_v2 spider1 spider2    # Run specific spiders"
    exit 1
fi

# Check if GNU parallel is installed
if ! command -v parallel &> /dev/null; then
    echo "❌ GNU parallel is not installed"
    echo ""
    echo "Installation instructions:"
    echo ""
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "  macOS:"
        echo "    brew install parallel"
    else
        echo "  Linux (Debian/Ubuntu):"
        echo "    sudo apt-get update"
        echo "    sudo apt-get install parallel"
        echo ""
        echo "  Linux (RHEL/CentOS):"
        echo "    sudo yum install parallel"
        echo ""
        echo "  Linux (Arch):"
        echo "    sudo pacman -S parallel"
    fi
    echo ""
    exit 1
fi

PROJECT="$1"
shift

# Get spider list
if [ $# -eq 0 ]; then
    # No spiders specified - run ALL in project
    echo "📋 Getting all spiders from project: $PROJECT"
    source .venv/bin/activate
    SPIDERS=$(./scrapai spiders list --project "$PROJECT" 2>/dev/null | grep '•' | awk '{print $2}')
else
    # Spiders specified - use those
    echo "📋 Using specified spiders"
    SPIDERS="$@"
fi

# Count spiders
SPIDER_COUNT=$(echo "$SPIDERS" | wc -w)

if [ $SPIDER_COUNT -eq 0 ]; then
    echo "❌ No spiders to crawl"
    exit 1
fi

# Check for Cloudflare-enabled spiders
echo "🔍 Checking spider configurations..."
source .venv/bin/activate

CF_CHECK=$(python3 -c "
from core.db import get_db
from core.models import Spider, SpiderSetting
import sys

db = next(get_db())
spider_names = '''$SPIDERS'''.split()

cf_count = 0
for spider_name in spider_names:
    spider = db.query(Spider).filter(
        Spider.name == spider_name,
        Spider.project == '$PROJECT'
    ).first()

    if spider:
        for setting in spider.settings:
            if setting.key == 'CLOUDFLARE_ENABLED' and str(setting.value).lower() in ['true', '1']:
                cf_count += 1
                break

print(cf_count)
")

CF_COUNT=$CF_CHECK
REGULAR_COUNT=$((SPIDER_COUNT - CF_COUNT))

# Auto-detect optimal parallelism
CPU_CORES=$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)

if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    TOTAL_MEM=$(sysctl -n hw.memsize)
    AVAILABLE_MEM_MB=$((TOTAL_MEM / 1024 / 1024 * 70 / 100))  # Assume 70% available
else
    # Linux
    AVAILABLE_MEM_MB=$(free -m | awk '/^Mem:/ {print $7}')
fi

# Calculate memory per crawler based on Cloudflare usage
# Regular: 200MB, Cloudflare: 500MB
if [ $CF_COUNT -eq 0 ]; then
    # All regular spiders
    MEM_PER_SPIDER=200
    SPIDER_TYPE="regular"
elif [ $CF_COUNT -eq $SPIDER_COUNT ]; then
    # All Cloudflare spiders
    MEM_PER_SPIDER=500
    SPIDER_TYPE="Cloudflare"
else
    # Mixed - use weighted average
    MEM_PER_SPIDER=$(( (REGULAR_COUNT * 200 + CF_COUNT * 500) / SPIDER_COUNT ))
    SPIDER_TYPE="mixed (${CF_COUNT} Cloudflare + ${REGULAR_COUNT} regular)"
fi

# Calculate: (Available RAM - 2GB) / Memory per spider
MEM_PARALLEL=$(( (AVAILABLE_MEM_MB - 2048) / MEM_PER_SPIDER ))

# Use 80% of CPU cores
CPU_PARALLEL=$(( CPU_CORES * 80 / 100 ))

# Take minimum, constrain 2-20
PARALLEL=$(( MEM_PARALLEL < CPU_PARALLEL ? MEM_PARALLEL : CPU_PARALLEL ))
[ $PARALLEL -lt 2 ] && PARALLEL=2
[ $PARALLEL -gt 20 ] && PARALLEL=20

echo ""
echo "=========================================="
echo "🚀 Parallel Crawler - Configuration"
echo "=========================================="
echo "Project: $PROJECT"
echo "Spiders to crawl: $SPIDER_COUNT ($SPIDER_TYPE)"
if [ $CF_COUNT -gt 0 ]; then
    echo "  ⚠️  $CF_COUNT Cloudflare-enabled (higher memory usage)"
fi
echo ""
echo "Machine Capacity:"
echo "  • CPU cores: $CPU_CORES"
echo "  • Available RAM: ${AVAILABLE_MEM_MB}MB"
echo "  • Memory per spider: ~${MEM_PER_SPIDER}MB"
echo ""
echo "Auto-detected Settings:"
echo "  • Parallel jobs: $PARALLEL"
echo "  • Timeout per spider: 8h"
echo "  • Halt if >50% fail"
echo ""
echo "Estimated time: ~$((SPIDER_COUNT / PARALLEL)) batches"
echo "=========================================="
echo ""

# Ask for confirmation
read -p "Do you want to continue? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Cancelled"
    exit 0
fi

echo ""
echo "🚀 Starting parallel crawl..."
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKER_SCRIPT="$SCRIPT_DIR/.parallel_crawl_worker.sh"

# Create temp file with spider list
TEMP_FILE=$(mktemp)
echo "$SPIDERS" | tr ' ' '\n' > "$TEMP_FILE"

# Run parallel using worker script
echo "$SPIDERS" | tr ' ' '\n' | parallel \
    -j $PARALLEL \
    --timeout 8h \
    --halt soon,fail=50% \
    --line-buffer \
    --tagstring "[\033[1;34m{}\033[0m]" \
    "$WORKER_SCRIPT" {} "$PROJECT"

EXIT_CODE=$?

# Clean up
rm -f "$TEMP_FILE"

echo ""
echo "✅ Done"
exit $EXIT_CODE
