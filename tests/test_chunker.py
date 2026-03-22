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
