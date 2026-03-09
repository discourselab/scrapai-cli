#!/bin/bash
# crawl-stats.sh — Show crawl jsonl file count and line counts for a project.
# Usage: ./crawl-stats.sh [project] [s3_project]
#   project:    local project name (default: world_news)
#   s3_project: S3 folder to count uploaded spiders (default: world_news_premium)

PROJECT="${1:-world_news}"
S3_PROJECT="${2:-world_news_premium}"
DATA_DIR="${DATA_DIR:-./data}"

# Load .env for S3 credentials
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

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

# S3 uploaded folders count
echo ""
echo "S3 Uploaded: $S3_PROJECT"
echo ""
if [ -z "$S3_ACCESS_KEY" ] || [ -z "$S3_SECRET_KEY" ] || [ -z "$S3_ENDPOINT" ] || [ -z "$S3_BUCKET" ]; then
    echo "  S3 credentials not configured (set S3_* vars in .env)"
else
    source .venv/bin/activate 2>/dev/null
    python3 - <<PYEOF
import boto3, sys
from botocore.client import Config

s3 = boto3.client(
    "s3",
    endpoint_url="$S3_ENDPOINT",
    aws_access_key_id="$S3_ACCESS_KEY",
    aws_secret_access_key="$S3_SECRET_KEY",
    config=Config(signature_version="s3v4"),
)
prefix = "$S3_PROJECT/"
paginator = s3.get_paginator("list_objects_v2")
folders = set()
total_files = 0
for page in paginator.paginate(Bucket="$S3_BUCKET", Prefix=prefix, Delimiter="/"):
    for cp in page.get("CommonPrefixes", []):
        folders.add(cp["Prefix"])
    # Also count without delimiter to get file totals
# Re-paginate without delimiter to count all files
for page in paginator.paginate(Bucket="$S3_BUCKET", Prefix=prefix):
    total_files += page.get("KeyCount", 0)
print(f"  Folders (spiders): {len(folders)}")
print(f"  Total files:       {total_files}")
PYEOF
fi
