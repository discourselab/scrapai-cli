import click
import subprocess
import sys
import os
from pathlib import Path


@click.command(context_settings=dict(ignore_unknown_options=True))
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def setup(args):
    """Setup virtual environment and database"""
    skip_deps = "--skip-deps" in args

    click.echo("🚀 Setting up scrapai environment...")

    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    venv_path = Path(".venv")
    # Windows uses Scripts/python.exe, Unix uses bin/python
    if sys.platform == "win32":
        venv_python = venv_path / "Scripts" / "python.exe"
    else:
        venv_python = venv_path / "bin" / "python"

    if not skip_deps:
        if not venv_path.exists():
            click.echo("📦 Creating virtual environment...")
            try:
                subprocess.run(
                    [sys.executable, "-m", "venv", ".venv"], check=True, cwd=script_dir
                )
                click.echo("✅ Virtual environment created")
            except subprocess.CalledProcessError as e:
                click.echo(f"❌ Failed to create virtual environment: {e}")
                sys.exit(1)
        else:
            click.echo("✅ Virtual environment already exists")

        requirements_path = Path("requirements.txt")
        if requirements_path.exists():
            click.echo("📋 Installing requirements...")
            try:
                subprocess.run(
                    [str(venv_python), "-m", "pip", "install", "--upgrade", "pip"],
                    check=True,
                    cwd=script_dir,
                    capture_output=True,
                )
                subprocess.run(
                    [
                        str(venv_python),
                        "-m",
                        "pip",
                        "install",
                        "-r",
                        "requirements.txt",
                    ],
                    check=True,
                    cwd=script_dir,
                    capture_output=True,
                )
                click.echo("✅ Requirements installed")

                click.echo("🌐 Installing Playwright Chromium browser...")
                subprocess.run(
                    [str(venv_python), "-m", "playwright", "install", "chromium"],
                    check=True,
                    cwd=script_dir,
                )
                click.echo("✅ Playwright Chromium installed")

                # On Linux, remind about system dependencies
                if sys.platform.startswith("linux"):
                    click.echo(
                        "\n⚠️  Linux users: If Chromium fails to launch, install system dependencies:"
                    )
                    click.echo(
                        "   sudo .venv/bin/python -m playwright install-deps chromium"
                    )
                    click.echo("   (requires sudo for system package installation)\n")
            except subprocess.CalledProcessError as e:
                click.echo(f"❌ Failed to install requirements: {e}")
                sys.exit(1)
        else:
            click.echo("⚠️  requirements.txt not found")

    env_file = Path(".env")
    env_example = Path(".env.example")
    if not env_file.exists() and env_example.exists():
        click.echo("📝 Creating .env from .env.example...")
        try:
            import shutil

            shutil.copy(env_example, env_file)
            click.echo("✅ .env file created (using SQLite by default)")
        except Exception as e:
            click.echo(f"⚠️  Warning: Could not create .env: {e}")

    # Lock down .env — it holds secrets (proxy creds, DB URL, S3 keys). Set
    # owner-only (600) so other OS users on a shared host can't read it.
    if env_file.exists():
        try:
            os.chmod(env_file, 0o600)
            click.echo("🔒 .env permissions set to 600 (owner-only)")
        except Exception as e:
            click.echo(f"⚠️  Could not set .env permissions: {e}")

    # Test write permission to DATA_DIR
    click.echo("📁 Checking data directory permissions...")
    try:
        from dotenv import load_dotenv

        load_dotenv()
        data_dir = Path(os.getenv("DATA_DIR", "./data"))
        data_dir.mkdir(parents=True, exist_ok=True)

        test_file = data_dir / "welcome.md"
        test_file.write_text(
            "# Welcome to scrapai\n\nThis directory stores your crawl data."
        )
        click.echo(f"✅ Have permission to write to data directory: {data_dir}")
    except Exception as e:
        click.echo(f"❌ Don't have permission to write to data directory: {data_dir}")
        click.echo(f"   Error: {e}")
        click.echo("   Please check file permissions or change DATA_DIR in .env")
        sys.exit(1)

    click.echo("🗄️  Initializing database...")
    try:
        result = subprocess.run(
            [str(venv_python), "-m", "alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            cwd=script_dir,
        )
        if result.returncode == 0:
            click.echo("✅ Database initialized with migrations")
        else:
            click.echo("❌ Database migrations failed")
            click.echo(f"   Error: {result.stderr}")
            click.echo(
                "   Please check your DATABASE_URL in .env and database permissions"
            )
            sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Database setup failed: {e}")
        sys.exit(1)

    click.echo("🔧 Configuring Claude Code permissions...")
    try:
        import json

        settings_dir = Path(".claude")
        settings_dir.mkdir(exist_ok=True)
        settings_file = settings_dir / "settings.local.json"

        new_allow = [
            "Read",
            "Write",
            "Edit",
            "Update",
            "Glob",
            "Grep",
            "Bash(./scrapai:*)",
            "Bash(source:*)",
            "Bash(sqlite3:*)",
            "Bash(psql:*)",
            "Bash(xvfb-run:*)",
        ]
        new_deny = [
            "Edit(scrapai)",
            "Update(scrapai)",
            "Edit(.claude/*)",
            "Update(.claude/*)",
            "Write(**/*.py)",
            "Edit(**/*.py)",
            "Update(**/*.py)",
            "MultiEdit(**/*.py)",
            "Write(.env)",
            "Write(secrets/**)",
            "Write(config/**/*.key)",
            "Write(**/*password*)",
            "Write(**/*secret*)",
            "WebFetch",
            "WebSearch",
            "Bash(rm:*)",
        ]

        if settings_file.exists():
            with open(settings_file, "r") as f:
                settings = json.load(f)
        else:
            settings = {"permissions": {}}

        if "permissions" not in settings:
            settings["permissions"] = {}

        existing_allow = settings["permissions"].get("allow", [])
        for item in new_allow:
            if item not in existing_allow:
                existing_allow.append(item)
        settings["permissions"]["allow"] = existing_allow

        existing_deny = settings["permissions"].get("deny", [])
        for item in new_deny:
            if item not in existing_deny:
                existing_deny.append(item)
        settings["permissions"]["deny"] = existing_deny

        with open(settings_file, "w") as f:
            json.dump(settings, f, indent=2)

        click.echo("✅ Claude Code permissions configured")
    except Exception as e:
        click.echo(f"⚠️  Warning: Could not configure Claude Code settings: {e}")

    click.echo("🎉 scrapai setup complete!")
    click.echo("📝 You can now:")
    cmd_prefix = "scrapai" if sys.platform == "win32" else "./scrapai"
    click.echo(f"   • List spiders: {cmd_prefix} spiders list --project <name>")
    click.echo(
        f"   • Import spiders: {cmd_prefix} spiders import <file> --project <name>"
    )
    click.echo(f"   • Run crawls: {cmd_prefix} crawl <spider_name> --project <name>")


@click.command()
def verify():
    """Verify environment setup (no installations)"""
    click.echo("🔍 Verifying scrapai environment...\n")

    all_good = True
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    venv_path = Path(".venv")
    # Windows uses Scripts/python.exe, Unix uses bin/python
    if sys.platform == "win32":
        venv_python = venv_path / "Scripts" / "python.exe"
    else:
        venv_python = venv_path / "bin" / "python"

    if not venv_path.exists():
        click.echo("❌ Virtual environment not found")
        cmd_prefix = "scrapai" if sys.platform == "win32" else "./scrapai"
        click.echo(f"   Run: {cmd_prefix} setup")
        all_good = False
    else:
        click.echo("✅ Virtual environment exists")

        try:
            result = subprocess.run(
                [
                    str(venv_python),
                    "-c",
                    'import scrapy, sqlalchemy, alembic; print("ok")',
                ],
                capture_output=True,
                text=True,
                cwd=script_dir,
            )
            if result.returncode == 0 and "ok" in result.stdout:
                click.echo("✅ Core dependencies installed")
            else:
                click.echo("❌ Missing dependencies")
                cmd_prefix = "scrapai" if sys.platform == "win32" else "./scrapai"
                click.echo(f"   Run: {cmd_prefix} setup")
                all_good = False
        except Exception as e:
            click.echo(f"❌ Error checking dependencies: {e}")
            click.echo("   Run: ./scrapai setup")
            all_good = False

    if all_good:
        try:
            result = subprocess.run(
                [str(venv_python), "-m", "alembic", "current"],
                capture_output=True,
                text=True,
                cwd=script_dir,
            )
            if result.returncode == 0:
                if "head" in result.stdout or result.stdout.strip():
                    click.echo("✅ Database initialized")
                else:
                    click.echo("❌ Database not initialized")
                    cmd_prefix = "scrapai" if sys.platform == "win32" else "./scrapai"
                    click.echo(f"   Run: {cmd_prefix} setup")
                    all_good = False
            else:
                click.echo("❌ Unable to check database status")
                cmd_prefix = "scrapai" if sys.platform == "win32" else "./scrapai"
                click.echo(f"   Run: {cmd_prefix} setup")
                all_good = False
        except Exception as e:
            click.echo(f"❌ Error checking database: {e}")
            cmd_prefix = "scrapai" if sys.platform == "win32" else "./scrapai"
            click.echo(f"   Run: {cmd_prefix} setup")
            all_good = False

    click.echo()
    if all_good:
        click.echo("🎉 Environment is ready!")
        click.echo("📝 You can now:")
        cmd_prefix = "scrapai" if sys.platform == "win32" else "./scrapai"
        click.echo(f"   • List spiders: {cmd_prefix} spiders list --project <name>")
        click.echo(
            f"   • Import spiders: {cmd_prefix} spiders import <file> --project <name>"
        )
        click.echo(
            f"   • Run crawls: {cmd_prefix} crawl <spider_name> --project <name>"
        )
    else:
        click.echo("⚠️  Environment setup incomplete")
        cmd_prefix = "scrapai" if sys.platform == "win32" else "./scrapai"
        click.echo(f"   Run: {cmd_prefix} setup")
