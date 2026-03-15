import click


@click.group()
def projects():
    """Project management"""
    pass


@projects.command("list")
def list_projects():
    """List all projects"""
    from core.services.project_service import list_projects as _list_projects

    project_list = _list_projects()

    if project_list:
        click.echo("📁 Available Projects:")
        for proj in project_list:
            click.echo(f"  • {proj.name}")
            click.echo(f"    Spiders: {proj.spider_count}")
    else:
        click.echo("No projects found.")
