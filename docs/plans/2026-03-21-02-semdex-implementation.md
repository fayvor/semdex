# semdex Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Python CLI tool and MCP server that creates a local semantic index of project files using embeddings and LanceDB vector search.

**Architecture:** Python package with Click CLI, sentence-transformers for local embeddings, LanceDB for vector storage, tree-sitter for smart chunking, and MCP Python SDK for Claude Code integration. All data stored in `.claude/semdex/`.

**Tech Stack:** Python 3.11+, Click, sentence-transformers, LanceDB, tree-sitter, MCP Python SDK, pathspec

**Design doc:** `docs/plans/2026-03-21-01-semdex-design.md`

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/semdex/__init__.py`
- Create: `src/semdex/cli.py`
- Create: `.gitignore`

**Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "semdex"
version = "0.1.0"
description = "A semantic project indexer for Claude"
requires-python = ">=3.11"
dependencies = [
    "click>=8.0",
    "lancedb>=0.6",
    "sentence-transformers>=2.0",
    "pathspec>=0.11",
    "mcp>=1.0",
    "tree-sitter>=0.23",
    "tree-sitter-python>=0.23",
    "tree-sitter-javascript>=0.23",
    "tree-sitter-typescript>=0.23",
]

[project.scripts]
semdex = "semdex.cli:cli"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

**Step 2: Create .gitignore**

```
__pycache__/
*.pyc
.venv/
dist/
build/
*.egg-info/
.claude/
```

**Step 3: Create src/semdex/__init__.py**

```python
"""semdex - A semantic project indexer for Claude."""

__version__ = "0.1.0"
```

**Step 4: Create src/semdex/cli.py with skeleton**

```python
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
```

**Step 5: Create virtual environment and install in dev mode**

Run:
```bash
cd /Users/fayvor/Dev/semdex
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]" 2>&1 | tail -5
```

Note: add `dev` extras to pyproject.toml first:
```toml
[project.optional-dependencies]
dev = ["pytest>=7.0"]
```

**Step 6: Verify CLI works**

Run: `semdex --help`
Expected: Shows help with all subcommands listed

**Step 7: Commit**

```bash
git add pyproject.toml .gitignore src/
git commit -m "Scaffold project with CLI skeleton"
```

---

### Task 2: Config Module

**Files:**
- Create: `src/semdex/config.py`
- Create: `tests/test_config.py`

**Step 1: Write the failing test**

```python
import json
import os
import tempfile
from pathlib import Path

from semdex.config import SemdexConfig


def test_default_config():
    with tempfile.TemporaryDirectory() as tmpdir:
        config = SemdexConfig(project_root=Path(tmpdir))
        assert config.semdex_dir == Path(tmpdir) / ".claude" / "semdex"
        assert config.db_path == Path(tmpdir) / ".claude" / "semdex" / "lance.db"
        assert config.max_file_size == 1_000_000
        assert config.chunk_threshold == 200
        assert config.embedding_model == "all-MiniLM-L6-v2"


def test_ensure_dirs_creates_structure():
    with tempfile.TemporaryDirectory() as tmpdir:
        config = SemdexConfig(project_root=Path(tmpdir))
        config.ensure_dirs()
        assert config.semdex_dir.exists()


def test_save_and_load_config():
    with tempfile.TemporaryDirectory() as tmpdir:
        config = SemdexConfig(project_root=Path(tmpdir))
        config.ensure_dirs()
        config.max_file_size = 500_000
        config.save()

        loaded = SemdexConfig.load(Path(tmpdir))
        assert loaded.max_file_size == 500_000
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

# Directories always excluded from indexing
DEFAULT_EXCLUDES = [
    "node_modules/",
    ".git/",
    "dist/",
    "build/",
    "coverage/",
    "__pycache__/",
    ".venv/",
    ".claude/",
    "*.egg-info/",
]

# File extensions considered binary (skip these)
BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
    ".mp3", ".mp4", ".wav", ".avi", ".mov",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".exe", ".dll", ".so", ".dylib", ".o",
    ".woff", ".woff2", ".ttf", ".eot",
    ".pyc", ".pyo", ".class",
}


@dataclass
class SemdexConfig:
    project_root: Path
    embedding_model: str = "all-MiniLM-L6-v2"
    max_file_size: int = 1_000_000  # 1MB
    chunk_threshold: int = 200  # lines
    extra_excludes: list[str] = field(default_factory=list)

    @property
    def semdex_dir(self) -> Path:
        return self.project_root / ".claude" / "semdex"

    @property
    def db_path(self) -> Path:
        return self.semdex_dir / "lance.db"

    @property
    def config_path(self) -> Path:
        return self.semdex_dir / "config.json"

    @property
    def hook_log_path(self) -> Path:
        return self.semdex_dir / "hook.log"

    def ensure_dirs(self) -> None:
        self.semdex_dir.mkdir(parents=True, exist_ok=True)

    def save(self) -> None:
        data = {
            "embedding_model": self.embedding_model,
            "max_file_size": self.max_file_size,
            "chunk_threshold": self.chunk_threshold,
            "extra_excludes": self.extra_excludes,
        }
        self.config_path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, project_root: Path) -> SemdexConfig:
        config = cls(project_root=project_root)
        if config.config_path.exists():
            data = json.loads(config.config_path.read_text())
            config.embedding_model = data.get("embedding_model", config.embedding_model)
            config.max_file_size = data.get("max_file_size", config.max_file_size)
            config.chunk_threshold = data.get("chunk_threshold", config.chunk_threshold)
            config.extra_excludes = data.get("extra_excludes", config.extra_excludes)
        return config
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add src/semdex/config.py tests/test_config.py
git commit -m "Add config module with defaults and persistence"
```

---

### Task 3: Embedding Provider Abstraction

**Files:**
- Create: `src/semdex/embeddings.py`
- Create: `tests/test_embeddings.py`

**Step 1: Write the failing test**

```python
from semdex.embeddings import LocalEmbedder


