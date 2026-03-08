#!/bin/bash
# crawl-new.sh — Run spiders using GNU parallel, skip already-crawled ones.
# Usage: ./crawl-new.sh <project> [jobs]
#   project: project name (e.g. world_news_1)
#   jobs: number of parallel crawls (default: 5)

set -uo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: ./crawl-new.sh <project> [jobs]"
    exit 1
fi

PROJECT="$1"
DATA_DIR="${DATA_DIR:-./data}"
JOBS="${2:-5}"

run_spider() {
    local spider="$1"
    local project="$2"
    local data_dir="$3"
    local crawl_dir="$data_dir/$project/$spider/crawls"

    # Check if any jsonl files exist
    local existing
    existing=$(ls "$crawl_dir"/crawl_*.jsonl 2>/dev/null || true)

    if [ -n "$existing" ]; then
        local total_lines=0
        for f in $existing; do
            total_lines=$((total_lines + $(wc -l < "$f")))
        done

        if [ "$total_lines" -ge 100 ]; then
            echo "⏭  SKIP $spider (already crawled: $total_lines lines)"
            return 0
        else
            echo "🔄 RERUN $spider (only $total_lines lines — resetting deltafetch)"
            ./scrapai crawl "$spider" --project "$project" --timeout 28800 --reset-deltafetch
            echo "✅ DONE $spider"
            return 0
        fi
    fi

    echo "🚀 START $spider"
    ./scrapai crawl "$spider" --project "$project" --timeout 28800
    echo "✅ DONE $spider"
}

export -f run_spider

spiders=$(./scrapai db query \
    "SELECT name FROM spiders WHERE project = '$PROJECT' AND active = true ORDER BY name" \
    --format csv | tail -n +2)

total=$(echo "$spiders" | wc -l)
echo "Found $total spiders | $JOBS parallel jobs | project: $PROJECT"
echo ""

echo "$spiders" | parallel -j "$JOBS" --line-buffer run_spider {} "$PROJECT" "$DATA_DIR"

echo ""
echo "All done."
