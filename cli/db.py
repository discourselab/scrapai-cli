import click
import subprocess
import sys
import os


def is_postgresql():
    """Check if database is PostgreSQL"""
    from core.db import engine

    return "postgresql" in str(engine.url)


def is_sqlite():
    """Check if database is SQLite"""
    from core.db import engine

    return "sqlite" in str(engine.url)


@click.group()
def db():
    """Database management"""
    pass


@db.command("migrate")
def migrate():
    """Run database migrations"""
    click.echo("🔄 Running database migrations...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        if result.returncode == 0:
            click.echo("✅ Migrations completed successfully!")
        else:
            click.echo("❌ Migration failed!")
    except Exception as e:
        click.echo(f"❌ Error running migrations: {e}")


@db.command("current")
def current():
    """Show current migration revision"""
    try:
        subprocess.run(
            [sys.executable, "-m", "alembic", "current"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
    except Exception as e:
        click.echo(f"❌ Error checking current revision: {e}")


@db.command("stats")
def stats():
    """Show database statistics (counts of spiders, items, queue)"""
    from core.db import get_db

    try:
        db = next(get_db())

        # Get counts
        spider_count = db.execute("SELECT COUNT(*) FROM spiders").scalar()
        item_count = db.execute("SELECT COUNT(*) FROM scraped_items").scalar()
        project_count = db.execute(
            "SELECT COUNT(DISTINCT project) FROM spiders WHERE project IS NOT NULL"
        ).scalar()

        # Queue breakdown
        queue_total = db.execute("SELECT COUNT(*) FROM crawl_queue").scalar()
        queue_pending = db.execute(
            "SELECT COUNT(*) FROM crawl_queue WHERE status = 'pending'"
        ).scalar()
        queue_processing = db.execute(
            "SELECT COUNT(*) FROM crawl_queue WHERE status = 'processing'"
        ).scalar()
        queue_completed = db.execute(
            "SELECT COUNT(*) FROM crawl_queue WHERE status = 'completed'"
        ).scalar()
        queue_failed = db.execute(
            "SELECT COUNT(*) FROM crawl_queue WHERE status = 'failed'"
        ).scalar()

        click.echo("📊 Database Statistics\n")
        click.echo(f"   Spiders: {spider_count:,}")
        click.echo(f"   Scraped Items: {item_count:,}")
        click.echo(f"   Projects: {project_count:,}")
        click.echo(f"\n   Queue Items: {queue_total:,}")
        if queue_total > 0:
            click.echo(f"      • Pending: {queue_pending:,}")
            click.echo(f"      • Processing: {queue_processing:,}")
            click.echo(f"      • Completed: {queue_completed:,}")
            click.echo(f"      • Failed: {queue_failed:,}")

    except Exception as e:
        click.echo(f"❌ Failed to get statistics: {e}")


@db.command("tables")
def tables():
    """List all tables with row counts"""
    from core.db import get_db

    try:
        db = next(get_db())

        # Get table names (works for both SQLite and PostgreSQL)
        if is_postgresql():
            result = db.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
        else:  # SQLite
            result = db.execute("""
                SELECT name as table_name
                FROM sqlite_master
                WHERE type='table'
                ORDER BY name
            """)

        table_names = [row[0] for row in result]

        if not table_names:
            click.echo("(no tables found)")
            return

        click.echo("📋 Database Tables\n")

        # Get row count for each table
        max_name_len = max(len(name) for name in table_names)

        for table_name in table_names:
            try:
                count = db.execute(f"SELECT COUNT(*) FROM {table_name}").scalar()
                click.echo(f"   {table_name.ljust(max_name_len)}  {count:,} rows")
            except Exception as e:
                click.echo(f"   {table_name.ljust(max_name_len)}  (error: {e})")

    except Exception as e:
        click.echo(f"❌ Failed to list tables: {e}")


@db.command("inspect")
@click.argument("table")
def inspect(table):
    """Show schema for a specific table

    Example: ./scrapai db inspect spiders
    """
    from core.db import get_db

    try:
        db = next(get_db())

        click.echo(f"🔍 Table: {table}\n")

        # Get schema (works for both SQLite and PostgreSQL)
        if is_postgresql():
            result = db.execute(f"""
                SELECT
                    column_name,
                    data_type,
                    character_maximum_length,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_name = '{table}'
                ORDER BY ordinal_position
            """)

            click.echo("Column                Type                 Nullable  Default")
            click.echo("-" * 70)

            for row in result:
                col_name = row[0]
                data_type = row[1]
                max_len = row[2]
                nullable = row[3]
                default = row[4]

                if max_len:
                    type_str = f"{data_type}({max_len})"
                else:
                    type_str = data_type

                null_str = "YES" if nullable == "YES" else "NO"
                default_str = str(default) if default else ""

                click.echo(f"{col_name:20}  {type_str:18}  {null_str:8}  {default_str}")

        else:  # SQLite
            result = db.execute(f"PRAGMA table_info({table})")

            click.echo("Column                Type                 Nullable  Default")
            click.echo("-" * 70)

            for row in result:
                col_name = row[1]
                data_type = row[2]
                not_null = row[3]
                default = row[4]

                null_str = "NO" if not_null else "YES"
                default_str = str(default) if default else ""

                click.echo(
                    f"{col_name:20}  {data_type:18}  {null_str:8}  {default_str}"
                )

        # Show row count
        count = db.execute(f"SELECT COUNT(*) FROM {table}").scalar()
        click.echo(f"\nTotal rows: {count:,}")

    except Exception as e:
        click.echo(f"❌ Failed to inspect table '{table}': {e}")


@db.command("query")
@click.argument("sql")
@click.option(
    "--format",
    type=click.Choice(["table", "json", "csv"]),
    default="table",
    help="Output format",
)
def query(sql, format):
    """Execute a read-only SQL query against the database.

    Only SELECT queries are allowed for safety.

    Examples:
      ./scrapai db query "SELECT * FROM spiders LIMIT 5"
      ./scrapai db query "SELECT COUNT(*) FROM scraped_items" --format json
    """
    from core.db import get_db
    import json as json_lib

    # Safety check - only allow SELECT queries
    sql_upper = sql.strip().upper()
    if not sql_upper.startswith("SELECT"):
        click.echo("❌ Only SELECT queries are allowed")
        click.echo("   This is a read-only query command for safety")
        return

    try:
        db = next(get_db())
        result = db.execute(sql)
        rows = result.fetchall()

        if not rows:
            click.echo("(no results)")
            return

        if format == "json":
            # Convert to list of dicts
            columns = result.keys()
            output = [dict(zip(columns, row)) for row in rows]
            click.echo(json_lib.dumps(output, indent=2, default=str))

        elif format == "csv":
            # CSV output
            columns = result.keys()
            click.echo(",".join(columns))
            for row in rows:
                click.echo(",".join(str(v) for v in row))

        else:  # table format (default)
            # Simple table output
            columns = result.keys()

            # Calculate column widths
            col_widths = [len(str(col)) for col in columns]
            for row in rows:
                for i, val in enumerate(row):
                    col_widths[i] = max(col_widths[i], len(str(val)))

            # Print header
            header = " | ".join(
                str(col).ljust(width) for col, width in zip(columns, col_widths)
            )
            click.echo(header)
            click.echo("-" * len(header))

            # Print rows
            for row in rows:
                click.echo(
                    " | ".join(
                        str(val).ljust(width) for val, width in zip(row, col_widths)
                    )
                )

            click.echo(f"\n({len(rows)} rows)")

    except Exception as e:
        click.echo(f"❌ Query failed: {e}")


@db.command("transfer")
@click.argument("source_url")
@click.option(
    "--skip-items",
    is_flag=True,
    help="Skip scraped_items (transfer only spiders and queue)",
)
def transfer(source_url, skip_items):
    """Transfer data from another database into the current one.

    First update DATABASE_URL in .env to your new database, then run:

    \b
      ./scrapai db transfer sqlite:///scrapai.db
      ./scrapai db transfer postgresql://old-host/dbname

    SOURCE_URL is the old database to copy FROM. Data is written to
    whatever DATABASE_URL is currently set in .env.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from core.db import SessionLocal, Base, DATABASE_URL
    from core.models import Spider, SpiderRule, SpiderSetting, ScrapedItem, CrawlQueue

    if source_url == DATABASE_URL:
        click.echo("❌ Source is the same as current database.")
        click.echo("   Update DATABASE_URL in .env to your new database first.")
        return

    click.echo(f"📦 Source (old): {source_url}")
    click.echo(f"📦 Target (current): {DATABASE_URL}")

    # Connect to source
    source_engine = create_engine(source_url)
    SourceSession = sessionmaker(bind=source_engine)

    # Ensure target tables exist
    Base.metadata.create_all(bind=SessionLocal().get_bind())

    source = SourceSession()
    target = SessionLocal()

    try:
        # Transfer spiders with rules and settings
        spiders = source.query(Spider).all()
        click.echo(f"\n🕷️  Transferring {len(spiders)} spiders...")

        spider_id_map = {}
        for s in spiders:
            new_spider = Spider(
                name=s.name,
                allowed_domains=s.allowed_domains,
                start_urls=s.start_urls,
                source_url=s.source_url,
                active=s.active,
                project=s.project,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            target.add(new_spider)
            target.flush()
            spider_id_map[s.id] = new_spider.id

            for r in s.rules:
                target.add(
                    SpiderRule(
                        spider_id=new_spider.id,
                        allow_patterns=r.allow_patterns,
                        deny_patterns=r.deny_patterns,
                        restrict_xpaths=r.restrict_xpaths,
                        restrict_css=r.restrict_css,
                        callback=r.callback,
                        follow=r.follow,
                        priority=r.priority,
                    )
                )

            for st in s.settings:
                target.add(
                    SpiderSetting(
                        spider_id=new_spider.id,
                        key=st.key,
                        value=st.value,
                        type=st.type,
                    )
                )

        click.echo(f"   ✅ {len(spiders)} spiders (with rules and settings)")

        # Transfer scraped items
        if not skip_items:
            item_count = source.query(ScrapedItem).count()
            click.echo(f"\n📰 Transferring {item_count} scraped items...")

            batch_size = 1000
            transferred = 0
            for spider_id_old, spider_id_new in spider_id_map.items():
                items = (
                    source.query(ScrapedItem)
                    .filter(ScrapedItem.spider_id == spider_id_old)
                    .all()
                )
                for item in items:
                    target.add(
                        ScrapedItem(
                            spider_id=spider_id_new,
                            url=item.url,
                            title=item.title,
                            content=item.content,
                            published_date=item.published_date,
                            author=item.author,
                            scraped_at=item.scraped_at,
                            metadata_json=item.metadata_json,
                        )
                    )
                    transferred += 1
                    if transferred % batch_size == 0:
                        target.flush()
                        click.echo(f"   ... {transferred}/{item_count}")

            click.echo(f"   ✅ {transferred} items")
        else:
            click.echo("\n⏭️  Skipping scraped items (--skip-items)")

        # Transfer queue
        queue_items = source.query(CrawlQueue).all()
        click.echo(f"\n📋 Transferring {len(queue_items)} queue items...")

        for q in queue_items:
            target.add(
                CrawlQueue(
                    project_name=q.project_name,
                    website_url=q.website_url,
                    custom_instruction=q.custom_instruction,
                    status=q.status,
                    priority=q.priority,
                    error_message=q.error_message,
                    retry_count=q.retry_count,
                    created_at=q.created_at,
                    updated_at=q.updated_at,
                    completed_at=q.completed_at,
                )
            )

        click.echo(f"   ✅ {len(queue_items)} queue items")

        target.commit()
        click.echo("\n🎉 Transfer complete! Your new database is ready.")

    except Exception as e:
        target.rollback()
        click.echo(f"\n❌ Transfer failed: {e}")
        raise
    finally:
        source.close()
        target.close()
        source_engine.dispose()
