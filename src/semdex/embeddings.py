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