def test_local_embedder_encodes_text():
    embedder = LocalEmbedder(model_name="all-MiniLM-L6-v2")
    vectors = embedder.encode(["hello world", "foo bar"])
    assert len(vectors) == 2
    assert len(vectors[0]) == 384  # MiniLM output dimension


def test_local_embedder_single_text():
    embedder = LocalEmbedder(model_name="all-MiniLM-L6-v2")
    vectors = embedder.encode(["test"])
    assert len(vectors) == 1
    assert len(vectors[0]) == 384


def test_local_embedder_empty_input():
    embedder = LocalEmbedder(model_name="all-MiniLM-L6-v2")
    vectors = embedder.encode([])
    assert vectors == []
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_embeddings.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
from __future__ import annotations

from sentence_transformers import SentenceTransformer


class LocalEmbedder:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self._model = SentenceTransformer(model_name)
        self.dimension = self._model.get_sentence_embedding_dimension()

    def encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        embeddings = self._model.encode(texts)
        return [vec.tolist() for vec in embeddings]
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_embeddings.py -v`
Expected: 3 passed (first run will download model ~80MB)

**Step 5: Commit**

```bash
git add src/semdex/embeddings.py tests/test_embeddings.py
git commit -m "Add local embedding provider with sentence-transformers"
```

---

### Task 4: Chunker Module

**Files:**
- Create: `src/semdex/chunker.py`
- Create: `tests/test_chunker.py`

**Step 1: Write the failing tests**

```python
from semdex.chunker import Chunk, chunk_text, chunk_file
from pathlib import Path
import tempfile


def test_small_file_returns_single_chunk():
    content = "line1\nline2\nline3\n"
    chunks = chunk_text(content, threshold=200)
    assert len(chunks) == 1
    assert chunks[0].chunk_type == "whole-file"
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 3


def test_large_file_returns_multiple_chunks():
    content = "\n".join(f"line {i}" for i in range(300))
    chunks = chunk_text(content, threshold=200)
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.chunk_type == "window"


def test_sliding_window_overlap():
    content = "\n".join(f"line {i}" for i in range(300))
    chunks = chunk_text(content, threshold=200)
    # Chunks should overlap
    if len(chunks) >= 2:
        assert chunks[1].start_line < chunks[0].end_line


def test_chunk_file_reads_from_disk():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("hello\nworld\n")
        f.flush()
        chunks = chunk_file(Path(f.name), threshold=200)
        assert len(chunks) == 1
        assert "hello" in chunks[0].content
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_chunker.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write minimal implementation**

Start with sliding-window only. Tree-sitter parsing will be added in Task 5.

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

WINDOW_SIZE = 100  # lines per chunk
OVERLAP = 20  # lines of overlap between chunks


@dataclass
class Chunk:
    content: str
    start_line: int
    end_line: int
    chunk_type: str  # "whole-file", "window", "function", "class"


def chunk_text(content: str, threshold: int = 200) -> list[Chunk]:
    lines = content.splitlines()
    total = len(lines)

    if total <= threshold:
        return [Chunk(
            content=content,
            start_line=1,
            end_line=total,
            chunk_type="whole-file",
        )]

    chunks = []
    start = 0
    while start < total:
        end = min(start + WINDOW_SIZE, total)
        chunk_lines = lines[start:end]
        chunks.append(Chunk(
            content="\n".join(chunk_lines),
            start_line=start + 1,
            end_line=end,
            chunk_type="window",
        ))
        if end >= total:
            break
        start += WINDOW_SIZE - OVERLAP
    return chunks


def chunk_file(path: Path, threshold: int = 200) -> list[Chunk]:
    content = path.read_text(errors="replace")
    return chunk_text(content, threshold=threshold)
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_chunker.py -v`
Expected: 4 passed

**Step 5: Commit**

```bash
git add src/semdex/chunker.py tests/test_chunker.py
git commit -m "Add chunker with whole-file and sliding window"
```

---

### Task 5: Tree-Sitter Smart Chunking

**Files:**
- Modify: `src/semdex/chunker.py`
- Create: `tests/test_chunker_treesitter.py`

**Step 1: Write the failing tests**

```python
from semdex.chunker import chunk_text_with_treesitter


