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
