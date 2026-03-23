from semdex.embeddings import LocalEmbedder


def test_local_embedder_encodes_text():
    embedder = LocalEmbedder(model_name="sentence-transformers/all-MiniLM-L6-v2")
    vectors = embedder.encode(["hello world", "foo bar"])
    assert len(vectors) == 2
    assert len(vectors[0]) == 384  # MiniLM output dimension


def test_local_embedder_single_text():
    embedder = LocalEmbedder(model_name="sentence-transformers/all-MiniLM-L6-v2")
    vectors = embedder.encode(["test"])
    assert len(vectors) == 1
    assert len(vectors[0]) == 384


def test_local_embedder_empty_input():
    embedder = LocalEmbedder(model_name="sentence-transformers/all-MiniLM-L6-v2")
    vectors = embedder.encode([])
    assert vectors == []