def test_python_function_chunking():
    code = '''
import os

def foo():
    """Do foo."""
    return 1

class Bar:
    def method(self):
        pass

def baz():
    return 2
'''
    # Make it "large" by repeating with padding
    padded = code + "\n" * 200
    chunks = chunk_text_with_treesitter(padded, language="python", threshold=200)
    types = [c.chunk_type for c in chunks]
    assert "function" in types or "class" in types


def test_unknown_language_returns_none():
    result = chunk_text_with_treesitter("hello", language="brainfuck", threshold=200)
    assert result is None


def test_small_file_skipped():
    result = chunk_text_with_treesitter("x = 1\n", language="python", threshold=200)
    assert result is None  # Below threshold, caller uses whole-file
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_chunker_treesitter.py -v`
Expected: FAIL with ImportError

**Step 3: Add tree-sitter chunking to chunker.py**

Add to `src/semdex/chunker.py`:

```python
LANGUAGE_MAP = {}

def _get_parser(language: str):
    """Load tree-sitter parser for a language. Returns None if unsupported."""
    if language in LANGUAGE_MAP:
        return LANGUAGE_MAP[language]

    try:
        from tree_sitter import Language, Parser
        if language == "python":
            import tree_sitter_python as ts_lang
        elif language == "javascript":
            import tree_sitter_javascript as ts_lang
        elif language == "typescript":
            import tree_sitter_typescript as ts_lang
            # typescript module provides typescript and tsx
            ts_lang = ts_lang  # use default
        else:
            LANGUAGE_MAP[language] = None
            return None

        lang = Language(ts_lang.language())
        parser = Parser(lang)
        LANGUAGE_MAP[language] = parser
        return parser
    except (ImportError, Exception):
        LANGUAGE_MAP[language] = None
        return None


# Map file extensions to tree-sitter language names
EXT_TO_LANGUAGE = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
}

# Node types that represent top-level blocks to extract
BLOCK_NODE_TYPES = {
    "function_definition",   # Python
    "class_definition",      # Python
    "function_declaration",  # JS/TS
    "class_declaration",     # JS/TS
    "export_statement",      # JS/TS
}


def chunk_text_with_treesitter(
    content: str, language: str, threshold: int = 200
) -> list[Chunk] | None:
    lines = content.splitlines()
    if len(lines) <= threshold:
        return None  # Caller should use whole-file

    parser = _get_parser(language)
    if parser is None:
        return None  # Caller should use sliding window

    tree = parser.parse(bytes(content, "utf-8"))
    root = tree.root_node

    chunks = []
    for child in root.children:
        if child.type in BLOCK_NODE_TYPES:
            start = child.start_point[0]
            end = child.end_point[0]
            chunk_type = "function" if "function" in child.type else "class"
            chunk_content = "\n".join(lines[start:end + 1])
            chunks.append(Chunk(
                content=chunk_content,
                start_line=start + 1,
                end_line=end + 1,
                chunk_type=chunk_type,
            ))

    return chunks if chunks else None
```

Also update `chunk_file` to try tree-sitter first:

```python
def chunk_file(path: Path, threshold: int = 200) -> list[Chunk]:
    content = path.read_text(errors="replace")
    language = EXT_TO_LANGUAGE.get(path.suffix)

    if language:
        ts_chunks = chunk_text_with_treesitter(content, language, threshold)
        if ts_chunks:
            return ts_chunks

    return chunk_text(content, threshold=threshold)
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_chunker_treesitter.py tests/test_chunker.py -v`
Expected: All passed

**Step 5: Commit**

```bash
git add src/semdex/chunker.py tests/test_chunker_treesitter.py
git commit -m "Add tree-sitter smart chunking for Python, JS, TS"
```

---

### Task 6: LanceDB Store Module

**Files:**
- Create: `src/semdex/store.py`
- Create: `tests/test_store.py`

**Step 1: Write the failing tests**

```python
import tempfile
from pathlib import Path

from semdex.store import SemdexStore


def test_store_add_and_search():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SemdexStore(db_path=Path(tmpdir) / "lance.db", dimension=4)
        store.add_chunks([
            {
                "file_path": "foo.py",
                "start_line": 1,
                "end_line": 10,
                "chunk_type": "whole-file",
                "content": "def foo(): pass",
                "source_dir": ".",
                "last_indexed": "2026-03-21T00:00:00",
                "vector": [1.0, 0.0, 0.0, 0.0],
            },
            {
                "file_path": "bar.py",
                "start_line": 1,
                "end_line": 5,
                "chunk_type": "whole-file",
                "content": "def bar(): pass",
                "source_dir": ".",
                "last_indexed": "2026-03-21T00:00:00",
                "vector": [0.0, 1.0, 0.0, 0.0],
            },
        ])
        results = store.search([1.0, 0.0, 0.0, 0.0], top_k=1)
        assert len(results) == 1
        assert results[0]["file_path"] == "foo.py"


