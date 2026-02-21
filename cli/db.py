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
