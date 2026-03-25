from __future__ import annotations

import os
import shutil
from pathlib import Path

import click

from semdex.config import SemdexConfig
from semdex.hooks import install_hook, uninstall_hook
from semdex.indexer import index_project
from semdex.server import run_server
from semdex.store import SemdexStore


def _find_project_root() -> Path:
    """Find the project root (directory containing .git)."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / ".git").is_dir():
            return parent
    return cwd


@click.group()
def cli():
    """semdex - A semantic project indexer for Claude."""
    pass


@cli.command()
def init():
    """Initialize semdex for the current project."""
    root = _find_project_root()
    config = SemdexConfig(project_root=root)
    config.ensure_dirs()

    # Add .claude/ to .gitignore
    gitignore = root / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        if ".claude/" not in content:
            with open(gitignore, "a") as f:
                f.write("\n.claude/\n")
            click.echo("Added .claude/ to .gitignore")
    else:
        gitignore.write_text(".claude/\n")
        click.echo("Created .gitignore with .claude/")

    # Save config
    config.save()

    # Build initial index
    click.echo("Building initial index...")
    stats = index_project(root, config)
    click.echo(f"Indexed {stats['files_indexed']} files ({stats['chunks_created']} chunks)")

    # Install hook
    if (root / ".git").is_dir():
        install_hook(root)
        click.echo("Installed post-commit hook")

    # Print next steps
    click.echo("\n--- Next steps ---")
    click.echo("")
    click.echo("1. Register the MCP server with Claude Code:")
    click.echo("   claude mcp add semdex -- semdex serve")
    click.echo("")
    click.echo("2. Verify Claude can see it:")
    click.echo("   claude mcp list")
    click.echo("")
    click.echo("3. Start a Claude Code session and ask it to search your project!")
    click.echo("   Claude now has access to: search, related, summary tools")


@cli.command()
@click.argument("target", required=False)
@click.option("--force", is_flag=True, help="Force re-index (bypass mtime checks or rebuild from scratch)")
def index(target, force):
    """Build or rebuild the semantic index."""
    root = _find_project_root()
    config = SemdexConfig.load(root)
    config.ensure_dirs()

    if force and not target:
        # Full project + force: nuclear option - wipe and rebuild
        click.echo("Deleting existing index...")
        if config.db_path.exists():
            shutil.rmtree(config.db_path)
        click.echo("Rebuilding full index from scratch...")
        stats = index_project(root, config)
    elif target:
        # Specific file/dir: pass force flag to bypass mtime check
        target_path = Path(target).resolve()
        if target_path.is_dir():
            click.echo(f"Indexing directory: {target_path}")
            stats = index_project(root, config, target_dir=target_path, force=force)
        elif target_path.is_file():
            click.echo(f"Indexing file: {target_path}")
            stats = index_project(root, config, files=[target_path], force=force)
        else:
            click.echo(f"Error: {target} not found", err=True)
            raise SystemExit(1)
    else:
        # Full project, no force: smart indexing
        click.echo("Rebuilding full index...")
        stats = index_project(root, config)

    # Display results
    skipped = stats.get("files_skipped", 0)
    deleted = stats.get("files_deleted", 0)
    if skipped > 0 or deleted > 0:
        click.echo(f"Processed {stats['files_discovered']} files "
                   f"({skipped} skipped, {stats['files_indexed']} indexed, {deleted} deleted)")
    click.echo(f"Indexed {stats['files_indexed']} files ({stats['chunks_created']} chunks)")


@cli.command()
@click.argument("query")
@click.option("--top-k", default=10, type=int, help="Number of results")
def search(query, top_k):
    """Search the semantic index."""
    root = _find_project_root()
    config = SemdexConfig.load(root)

    from semdex.embeddings import LocalEmbedder

    embedder = LocalEmbedder(model_name=config.embedding_model)
    store = SemdexStore(db_path=config.db_path, dimension=embedder.dimension)

    vector = embedder.encode([query])[0]
    results = store.search(vector, top_k=top_k)

    if not results:
        click.echo("No results found. Is the index built? Run: semdex init")
        return

    for i, r in enumerate(results, 1):
        score = r.get("score", 0)
        click.echo(f"{i}. {r['file_path']}:{r['start_line']}-{r['end_line']} "
                    f"({r['chunk_type']}, score: {score:.4f})")


@cli.command()
def serve():
    """Start the MCP server."""
    root = _find_project_root()
    run_server(root)


@cli.command()
def status():
    """Show index statistics."""
    root = _find_project_root()
    config = SemdexConfig.load(root)

    if not config.db_path.exists():
        click.echo("No index found. Run: semdex init")
        return

    store = SemdexStore(db_path=config.db_path)
    stats = store.stats()
    click.echo(f"Files indexed: {stats['total_files']}")
    click.echo(f"Total chunks:  {stats['total_chunks']}")
    click.echo(f"Last indexed:  {stats['last_indexed']}")
    click.echo(f"Index path:    {config.semdex_dir}")


@cli.command()
@click.argument("path")
def forget(path):
    """Remove a path from the index."""
    root = _find_project_root()
    config = SemdexConfig.load(root)
    store = SemdexStore(db_path=config.db_path)

    target = Path(path).resolve()
    if target.is_dir():
        store.delete_by_source_dir(str(target))
        click.echo(f"Removed directory from index: {target}")
    else:
        rel = str(Path(path))
        store.delete_by_file(rel)
        click.echo(f"Removed file from index: {rel}")


@cli.group()
def hook():
    """Manage git hooks."""
    pass


@hook.command("install")
def hook_install():
    """Install the post-commit hook."""
    root = _find_project_root()
    if not (root / ".git").is_dir():
        click.echo("Not a git repository", err=True)
        raise SystemExit(1)
    install_hook(root)
    click.echo("Post-commit hook installed")


@hook.command("uninstall")
def hook_uninstall():
    """Uninstall the post-commit hook."""
    root = _find_project_root()
    uninstall_hook(root)
    click.echo("Post-commit hook removed")