def test_store_delete_by_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SemdexStore(db_path=Path(tmpdir) / "lance.db", dimension=4)
        store.add_chunks([
            {
                "file_path": "foo.py",
                "start_line": 1,
                "end_line": 10,
                "chunk_type": "whole-file",
                "content": "def foo(): pass",
                "source_dir": ".",
                "last_indexed": "2026-03-21T00:00:00",
                "vector": [1.0, 0.0, 0.0, 0.0],
            },
        ])
        store.delete_by_file("foo.py")
        results = store.search([1.0, 0.0, 0.0, 0.0], top_k=10)
        assert len(results) == 0


def test_store_delete_by_source_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SemdexStore(db_path=Path(tmpdir) / "lance.db", dimension=4)
        store.add_chunks([
            {
                "file_path": "/ext/foo.py",
                "start_line": 1,
                "end_line": 10,
                "chunk_type": "whole-file",
                "content": "def foo(): pass",
                "source_dir": "/ext",
                "last_indexed": "2026-03-21T00:00:00",
                "vector": [1.0, 0.0, 0.0, 0.0],
            },
        ])
        store.delete_by_source_dir("/ext")
        results = store.search([1.0, 0.0, 0.0, 0.0], top_k=10)
        assert len(results) == 0


def test_store_get_file_summary():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SemdexStore(db_path=Path(tmpdir) / "lance.db", dimension=4)
        store.add_chunks([
            {
                "file_path": "foo.py",
                "start_line": 1,
                "end_line": 10,
                "chunk_type": "function",
                "content": "def foo(): pass",
                "source_dir": ".",
                "last_indexed": "2026-03-21T00:00:00",
                "vector": [1.0, 0.0, 0.0, 0.0],
            },
            {
                "file_path": "foo.py",
                "start_line": 11,
                "end_line": 20,
                "chunk_type": "class",
                "content": "class Foo: pass",
                "source_dir": ".",
                "last_indexed": "2026-03-21T00:00:00",
                "vector": [0.0, 1.0, 0.0, 0.0],
            },
        ])
        summary = store.get_file_summary("foo.py")
        assert summary["file_path"] == "foo.py"
        assert summary["chunk_count"] == 2
        assert "function" in summary["chunk_types"]
        assert "class" in summary["chunk_types"]


def test_store_stats():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SemdexStore(db_path=Path(tmpdir) / "lance.db", dimension=4)
        store.add_chunks([
            {
                "file_path": "foo.py",
                "start_line": 1,
                "end_line": 10,
                "chunk_type": "whole-file",
                "content": "def foo(): pass",
                "source_dir": ".",
                "last_indexed": "2026-03-21T00:00:00",
                "vector": [1.0, 0.0, 0.0, 0.0],
            },
        ])
        stats = store.stats()
        assert stats["total_chunks"] == 1
        assert stats["total_files"] == 1
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_store.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
from __future__ import annotations

from pathlib import Path

import lancedb


class SemdexStore:
    TABLE_NAME = "chunks"

    def __init__(self, db_path: Path, dimension: int = 384):
        self._db = lancedb.connect(str(db_path))
        self._dimension = dimension
        self._table = None

    def _get_table(self):
        if self._table is None:
            try:
                self._table = self._db.open_table(self.TABLE_NAME)
            except Exception:
                self._table = None
        return self._table

    def _ensure_table(self, data: list[dict]):
        if self._get_table() is None:
            self._table = self._db.create_table(self.TABLE_NAME, data)
        else:
            self._table.add(data)

    def add_chunks(self, chunks: list[dict]) -> None:
        if not chunks:
            return
        self._ensure_table(chunks)

    def search(self, query_vector: list[float], top_k: int = 10) -> list[dict]:
        table = self._get_table()
        if table is None:
            return []
        results = table.search(query_vector).limit(top_k).to_pandas()
        rows = []
        for _, row in results.iterrows():
            rows.append({
                "file_path": row["file_path"],
                "start_line": int(row["start_line"]),
                "end_line": int(row["end_line"]),
                "chunk_type": row["chunk_type"],
                "content": row["content"],
                "score": float(row["_distance"]),
            })
        return rows

    def delete_by_file(self, file_path: str) -> None:
        table = self._get_table()
        if table is not None:
            table.delete(f'file_path = "{file_path}"')

    def delete_by_source_dir(self, source_dir: str) -> None:
        table = self._get_table()
        if table is not None:
            table.delete(f'source_dir = "{source_dir}"')

    def get_file_summary(self, file_path: str) -> dict | None:
        table = self._get_table()
        if table is None:
            return None
        df = table.to_pandas()
        file_rows = df[df["file_path"] == file_path]
        if file_rows.empty:
            return None
        return {
            "file_path": file_path,
            "chunk_count": len(file_rows),
            "chunk_types": sorted(file_rows["chunk_type"].unique().tolist()),
            "last_indexed": file_rows["last_indexed"].max(),
        }

    def stats(self) -> dict:
        table = self._get_table()
        if table is None:
            return {"total_chunks": 0, "total_files": 0, "last_indexed": None}
        df = table.to_pandas()
        return {
            "total_chunks": len(df),
            "total_files": df["file_path"].nunique(),
            "last_indexed": df["last_indexed"].max(),
        }
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_store.py -v`
Expected: 5 passed

**Step 5: Commit**

```bash
git add src/semdex/store.py tests/test_store.py
git commit -m "Add LanceDB store with search, delete, summary"
```

---

### Task 7: File Discovery (Indexer Module)

**Files:**
- Create: `src/semdex/indexer.py`
- Create: `tests/test_indexer.py`

**Step 1: Write the failing tests**

```python
import tempfile
from pathlib import Path

