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
