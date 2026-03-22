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
        arrow_table = table.search(query_vector).limit(top_k).to_arrow()
        rows = []
        for i in range(arrow_table.num_rows):
            rows.append({
                "file_path": arrow_table.column("file_path")[i].as_py(),
                "start_line": int(arrow_table.column("start_line")[i].as_py()),
                "end_line": int(arrow_table.column("end_line")[i].as_py()),
                "chunk_type": arrow_table.column("chunk_type")[i].as_py(),
                "content": arrow_table.column("content")[i].as_py(),
                "score": float(arrow_table.column("_distance")[i].as_py()),
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
        arrow_table = table.to_arrow()
        col = arrow_table.column("file_path").to_pylist()
        indices = [i for i, v in enumerate(col) if v == file_path]
        if not indices:
            return None
        chunk_types = list({arrow_table.column("chunk_type")[i].as_py() for i in indices})
        last_indexed = max(arrow_table.column("last_indexed")[i].as_py() for i in indices)
        return {
            "file_path": file_path,
            "chunk_count": len(indices),
            "chunk_types": sorted(chunk_types),
            "last_indexed": last_indexed,
        }

    def stats(self) -> dict:
        table = self._get_table()
        if table is None:
            return {"total_chunks": 0, "total_files": 0, "last_indexed": None}
        arrow_table = table.to_arrow()
        total_chunks = arrow_table.num_rows
        file_paths = set(arrow_table.column("file_path").to_pylist())
        last_indexed_list = arrow_table.column("last_indexed").to_pylist()
        last_indexed = max(last_indexed_list) if last_indexed_list else None
        return {
            "total_chunks": total_chunks,
            "total_files": len(file_paths),
            "last_indexed": last_indexed,
        }