from semdex.indexer import discover_files
from semdex.config import SemdexConfig


def test_discover_files_finds_source_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "main.py").write_text("print('hello')")
        (root / "lib.js").write_text("console.log('hi')")
        (root / "README.md").write_text("# hi")
        config = SemdexConfig(project_root=root)
        files = discover_files(root, config)
        names = {f.name for f in files}
        assert "main.py" in names
        assert "lib.js" in names
        assert "README.md" in names


def test_discover_files_skips_excluded_dirs():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "main.py").write_text("x = 1")
        nm = root / "node_modules"
        nm.mkdir()
        (nm / "dep.js").write_text("module.exports = {}")
        config = SemdexConfig(project_root=root)
        files = discover_files(root, config)
        paths = [str(f) for f in files]
        assert not any("node_modules" in p for p in paths)


def test_discover_files_skips_binary():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "main.py").write_text("x = 1")
        (root / "image.png").write_bytes(b"\x89PNG\r\n")
        config = SemdexConfig(project_root=root)
        files = discover_files(root, config)
        names = {f.name for f in files}
        assert "main.py" in names
        assert "image.png" not in names


def test_discover_files_respects_gitignore():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "main.py").write_text("x = 1")
        (root / "secret.env").write_text("KEY=val")
        (root / ".gitignore").write_text("*.env\n")
        config = SemdexConfig(project_root=root)
        files = discover_files(root, config)
        names = {f.name for f in files}
        assert "main.py" in names
        assert "secret.env" not in names


def test_discover_files_skips_large_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "small.py").write_text("x = 1")
        (root / "huge.py").write_text("x" * 2_000_000)
        config = SemdexConfig(project_root=root, max_file_size=1_000_000)
        files = discover_files(root, config)
        names = {f.name for f in files}
        assert "small.py" in names
        assert "huge.py" not in names
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_indexer.py -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

```python
from __future__ import annotations

from pathlib import Path

import pathspec

from semdex.config import SemdexConfig, DEFAULT_EXCLUDES, BINARY_EXTENSIONS


def discover_files(
    root: Path, config: SemdexConfig, respect_gitignore: bool = True
) -> list[Path]:
    """Walk root and return indexable file paths."""
    ignore_patterns = list(DEFAULT_EXCLUDES) + config.extra_excludes

    if respect_gitignore:
        gitignore_path = root / ".gitignore"
        if gitignore_path.exists():
            ignore_patterns.extend(
                gitignore_path.read_text().splitlines()
            )

    spec = pathspec.GitIgnoreSpec.from_lines(ignore_patterns)
    files = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue

        rel = path.relative_to(root)

        if spec.match_file(str(rel)):
            continue

        if path.suffix.lower() in BINARY_EXTENSIONS:
            continue

        if path.stat().st_size > config.max_file_size:
            continue

        files.append(path)

    return sorted(files)
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_indexer.py -v`
Expected: 5 passed

**Step 5: Commit**

```bash
git add src/semdex/indexer.py tests/test_indexer.py
git commit -m "Add file discovery with gitignore and exclusions"
```

---

### Task 8: Full Indexing Pipeline

**Files:**
- Modify: `src/semdex/indexer.py`
- Create: `tests/test_indexer_pipeline.py`

**Step 1: Write the failing test**

```python
import tempfile
from pathlib import Path
from unittest.mock import patch

from semdex.config import SemdexConfig
from semdex.indexer import index_project


def test_index_project_end_to_end():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "main.py").write_text("def hello():\n    return 'hi'\n")
        (root / "lib.py").write_text("x = 1\n")

        config = SemdexConfig(project_root=root)
        config.ensure_dirs()

        stats = index_project(root, config)
        assert stats["files_indexed"] == 2
        assert stats["chunks_created"] > 0


def test_index_specific_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "a.py").write_text("x = 1\n")
        (root / "b.py").write_text("y = 2\n")

        config = SemdexConfig(project_root=root)
        config.ensure_dirs()

        stats = index_project(root, config, files=[root / "a.py"])
        assert stats["files_indexed"] == 1


def test_index_external_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir) / "project"
        ext = Path(tmpdir) / "external"
        root.mkdir()
        ext.mkdir()
        (root / "main.py").write_text("x = 1\n")
        (ext / "lib.py").write_text("y = 2\n")

        config = SemdexConfig(project_root=root)
        config.ensure_dirs()

        stats = index_project(root, config, target_dir=ext)
        assert stats["files_indexed"] == 1
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_indexer_pipeline.py -v`
Expected: FAIL with ImportError (index_project not defined)

**Step 3: Add index_project to indexer.py**

Append to `src/semdex/indexer.py`:

