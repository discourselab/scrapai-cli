#!/bin/bash
# crawl-stats.sh — Show crawl jsonl file count and line counts for a project.
# Usage: ./crawl-stats.sh [project]
#   project: project name (default: world_news)

PROJECT="${1:-world_news}"
DATA_DIR="${DATA_DIR:-./data}"

files=$(find "$DATA_DIR/$PROJECT" -name "crawl_*.jsonl" | sort)
total=$(echo "$files" | grep -c . || true)

if [ "$total" -eq 0 ]; then
    echo "No crawl jsonl files found for project: $PROJECT"
    exit 0
fi

echo "Project: $PROJECT | Files: $total"
echo ""
printf "%-50s %10s\n" "Spider" "Lines"
printf "%-50s %10s\n" "------" "-----"

total_lines=0
while IFS= read -r f; do
    spider=$(echo "$f" | sed "s|$DATA_DIR/$PROJECT/||" | sed 's|/crawls/.*||')
    lines=$(wc -l < "$f")
    total_lines=$((total_lines + lines))
    printf "%-50s %10d\n" "$spider" "$lines"
done <<< "$files"

echo ""
printf "%-50s %10d\n" "TOTAL" "$total_lines"
