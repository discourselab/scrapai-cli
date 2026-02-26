"""
ScrapAI Spider DAG Generator

This file dynamically generates Airflow DAGs from spiders in the ScrapAI database.
Each spider becomes a separate DAG that can be scheduled and monitored in Airflow.

Features:
- Auto-generates DAGs from spider database
- Project-based tagging and access control
- Configurable schedules per spider
- Integration with existing ./scrapai crawl commands
- Optional S3 upload (if S3 credentials are set)
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

# Add scrapai to Python path so we can import from core
SCRAPAI_PATH = Path(os.getenv('SCRAPAI_CLI_PATH', '/opt/scrapai'))
sys.path.insert(0, str(SCRAPAI_PATH))

try:
    from core.db import SessionLocal
    from core.models import Spider
except ImportError as e:
    print(f"Warning: Could not import ScrapAI modules: {e}")
    print(f"Make sure SCRAPAI_CLI_PATH is set correctly: {SCRAPAI_PATH}")
    # Create empty globals so Airflow doesn't error on import
    sys.exit(0)

# Check if S3 credentials are configured
S3_ENABLED = all([
    os.getenv('S3_ACCESS_KEY'),
    os.getenv('S3_SECRET_KEY'),
    os.getenv('S3_ENDPOINT'),
    os.getenv('S3_BUCKET'),
])

print(f"S3 Upload: {'ENABLED' if S3_ENABLED else 'DISABLED (credentials not found)'}")


# Default DAG arguments
DEFAULT_DAG_ARGS = {
    'owner': 'scrapai',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
    'start_date': days_ago(1),
}


def upload_to_s3(spider_name: str, **context):
    """
    Upload the latest crawl output to S3-compatible storage (gzip compressed)

    Args:
        spider_name: Name of the spider
        context: Airflow context
    """
    import boto3
    import gzip
    import shutil
    from glob import glob

    # Get S3 credentials from environment
    s3_access_key = os.getenv('S3_ACCESS_KEY')
    s3_secret_key = os.getenv('S3_SECRET_KEY')
    s3_endpoint = os.getenv('S3_ENDPOINT')
    s3_bucket = os.getenv('S3_BUCKET')

    # Find the latest crawl file (search recursively for date-organized folders)
    data_dir = SCRAPAI_PATH / 'data' / spider_name
    crawl_files = sorted(glob(str(data_dir / '**' / 'crawl_*.jsonl'), recursive=True), reverse=True)

    if not crawl_files:
        print(f"⚠️  No crawl files found for {spider_name}")
        return

    latest_file = crawl_files[0]
    latest_path = Path(latest_file)

    # Get original file size
    original_size_mb = latest_path.stat().st_size / (1024 * 1024)
    print(f"📄 Original file: {latest_path.name} ({original_size_mb:.2f} MB)")

    # Compress to .jsonl.gz
    gz_path = Path(str(latest_path) + '.gz')
    print(f"🗜️  Compressing to gzip...")

    with open(latest_path, 'rb') as f_in:
        with gzip.open(gz_path, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)

    compressed_size_mb = gz_path.stat().st_size / (1024 * 1024)
    compression_ratio = (1 - compressed_size_mb / original_size_mb) * 100
    print(f"✅ Compressed: {compressed_size_mb:.2f} MB (saved {compression_ratio:.1f}%)")

    # Preserve folder structure: spider_name/date/filename.gz
    relative_path = gz_path.relative_to(SCRAPAI_PATH / 'data')
    s3_key = str(relative_path)

    print(f"📤 Uploading {relative_path} to S3...")

    try:
        # Initialize S3 client
        s3_client = boto3.client(
            's3',
            endpoint_url=s3_endpoint,
            aws_access_key_id=s3_access_key,
            aws_secret_access_key=s3_secret_key,
        )

        # Upload compressed file
        s3_client.upload_file(str(gz_path), s3_bucket, s3_key)

        print(f"✅ Uploaded to s3://{s3_bucket}/{s3_key}")

        # Clean up local files after successful upload
        gz_path.unlink()
        latest_path.unlink()
        print(f"🧹 Cleaned up local files (original + compressed)")

    except Exception as e:
        # Keep files locally if upload fails
        print(f"❌ Upload failed: {e}")
        print(f"📁 Keeping local files for retry: {latest_path}")
        # Clean up .gz file since upload failed
        if gz_path.exists():
            gz_path.unlink()
        raise  # Re-raise to mark task as failed in Airflow


def get_spiders_from_db():
    """Fetch all spiders from ScrapAI database"""
    try:
        session = SessionLocal()
        spiders = session.query(Spider).all()
        session.close()
        return spiders
    except Exception as e:
        print(f"Error fetching spiders from database: {e}")
        return []


def create_spider_dag(spider):
    """
    Create an Airflow DAG for a spider

    Args:
        spider: Spider model instance from database

    Returns:
        DAG object
    """
    # Determine project (default to 'default' if not set)
    project = getattr(spider, 'project', 'default') or 'default'

    # Create unique DAG ID
    dag_id = f"{project}_{spider.name}"

    # Tags for filtering and organization
    tags = [
        'scrapai',
        f'project:{project}',
        'spider',
    ]

    # Parse schedule (default to None for manual triggering)
    # You can add a 'schedule' field to your Spider model
    schedule_interval = getattr(spider, 'schedule_interval', None)

    # Create DAG
    dag = DAG(
        dag_id=dag_id,
        default_args=DEFAULT_DAG_ARGS,
        description=f'ScrapAI spider: {spider.name} (Project: {project})',
        schedule_interval=schedule_interval,
        tags=tags,
        catchup=False,
        max_active_runs=1,  # Prevent concurrent runs of same spider

        # Project-based access control
        # Note: You need to create these roles in Airflow UI first
        # access_control={
        #     f'{project}_admin': {'can_read', 'can_edit', 'can_delete'},
        #     f'{project}_user': {'can_read', 'can_edit'},
        # },
    )

    with dag:
        # Task to run the spider crawl
        crawl_task = BashOperator(
            task_id='crawl_spider',
            bash_command=f"""
            cd {SCRAPAI_PATH} && \
            source .venv/bin/activate && \
            ./scrapai crawl {spider.name} --timeout 28800
            """,
            # Graceful stop at 8h (28800s), hard kill at 9h as fallback
            execution_timeout=timedelta(hours=9),
        )

        # Optional: Add a task to verify crawl results
        verify_task = BashOperator(
            task_id='verify_results',
            bash_command=f"""
            cd {SCRAPAI_PATH} && \
            source .venv/bin/activate && \
            ./scrapai show {spider.name} --limit 5
            """,
            execution_timeout=timedelta(minutes=5),
        )

        # Task dependencies
        crawl_task >> verify_task

        # Conditionally add S3 upload task if credentials are configured
        if S3_ENABLED:
            upload_task = PythonOperator(
                task_id='upload_to_s3',
                python_callable=upload_to_s3,
                op_kwargs={'spider_name': spider.name},
                execution_timeout=timedelta(minutes=30),
            )
            verify_task >> upload_task

    return dag


# Filter DAGs by project (set to None to show all projects)
# Options: None (all), or comma-separated project names like 'project1,project2'
AIRFLOW_PROJECT_FILTER = os.getenv('AIRFLOW_PROJECT_FILTER', None)


# Generate DAGs for all spiders
def generate_dags():
    """Generate all DAGs from database spiders"""
    spiders = get_spiders_from_db()

    # Apply project filter
    if AIRFLOW_PROJECT_FILTER:
        if isinstance(AIRFLOW_PROJECT_FILTER, str):
            allowed_projects = [p.strip() for p in AIRFLOW_PROJECT_FILTER.split(',')]
        else:
            allowed_projects = AIRFLOW_PROJECT_FILTER

        spiders = [s for s in spiders if getattr(s, 'project', 'default') in allowed_projects]
        print(f"Project filter: {allowed_projects}")

    print(f"Generating DAGs for {len(spiders)} spiders...")

    dags = {}
    for spider in spiders:
        try:
            dag = create_spider_dag(spider)
            dags[dag.dag_id] = dag
            print(f"  ✓ Generated DAG: {dag.dag_id}")
        except Exception as e:
            print(f"  ✗ Error generating DAG for spider '{spider.name}': {e}")

    return dags


# Generate all DAGs and add to globals so Airflow can discover them
all_dags = generate_dags()
globals().update(all_dags)

print(f"\nTotal DAGs generated: {len(all_dags)}")