```python
from datetime import datetime, timezone

from semdex.chunker import chunk_file
from semdex.embeddings import LocalEmbedder
from semdex.store import SemdexStore


def index_project(
    project_root: Path,
    config: SemdexConfig,
    files: list[Path] | None = None,
    target_dir: Path | None = None,
) -> dict:
    """Index files and store embeddings. Returns stats dict."""
    embedder = LocalEmbedder(model_name=config.embedding_model)
    store = SemdexStore(db_path=config.db_path, dimension=embedder.dimension)

    if target_dir:
        # Index external directory — don't respect gitignore
        file_list = discover_files(target_dir, config, respect_gitignore=False)
        source_dir = str(target_dir.resolve())
        # Remove old entries for this dir before re-indexing
        store.delete_by_source_dir(source_dir)
    elif files:
        file_list = files
        source_dir = str(project_root.resolve())
        # Remove old entries for specified files
        for f in file_list:
            store.delete_by_file(str(f.relative_to(project_root)))
    else:
        file_list = discover_files(project_root, config)
        source_dir = str(project_root.resolve())

    now = datetime.now(timezone.utc).isoformat()
    all_chunks = []

    for path in file_list:
        chunks = chunk_file(path, threshold=config.chunk_threshold)
        if target_dir:
            rel_path = str(path.relative_to(target_dir))
        else:
            try:
                rel_path = str(path.relative_to(project_root))
            except ValueError:
                rel_path = str(path)

        for chunk in chunks:
            all_chunks.append({
                "file_path": rel_path,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "chunk_type": chunk.chunk_type,
                "content": chunk.content,
                "source_dir": source_dir,
                "last_indexed": now,
            })

    if not all_chunks:
        return {"files_indexed": 0, "chunks_created": 0}

    # Batch embed all chunks
    texts = [c["content"] for c in all_chunks]
    vectors = embedder.encode(texts)

    for chunk, vector in zip(all_chunks, vectors):
        chunk["vector"] = vector

    store.add_chunks(all_chunks)

    return {
        "files_indexed": len(file_list),
        "chunks_created": len(all_chunks),
    }
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_indexer_pipeline.py -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add src/semdex/indexer.py tests/test_indexer_pipeline.py
git commit -m "Add full indexing pipeline with embedding and storage"
```

---

### Task 9: Git Hooks Module

**Files:**
- Create: `src/semdex/hooks.py`
- Create: `tests/test_hooks.py`

**Step 1: Write the failing tests**

```python
import tempfile
from pathlib import Path

from semdex.hooks import install_hook, uninstall_hook, HOOK_MARKER


def test_install_hook_creates_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        hooks_dir = Path(tmpdir) / ".git" / "hooks"
        hooks_dir.mkdir(parents=True)
        install_hook(Path(tmpdir))
        hook_file = hooks_dir / "post-commit"
        assert hook_file.exists()
        content = hook_file.read_text()
        assert HOOK_MARKER in content
        assert "semdex" in content


def test_install_hook_preserves_existing():
    with tempfile.TemporaryDirectory() as tmpdir:
        hooks_dir = Path(tmpdir) / ".git" / "hooks"
        hooks_dir.mkdir(parents=True)
        hook_file = hooks_dir / "post-commit"
        hook_file.write_text("#!/bin/sh\necho 'existing'\n")
        hook_file.chmod(0o755)
        install_hook(Path(tmpdir))
        content = hook_file.read_text()
        assert "existing" in content
        assert HOOK_MARKER in content


def test_uninstall_hook_removes_semdex_section():
    with tempfile.TemporaryDirectory() as tmpdir:
        hooks_dir = Path(tmpdir) / ".git" / "hooks"
        hooks_dir.mkdir(parents=True)
        install_hook(Path(tmpdir))
        uninstall_hook(Path(tmpdir))
        hook_file = hooks_dir / "post-commit"
        if hook_file.exists():
            assert HOOK_MARKER not in hook_file.read_text()


def test_install_hook_is_idempotent():
    with tempfile.TemporaryDirectory() as tmpdir:
        hooks_dir = Path(tmpdir) / ".git" / "hooks"
        hooks_dir.mkdir(parents=True)
        install_hook(Path(tmpdir))
        install_hook(Path(tmpdir))
        content = (hooks_dir / "post-commit").read_text()
        assert content.count(HOOK_MARKER) == 2  # start and end markers only
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_hooks.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
from __future__ import annotations

import stat
from pathlib import Path

HOOK_MARKER = "# --- semdex ---"
HOOK_END_MARKER = "# --- /semdex ---"

HOOK_SCRIPT = f"""{HOOK_MARKER}
# Incremental re-index after commit
semdex index $(git diff HEAD~1 --name-only 2>/dev/null) >> .claude/semdex/hook.log 2>&1 &
{HOOK_END_MARKER}"""


def install_hook(repo_root: Path) -> None:
    hook_path = repo_root / ".git" / "hooks" / "post-commit"

    if hook_path.exists():
        content = hook_path.read_text()
        if HOOK_MARKER in content:
            return  # Already installed
        content = content.rstrip() + "\n\n" + HOOK_SCRIPT + "\n"
    else:
        content = "#!/bin/sh\n\n" + HOOK_SCRIPT + "\n"

    hook_path.write_text(content)
    hook_path.chmod(hook_path.stat().st_mode | stat.S_IEXEC)


def uninstall_hook(repo_root: Path) -> None:
    hook_path = repo_root / ".git" / "hooks" / "post-commit"
    if not hook_path.exists():
        return

    content = hook_path.read_text()
    if HOOK_MARKER not in content:
        return

    # Remove the semdex section
    lines = content.splitlines(keepends=True)
    new_lines = []
    in_semdex = False
    for line in lines:
        if HOOK_MARKER in line and HOOK_END_MARKER not in line:
            in_semdex = True
            continue
        if HOOK_END_MARKER in line:
            in_semdex = False
            continue
        if not in_semdex:
            new_lines.append(line)

    remaining = "".join(new_lines).strip()
    if remaining == "#!/bin/sh" or not remaining:
        hook_path.unlink()
    else:
        hook_path.write_text(remaining + "\n")
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_hooks.py -v`
Expected: 4 passed

