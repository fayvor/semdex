# semdex

A semantic project indexer for Claude that builds a searchable, on-disk database of your project's files using embeddings and vector search.

## Overview

`semdex` creates a local RAG (Retrieval-Augmented Generation) database for your project. When Claude works in your project, it can quickly search this semantic index to find relevant files, making it smarter about understanding your codebase without relying solely on grep or find commands.

## How It Works

1. **Build Index**: Run `semdex` from your project root to scan and index all project files
2. **Semantic Search**: The indexer creates embeddings for each file using a language model
3. **Local Storage**: The vector database is stored in `.claude/` (git-ignored) within your project
4. **Claude Integration**: A companion Claude skill uses this index to find related files when answering questions or implementing features

## Features

- **Command-line tool**: Simple `semdex` command to build/rebuild your project index
- **Semantic search**: Finds files based on meaning, not just keyword matching
- **Embedding-based**: Uses embeddings to understand code and document content
- **Chroma vector store**: Built on Chroma for efficient local vector storage
- **Claude skill included**: Automatically prefers indexed search over slower grep/find operations
- **Git-ignored**: Index is stored in `.claude/` and won't clutter your repository

## Installation

```bash
npm install -g semdex
# or
pip install semdex
```

## Usage

```bash
# Build or rebuild the index for your current project
semdex

# The index will be created in .claude/ and is now available to Claude
```

## Integration with Claude

Once installed, Claude will automatically use the semdex index when:
- Searching for related files in your project
- Understanding code structure and dependencies
- Finding examples or relevant code sections
- Building context about your project

The Claude skill prioritizes semdex results before falling back to grep, find, or other file search methods.

## What Gets Indexed

By default, semdex indexes:
- Source code files (.js, .ts, .py, .java, etc.)
- Documentation (README, docs/*.md)
- Configuration files (package.json, tsconfig.json, etc.)
- Comments and docstrings within code

It excludes:
- node_modules/
- .git/
- dist/, build/, coverage/
- Other common build/cache directories

## Storage

The index is stored in:
```
.claude/
└── semdex/
    └── chroma.db
```

Add `.claude/` to your `.gitignore` to keep the index out of version control.
