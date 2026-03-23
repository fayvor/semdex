# semdex

A semantic project indexer for Claude that builds a searchable, on-disk database of your project's files using embeddings and vector search.

## Overview

`semdex` creates a local RAG (Retrieval-Augmented Generation) database for your project. When Claude works in your project, it can quickly search this semantic index to find relevant files, making it smarter about understanding your codebase without relying solely on grep or find commands.

## How It Works

1. **Build Index**: Run `semdex init` from your project root to scan and index all project files
2. **Semantic Search**: The indexer creates embeddings for each file using a local ONNX model (no API keys needed)
3. **Local Storage**: The vector database is stored in `.claude/semdex/` (git-ignored) within your project
4. **Claude Integration**: An MCP server exposes `search`, `related`, and `summary` tools that Claude can call directly

## Features

- **Command-line tool**: Simple `semdex` command to build/rebuild your project index
- **Semantic search**: Finds files based on meaning, not just keyword matching
- **Local embeddings**: Uses fastembed with ONNX Runtime -- no PyTorch, no API keys
- **LanceDB vector store**: Embedded vector database, zero config
- **MCP server**: Claude Code calls semdex tools directly via the Model Context Protocol
- **Smart chunking**: Tree-sitter-based splitting for large files (Python, JS, TS)
- **Auto re-index**: Git post-commit hook keeps the index fresh
- **Git-ignored**: Index is stored in `.claude/` and won't clutter your repository

## Installation

```bash
# Install globally (recommended)
pipx install semdex

# Or with pip
pip install semdex
```

For development:
```bash
git clone <repo-url>
cd semdex
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Quick Start

```bash
# 1. Initialize semdex in your project
cd ~/your-project
semdex init

# 2. Register the MCP server with Claude Code
claude mcp add semdex -- semdex serve

# 3. Verify Claude can see it
claude mcp list

# 4. Start a Claude Code session -- Claude now has search, related, and summary tools!
```

## CLI Commands

```bash
semdex init                  # Initialize: index project, install git hook, print setup instructions
semdex index                 # Rebuild the full index
semdex index <dir>           # Index an external directory (ignores .gitignore)
semdex index <file>          # Re-index a specific file
semdex search <query>        # Search the index from the command line
semdex status                # Show index stats (file count, last indexed, size)
semdex forget <path>         # Remove a path from the index
semdex hook install          # Install the git post-commit hook
semdex hook uninstall        # Remove the git post-commit hook
semdex serve                 # Start the MCP server (called by Claude Code)
```

All commands accept `--project-root-dir <path>` to target a specific project.

## Integration with Claude Code

Once the MCP server is registered, Claude has access to three tools:

- **`search`**: Semantic search across your codebase. Claude can find files by meaning, not just keywords.
- **`related`**: Find files related to a given file. Useful when Claude is editing code and needs to find tests, models, or connected modules.
- **`summary`**: Get index metadata for a file (chunk count, types, last indexed).

## What Gets Indexed

By default, semdex indexes:
- Source code files (.js, .ts, .py, .java, etc.)
- Documentation (README, docs/*.md)
- Configuration files (package.json, tsconfig.json, etc.)
- Comments and docstrings within code

It excludes:
- `node_modules/`, `.git/`, `dist/`, `build/`, `coverage/`, `__pycache__/`, `.venv/`
- Binary files (images, archives, compiled files)
- Files over 1MB
- Patterns in your `.gitignore`

## Storage

The index is stored in:
```
.claude/
└── semdex/
    ├── lance.db/     # LanceDB vector database
    └── config.json   # semdex configuration
```

`semdex init` automatically adds `.claude/` to your `.gitignore`.