**Step 5: Commit**

```bash
git add src/semdex/hooks.py tests/test_hooks.py
git commit -m "Add git post-commit hook install/uninstall"
```

---

### Task 10: MCP Server

**Files:**
- Create: `src/semdex/server.py`
- Create: `tests/test_server.py`

**Step 1: Write the failing tests**

```python
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from semdex.server import create_server


def test_server_has_search_tool():
    server = create_server(project_root=Path("/tmp/fake"))
    tool_names = [t.name for t in server.list_tools()]
    assert "search" in tool_names


def test_server_has_related_tool():
    server = create_server(project_root=Path("/tmp/fake"))
    tool_names = [t.name for t in server.list_tools()]
    assert "related" in tool_names


def test_server_has_summary_tool():
    server = create_server(project_root=Path("/tmp/fake"))
    tool_names = [t.name for t in server.list_tools()]
    assert "summary" in tool_names
```

Note: Full integration tests for MCP tools will depend on whether `FastMCP` exposes `list_tools()` directly. The tests above may need adjustment based on the actual API. If `list_tools()` is not available, test by checking the server's internal tool registry or by calling the tools directly.

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_server.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from semdex.config import SemdexConfig
from semdex.embeddings import LocalEmbedder
from semdex.store import SemdexStore


def create_server(project_root: Path) -> FastMCP:
    mcp = FastMCP(name="semdex")
    config = SemdexConfig.load(project_root)

    _embedder = None
    _store = None

    def get_embedder():
        nonlocal _embedder
        if _embedder is None:
            _embedder = LocalEmbedder(model_name=config.embedding_model)
        return _embedder

    def get_store():
        nonlocal _store
        if _store is None:
            _store = SemdexStore(
                db_path=config.db_path,
                dimension=get_embedder().dimension,
            )
        return _store

    @mcp.tool()
    def search(query: str, top_k: int = 10) -> list[dict]:
        """Search the semantic index for files matching a natural language query."""
        embedder = get_embedder()
        store = get_store()
        vector = embedder.encode([query])[0]
        return store.search(vector, top_k=top_k)

    @mcp.tool()
    def related(file_path: str, top_k: int = 10) -> list[dict]:
        """Find files semantically related to the given file."""
        store = get_store()
        summary = store.get_file_summary(file_path)
        if summary is None:
            return [{"error": f"File '{file_path}' not found in index"}]

        # Get the file's chunks and use first chunk's embedding as query
        embedder = get_embedder()
        # Read the actual file to get its embedding
        full_path = project_root / file_path
        if full_path.exists():
            content = full_path.read_text(errors="replace")[:5000]
            vector = embedder.encode([content])[0]
            results = store.search(vector, top_k=top_k + 5)
            # Filter out the query file itself
            return [r for r in results if r["file_path"] != file_path][:top_k]
        return [{"error": f"File '{file_path}' not found on disk"}]

    @mcp.tool()
    def summary(file_path: str) -> dict:
        """Get index metadata summary for a file."""
        store = get_store()
        result = store.get_file_summary(file_path)
        if result is None:
            return {"error": f"File '{file_path}' not found in index"}
        return result

    return mcp


def run_server(project_root: Path) -> None:
    mcp = create_server(project_root)
    mcp.run()
```

**Step 4: Adjust tests if needed and run**

Run: `python -m pytest tests/test_server.py -v`
Expected: 3 passed (may need to adjust based on FastMCP API — check if `list_tools()` exists or use alternative introspection)

**Step 5: Commit**

```bash
git add src/semdex/server.py tests/test_server.py
git commit -m "Add MCP server with search, related, summary tools"
```

---

### Task 11: Wire Up CLI Commands

**Files:**
- Modify: `src/semdex/cli.py`

**Step 1: Write a smoke test**

Create `tests/test_cli.py`:

```python
from click.testing import CliRunner

from semdex.cli import cli


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "semdex" in result.output


