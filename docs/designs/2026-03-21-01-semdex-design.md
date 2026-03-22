# semdex Design

A semantic project indexer for Claude that builds a searchable, on-disk database of your project's files using embeddings and vector search, exposed via MCP.

## Architecture Overview

**Core components:**

1. **CLI** (`semdex`) -- entry point for `init`, `index`, `search`, `hook install/uninstall`, `serve`, `status`, `forget`
2. **Indexer** -- walks project files, applies hybrid chunking, generates embeddings, stores in LanceDB
3. **MCP Server** -- exposes `search`, `related`, and `summary` tools to Claude Code
4. **Hook** -- git post-commit hook that triggers incremental re-indexing of changed files

**Data flow:**

```
Project files -> Indexer -> Embeddings (local model) -> LanceDB (.claude/semdex/)
                                                            |
Claude Code -> MCP Server -> query LanceDB -> ranked results back to Claude
                                                            |
git commit -> post-commit hook -> incremental re-index of changed files
```

**Storage:** Everything lives in `.claude/semdex/` -- LanceDB tables, config, and model cache. Git-ignored by default.

## Technology Choices

- **Language:** Python
- **Embeddings:** Local-first with `sentence-transformers` (`all-MiniLM-L6-v2`, ~80MB). Optional API-based providers configurable via `semdex config`.
- **Vector store:** LanceDB -- embedded, zero-config, single-directory storage, handles both vectors and metadata.
- **Chunking:** Tree-sitter for language-aware splitting of large files, sliding-window fallback for unsupported file types.
- **CLI framework:** Click
- **MCP:** Python MCP SDK with stdio transport

## CLI Commands

### `semdex init`

One-time project setup:
- Creates `.claude/semdex/` directory
- Adds `.claude/` to `.gitignore` if not already present
- Runs full initial index of the project
- Installs the git post-commit hook
- Registers the MCP server in Claude Code's config

### `semdex index`

Three modes:
- `semdex index` -- full re-index of the project (respects `.gitignore` and default exclusions)
- `semdex index <file_path>` -- re-index specific files
- `semdex index <dir_path>` -- index a directory, ignoring `.gitignore` rules. Works for directories inside or outside the project. Indexed content is tagged with its source directory for separate management.

### `semdex search <query>`

CLI search for debugging/testing:
- Takes a natural language query, prints ranked results with file paths and scores
- Useful for verifying the index works without going through Claude

### `semdex hook install / uninstall`

Manage the post-commit hook:
- Installs/removes the hook from `.git/hooks/post-commit`
- Plays nicely with existing hooks (appends rather than overwrites)

### `semdex serve`

Starts the MCP server (called by Claude Code, not typically run manually).

### `semdex status`

Shows index stats: file count, last indexed time, index size on disk.

### `semdex forget <path>`

Remove a manually-added directory or file from the index. Necessary for content added via `semdex index <dir>` since gitignore-skipping content won't be cleaned up automatically.

## Indexer & Chunking

### File discovery

- Walks the project tree from the root
- Respects `.gitignore` rules (using `pathspec` library)
- Built-in exclusion list: `node_modules/`, `.git/`, `dist/`, `build/`, `coverage/`, `__pycache__/`, `.venv/`
- Includes source code, docs, and config files. Skips binaries and media.

### Hybrid chunking strategy

- **Small files (<=200 lines):** one embedding per file
- **Large files (>200 lines):** split at logical boundaries using tree-sitter (functions, classes, top-level blocks), falling back to sliding-window with overlap for unsupported file types
- Each chunk stores metadata: file path, line range, chunk type (whole-file / function / class), last modified timestamp

### Embeddings

- Default: `sentence-transformers` with `all-MiniLM-L6-v2`
- Optional: API-based provider via config
- Generated in batches for efficiency

### Incremental re-indexing (post-commit hook)

- Gets changed files from `git diff HEAD~1 --name-only`
- Deletes old chunks for those files from LanceDB
- Re-indexes only the changed files
- Handles deleted files by removing their entries

## MCP Server Tools

### `search`

- **Input:** `query` (string), optional `top_k` (int, default 10)
- **Returns:** ranked list of `{ file_path, line_range, snippet, score, chunk_type }`
- Semantic search across the entire index

### `related`

- **Input:** `file_path` (string), optional `top_k` (int, default 10)
- **Returns:** ranked list of files/chunks most similar to the given file's embedding
- Use case: find tests, related modules, or connected code

### `summary`

- **Input:** `file_path` (string)
- **Returns:** `{ file_path, chunk_count, chunk_types, last_indexed, top_keywords }`
- Structured metadata from the index, not a generated summary

### Server details

- Runs via `semdex serve` using the MCP Python SDK
- Uses stdio transport
- Registered in Claude Code config by `semdex init`

## Error Handling & Edge Cases

- **No index:** MCP tools return a clear message directing user to run `semdex init`
- **Stale results:** Results include `last_indexed` timestamp; missing files flagged as stale
- **Large projects:** Progress bar during indexing, batched embeddings, configurable max file size (default 1MB)
- **Hook failures:** Logged to `.claude/semdex/hook.log`, never block the commit
- **Binary files:** Detected and skipped automatically
- **Unknown text files:** Indexed with whole-file embedding, no tree-sitter parsing
- **Concurrent access:** LanceDB handles concurrent reads; writes use a file lock

## Project Structure

```
semdex/
├── pyproject.toml
├── src/
│   └── semdex/
│       ├── __init__.py
│       ├── cli.py           # Click CLI
│       ├── indexer.py       # File discovery, embedding generation
│       ├── chunker.py       # Hybrid chunking logic
│       ├── embeddings.py    # Embedding provider abstraction
│       ├── store.py         # LanceDB operations
│       ├── server.py        # MCP server
│       ├── hooks.py         # Git hook management
│       └── config.py        # Project config
└── tests/
    ├── test_indexer.py
    ├── test_chunker.py
    ├── test_store.py
    └── test_server.py
```

## Key Dependencies

- `click` -- CLI framework
- `sentence-transformers` -- local embeddings
- `lancedb` -- vector store
- `tree-sitter` + language grammars -- smart chunking
- `mcp` -- MCP Python SDK
- `pathspec` -- gitignore parsing
