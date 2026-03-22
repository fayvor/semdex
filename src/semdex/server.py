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
