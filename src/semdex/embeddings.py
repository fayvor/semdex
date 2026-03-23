from __future__ import annotations

from fastembed import TextEmbedding


class LocalEmbedder:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self._model = TextEmbedding(model_name=model_name)
        # all-MiniLM-L6-v2 produces 384-dimensional embeddings
        self.dimension = 384

    def encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        embeddings = list(self._model.embed(texts))
        return [vec.tolist() for vec in embeddings]
