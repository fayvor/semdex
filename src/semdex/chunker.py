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


def chunk_file(path: Path, threshold: int = 200) -> list[Chunk]:
    content = path.read_text(errors="replace")
    language = EXT_TO_LANGUAGE.get(path.suffix)

    if language:
        ts_chunks = chunk_text_with_treesitter(content, language, threshold)
        if ts_chunks:
            return ts_chunks

    return chunk_text(content, threshold=threshold)
