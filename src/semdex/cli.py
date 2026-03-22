import click


@click.group()
def cli():
    """semdex - A semantic project indexer for Claude."""
    pass


@cli.command()
def init():
    """Initialize semdex for the current project."""
    click.echo("semdex init - not yet implemented")


@cli.command()
@click.argument("target", required=False)
def index(target):
    """Build or rebuild the semantic index."""
    click.echo(f"semdex index {target or '.'} - not yet implemented")


@cli.command()
@click.argument("query")
@click.option("--top-k", default=10, type=int, help="Number of results")
def search(query, top_k):
    """Search the semantic index."""
    click.echo(f"semdex search '{query}' - not yet implemented")


@cli.command()
def serve():
    """Start the MCP server."""
    click.echo("semdex serve - not yet implemented")


@cli.command()
def status():
    """Show index statistics."""
    click.echo("semdex status - not yet implemented")


@cli.command()
@click.argument("path")
def forget(path):
    """Remove a path from the index."""
    click.echo(f"semdex forget '{path}' - not yet implemented")


@cli.group()
def hook():
    """Manage git hooks."""
    pass


@hook.command("install")
def hook_install():
    """Install the post-commit hook."""
    click.echo("semdex hook install - not yet implemented")


@hook.command("uninstall")
def hook_uninstall():
    """Uninstall the post-commit hook."""
    click.echo("semdex hook uninstall - not yet implemented")
