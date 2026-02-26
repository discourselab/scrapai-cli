import click
import json
import sys


@click.group()
def spiders():
    """Spider management"""
    pass


@spiders.command("list")
@click.option(
    "--project", default=None, help="Filter by project name (default: show all)"
)
def list_spiders(project):
    """List all spiders in DB"""
    from core.db import get_db
    from core.models import Spider

    db = next(get_db())

    query = db.query(Spider)
    if project:
        query = query.filter(Spider.project == project)
        click.echo(f"📋 Available Spiders (DB) - Project: {project}:")
    else:
        click.echo("📋 Available Spiders (DB) - All Projects:")

    spiders = query.all()
    if spiders:
        for s in spiders:
            created = (
                s.created_at.strftime("%Y-%m-%d %H:%M") if s.created_at else "Unknown"
            )
            updated = (
                s.updated_at.strftime("%Y-%m-%d %H:%M") if s.updated_at else created
            )
            project_tag = f"[{s.project}]" if s.project else "[default]"

            click.echo(
                f"  • {s.name} {project_tag} (Active: {s.active}) - Created: {created}, Updated: {updated}"
            )
            if s.source_url:
                click.echo(f"    Source: {s.source_url}")
    else:
        if project:
            click.echo(f"No spiders found in project '{project}'.")
        else:
            click.echo("No spiders found in database.")


@spiders.command("import")
@click.argument("file")
@click.option("--project", default="default", help="Project name (default: default)")
@click.option(
    "--skip-validation",
    is_flag=True,
    help="Skip Pydantic validation (backward compatibility)",
)
def import_spider(file, project, skip_validation):
    """Import spider from JSON file (use "-" for stdin)"""
    from core.db import get_db
    from core.models import Spider, SpiderRule, SpiderSetting
    from core.schemas import SpiderConfigSchema
    from pydantic import ValidationError

    db = next(get_db())

    try:
        # Load JSON
        if file == "-":
            data = json.load(sys.stdin)
        else:
            with open(file, "r") as f:
                data = json.load(f)

        # Validate with Pydantic schema (unless --skip-validation)
        if skip_validation:
            click.echo("⚠️  Skipping validation (--skip-validation flag)")
            validated = None
            # Use raw data
            spider_name = data["name"]
            allowed_domains = data["allowed_domains"]
            start_urls = data["start_urls"]
            source_url = data.get("source_url")
            rules = data.get("rules", [])
            settings_dict = data.get("settings", {})
            callbacks_dict = data.get("callbacks")
        else:
            try:
                validated = SpiderConfigSchema(**data)
                spider_name = validated.name
                allowed_domains = validated.allowed_domains
                start_urls = validated.start_urls
                source_url = validated.source_url
                rules = [r.model_dump() for r in validated.rules]
                settings_dict = validated.settings.model_dump(
                    exclude_none=True, exclude_unset=True
                )
                # Extract callbacks (convert to dict)
                callbacks_dict = None
                if validated.callbacks:
                    callbacks_dict = {
                        name: cb.model_dump()
                        for name, cb in validated.callbacks.items()
                    }
            except ValidationError as e:
                click.echo("❌ Spider configuration validation failed:")
                for error in e.errors():
                    field = " -> ".join(str(x) for x in error["loc"])
                    message = error["msg"]
                    click.echo(f"   • {field}: {message}")
                click.echo(
                    "\n💡 Use --skip-validation to bypass validation (not recommended)"
                )
                return

        # Check for existing spider
        existing = db.query(Spider).filter(Spider.name == spider_name).first()
        if existing:
            click.echo(f"⚠️  Spider '{spider_name}' already exists. Updating...")
            existing.allowed_domains = allowed_domains
            existing.start_urls = start_urls
            existing.source_url = source_url
            existing.project = project
            existing.callbacks_config = callbacks_dict

            # Delete old rules and settings
            db.query(SpiderRule).filter(SpiderRule.spider_id == existing.id).delete()
            db.query(SpiderSetting).filter(
                SpiderSetting.spider_id == existing.id
            ).delete()
            spider = existing
        else:
            # Create new spider
            spider = Spider(
                name=spider_name,
                allowed_domains=allowed_domains,
                start_urls=start_urls,
                source_url=source_url,
                project=project,
                callbacks_config=callbacks_dict,
            )
            db.add(spider)
            db.flush()

        # Add rules
        for rule_data in rules:
            # Handle both validated Pydantic objects and raw dicts
            if isinstance(rule_data, dict):
                rule = SpiderRule(
                    spider_id=spider.id,
                    allow_patterns=rule_data.get("allow"),
                    deny_patterns=rule_data.get("deny"),
                    restrict_xpaths=rule_data.get("restrict_xpaths"),
                    restrict_css=rule_data.get("restrict_css"),
                    callback=rule_data.get("callback"),
                    follow=rule_data.get("follow", True),
                    priority=rule_data.get("priority", 0),
                )
            else:
                # Already a validated Pydantic object
                rule = SpiderRule(
                    spider_id=spider.id,
                    allow_patterns=rule_data.get("allow"),
                    deny_patterns=rule_data.get("deny"),
                    restrict_xpaths=rule_data.get("restrict_xpaths"),
                    restrict_css=rule_data.get("restrict_css"),
                    callback=rule_data.get("callback"),
                    follow=rule_data.get("follow", True),
                    priority=rule_data.get("priority", 0),
                )
            db.add(rule)

        # Add settings
        for k, v in settings_dict.items():
            # Convert value to JSON string if it's a list/dict
            if isinstance(v, (list, dict)):
                value_str = json.dumps(v)
                type_name = "json"
            else:
                value_str = str(v)
                type_name = type(v).__name__

            setting = SpiderSetting(
                spider_id=spider.id, key=k, value=value_str, type=type_name
            )
            db.add(setting)

        db.commit()
        click.echo(f"✅ Spider '{spider.name}' imported successfully!")
        click.echo(f"   Project: {project}")
        click.echo(f"   Domains: {', '.join(allowed_domains)}")
        click.echo(f"   Start URLs: {len(start_urls)}")
        click.echo(f"   Rules: {len(rules)}")
        if callbacks_dict:
            click.echo(
                f"   Callbacks: {len(callbacks_dict)} ({', '.join(callbacks_dict.keys())})"
            )

    except json.JSONDecodeError as e:
        click.echo(f"❌ Invalid JSON file: {e}")
    except FileNotFoundError:
        click.echo(f"❌ File not found: {file}")
    except Exception as e:
        db.rollback()
        click.echo(f"❌ Error importing spider: {e}")


@spiders.command("delete")
@click.argument("name")
@click.option("--project", default=None, help="Project name")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation prompt")
def delete_spider(name, project, force):
    """Delete a spider"""
    from core.db import get_db
    from core.models import Spider

    db = next(get_db())
    query = db.query(Spider).filter(Spider.name == name)

    if project:
        query = query.filter(Spider.project == project)
        project_msg = f" in project '{project}'"
    else:
        project_msg = ""

    spider = query.first()

    if spider:
        if not force:
            confirm = input(
                f"Are you sure you want to delete spider '{name}'{project_msg}? (y/N): "
            )
            if confirm.lower() != "y":
                click.echo("❌ Delete cancelled")
                return

        db.delete(spider)
        db.commit()
        click.echo(f"🗑️  Spider '{name}'{project_msg} deleted!")
    else:
        click.echo(f"❌ Spider '{name}'{project_msg} not found.")