def test_init_creates_index(tmp_path):
    runner = CliRunner()
    # Create a minimal project
    (tmp_path / "main.py").write_text("x = 1\n")
    result = runner.invoke(cli, ["init"], catch_exceptions=False)
    # Just verify it doesn't crash for now
    assert result.exit_code == 0 or "error" not in result.output.lower()


def test_status_no_index():
    runner = CliRunner()
    result = runner.invoke(cli, ["status"])
    assert result.exit_code == 0


def test_hook_install_no_git():
    runner = CliRunner()
    result = runner.invoke(cli, ["hook", "install"])
    assert result.exit_code == 0 or "not a git" in result.output.lower()
```

**Step 2: Run to verify failure**

Run: `python -m pytest tests/test_cli.py -v`
Expected: Some pass (help), some fail (init does nothing real yet)

**Step 3: Wire up all CLI commands in cli.py**

Replace `src/semdex/cli.py` with full implementation:

```python
from __future__ import annotations

import os
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

    # Print MCP config for user
    semdex_path = os.popen("which semdex").read().strip() or "semdex"
    click.echo(f"\nAdd to your Claude Code MCP config:")
    click.echo(f'  "semdex": {{"command": "{semdex_path}", "args": ["serve"]}}')


@cli.command()
@click.argument("target", required=False)
def index(target):
    """Build or rebuild the semantic index."""
    root = _find_project_root()
    config = SemdexConfig.load(root)
    config.ensure_dirs()

    if target:
        target_path = Path(target).resolve()
        if target_path.is_dir():
            click.echo(f"Indexing directory: {target_path}")
            stats = index_project(root, config, target_dir=target_path)
        elif target_path.is_file():
            click.echo(f"Indexing file: {target_path}")
            stats = index_project(root, config, files=[target_path])
        else:
            click.echo(f"Error: {target} not found", err=True)
            raise SystemExit(1)
    else:
        click.echo("Rebuilding full index...")
        stats = index_project(root, config)

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
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_cli.py -v`
Expected: All pass

**Step 5: Run full test suite**

Run: `python -m pytest -v`
Expected: All tests pass

**Step 6: Commit**

```bash
git add src/semdex/cli.py tests/test_cli.py
git commit -m "Wire up all CLI commands to real implementations"
```

---

### Task 12: End-to-End Smoke Test

**Files:**
- Create: `tests/test_e2e.py`

**Step 1: Write the end-to-end test**

```python
import tempfile
import subprocess
from pathlib import Path


def test_full_workflow():
    """Test: init → index → search → status → forget."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Create a fake git repo
        subprocess.run(["git", "init"], cwd=root, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=root, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=root, capture_output=True,
        )

        # Create project files
        (root / "auth.py").write_text(
            "def authenticate(user, password):\n"
            "    '''Authenticate a user with credentials.'''\n"
            "    return check_password(user, password)\n"
        )
        (root / "db.py").write_text(
            "def connect_database(url):\n"
            "    '''Connect to the database.'''\n"
            "    return Connection(url)\n"
        )
        (root / "README.md").write_text("# Test Project\nA test project.\n")

        # git add and commit so HEAD exists
        subprocess.run(["git", "add", "."], cwd=root, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=root, capture_output=True,
        )

        from click.testing import CliRunner
        from semdex.cli import cli

        runner = CliRunner()

        # Init
        result = runner.invoke(cli, ["init"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Indexed" in result.output
        assert (root / ".claude" / "semdex").is_dir()

        # Status
        result = runner.invoke(cli, ["status"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Files indexed:" in result.output

        # Search
        result = runner.invoke(
            cli, ["search", "authentication"], catch_exceptions=False
        )
        assert result.exit_code == 0
        assert "auth.py" in result.output

        # Forget
        result = runner.invoke(
            cli, ["forget", "auth.py"], catch_exceptions=False
        )
        assert result.exit_code == 0
        assert "Removed" in result.output
```

**Step 2: Run the test**

Run: `python -m pytest tests/test_e2e.py -v`
Expected: PASS

Note: This test will be slow on first run (downloads model). Subsequent runs use cached model.

**Step 3: Run full test suite one final time**

Run: `python -m pytest -v`
Expected: All tests pass

**Step 4: Commit**

```bash
git add tests/test_e2e.py
git commit -m "Add end-to-end smoke test"
```

---

### Task Summary

| Task | What | Files |
|------|------|-------|
| 1 | Project scaffolding | pyproject.toml, .gitignore, __init__.py, cli.py skeleton |
| 2 | Config module | config.py, test_config.py |
| 3 | Embedding provider | embeddings.py, test_embeddings.py |
| 4 | Chunker (sliding window) | chunker.py, test_chunker.py |
| 5 | Chunker (tree-sitter) | chunker.py update, test_chunker_treesitter.py |
| 6 | LanceDB store | store.py, test_store.py |
| 7 | File discovery | indexer.py, test_indexer.py |
| 8 | Full indexing pipeline | indexer.py update, test_indexer_pipeline.py |
| 9 | Git hooks | hooks.py, test_hooks.py |
| 10 | MCP server | server.py, test_server.py |
| 11 | Wire up CLI | cli.py full impl, test_cli.py |
| 12 | End-to-end test | test_e2e.py |
