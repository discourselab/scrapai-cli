#!/bin/bash
# crawl-new.sh — Run spiders using GNU parallel, skip any with existing crawl files.
# Usage: ./crawl-new.sh <project> [jobs] [--reset-deltafetch]
#   project: project name (e.g. world_news_1)
#   jobs: number of parallel crawls (default: 5)
#   --reset-deltafetch: add --reset-deltafetch when a spider IS run (fresh starts only).
#
# Skip rule: any crawl_*.jsonl in the spider's crawls/ dir → skip.

set -uo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: ./crawl-new.sh <project> [jobs] [--reset-deltafetch]"
    exit 1
fi

PROJECT="$1"
DATA_DIR="${DATA_DIR:-./data}"
JOBS=5
RESET_DELTAFETCH=0

shift
while [ $# -gt 0 ]; do
    case "$1" in
        --reset-deltafetch)
            RESET_DELTAFETCH=1
            ;;
        *)
            JOBS="$1"
            ;;
    esac
    shift
done

run_spider() {
    local spider="$1"
    local project="$2"
    local data_dir="$3"
    local reset_deltafetch="$4"
    local crawl_dir="$data_dir/$project/$spider/crawls"

    local reset_arg=""
    if [ "$reset_deltafetch" = "1" ]; then
        reset_arg="--reset-deltafetch"
    fi

    # Skip if any crawl files already exist
    if ls "$crawl_dir"/crawl_*.jsonl >/dev/null 2>&1; then
        echo "⏭  SKIP $spider (crawl files already exist)"
        return 0
    fi

    echo "🚀 START $spider${reset_arg:+ (with $reset_arg)}"
    ./scrapai crawl "$spider" --project "$project" --timeout 28800 $reset_arg
    echo "✅ DONE $spider"
}

export -f run_spider

spiders=$(./scrapai db query \
    "SELECT name FROM spiders WHERE project = '$PROJECT' AND active = true ORDER BY name" \
    --format csv | tail -n +2)

total=$(echo "$spiders" | wc -l)
echo "Found $total spiders | $JOBS parallel jobs | project: $PROJECT | reset-deltafetch: $RESET_DELTAFETCH"
echo ""

echo "$spiders" | parallel -j "$JOBS" --line-buffer run_spider {} "$PROJECT" "$DATA_DIR" "$RESET_DELTAFETCH"

echo ""
echo "All done."
