import click
import subprocess
import sys
import os


@click.group()
def db():
    """Database management"""
    pass


@db.command('migrate')
def migrate():
    """Run database migrations"""
    click.echo("🔄 Running database migrations...")
    try:
        result = subprocess.run([
            sys.executable, '-m', 'alembic', 'upgrade', 'head'
        ], cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if result.returncode == 0:
            click.echo("✅ Migrations completed successfully!")
        else:
            click.echo("❌ Migration failed!")
    except Exception as e:
        click.echo(f"❌ Error running migrations: {e}")


@db.command('current')
def current():
    """Show current migration revision"""
    try:
        subprocess.run([
            sys.executable, '-m', 'alembic', 'current'
        ], cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    except Exception as e:
        click.echo(f"❌ Error checking current revision: {e}")


@db.command('transfer')
@click.argument('source_url')
@click.option('--skip-items', is_flag=True, help='Skip scraped_items (transfer only spiders and queue)')
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
                name=s.name, allowed_domains=s.allowed_domains,
                start_urls=s.start_urls, source_url=s.source_url,
                active=s.active, project=s.project,
                created_at=s.created_at, updated_at=s.updated_at,
            )
            target.add(new_spider)
            target.flush()
            spider_id_map[s.id] = new_spider.id

            for r in s.rules:
                target.add(SpiderRule(
                    spider_id=new_spider.id,
                    allow_patterns=r.allow_patterns, deny_patterns=r.deny_patterns,
                    restrict_xpaths=r.restrict_xpaths, restrict_css=r.restrict_css,
                    callback=r.callback, follow=r.follow, priority=r.priority,
                ))

            for st in s.settings:
                target.add(SpiderSetting(
                    spider_id=new_spider.id,
                    key=st.key, value=st.value, type=st.type,
                ))

        click.echo(f"   ✅ {len(spiders)} spiders (with rules and settings)")

        # Transfer scraped items
        if not skip_items:
            item_count = source.query(ScrapedItem).count()
            click.echo(f"\n📰 Transferring {item_count} scraped items...")

            batch_size = 1000
            transferred = 0
            for spider_id_old, spider_id_new in spider_id_map.items():
                items = source.query(ScrapedItem).filter(
                    ScrapedItem.spider_id == spider_id_old
                ).all()
                for item in items:
                    target.add(ScrapedItem(
                        spider_id=spider_id_new, url=item.url,
                        title=item.title, content=item.content,
                        published_date=item.published_date, author=item.author,
                        scraped_at=item.scraped_at, metadata_json=item.metadata_json,
                    ))
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
            target.add(CrawlQueue(
                project_name=q.project_name, website_url=q.website_url,
                custom_instruction=q.custom_instruction, status=q.status,
                priority=q.priority, error_message=q.error_message,
                retry_count=q.retry_count, created_at=q.created_at,
                updated_at=q.updated_at, completed_at=q.completed_at,
            ))

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
