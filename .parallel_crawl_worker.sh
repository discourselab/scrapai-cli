#!/bin/bash
# Worker script for parallel_crawl.sh

SPIDER_NAME=$1
PROJECT=$2

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

# Activate venv
source .venv/bin/activate

# Run crawl
echo "🚀 Starting crawl..."
./scrapai crawl "$SPIDER_NAME" --project "$PROJECT"

exit_code=$?

if [ $exit_code -eq 0 ]; then
    echo "✅ Completed successfully"
else
    echo "❌ Failed"
fi

exit $exit_code
