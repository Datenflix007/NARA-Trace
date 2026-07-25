from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from platformdirs import user_data_path

from naratrace.core.config import get_settings

SUBDIRECTORIES = (
    "database",
    "cache",
    "documents",
    "thumbnails",
    "ocr",
    "exports",
    "logs",
    "temp",
)


@dataclass(frozen=True)
class LocalPaths:
    root: Path
    database_dir: Path
    cache_dir: Path
    documents_dir: Path
    thumbnails_dir: Path
    ocr_dir: Path
    exports_dir: Path
    logs_dir: Path
    temp_dir: Path

    @property
    def database_file(self) -> Path:
        return self.database_dir / "naratrace.sqlite3"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_file.as_posix()}"

    def as_dict(self) -> dict[str, str]:
        return {
            "root": str(self.root),
            "database": str(self.database_dir),
            "cache": str(self.cache_dir),
            "documents": str(self.documents_dir),
            "thumbnails": str(self.thumbnails_dir),
            "ocr": str(self.ocr_dir),
            "exports": str(self.exports_dir),
            "logs": str(self.logs_dir),
            "temp": str(self.temp_dir),
        }


@lru_cache(maxsize=1)
def get_local_paths() -> LocalPaths:
    root = get_data_root()
    return LocalPaths(
        root=root,
        database_dir=root / "database",
        cache_dir=root / "cache",
        documents_dir=root / "documents",
        thumbnails_dir=root / "thumbnails",
        ocr_dir=root / "ocr",
        exports_dir=root / "exports",
        logs_dir=root / "logs",
        temp_dir=root / "temp",
    )


def get_data_root() -> Path:
    settings = get_settings()
    if settings.data_dir:
        return Path(settings.data_dir).expanduser().resolve()
    return user_data_path("NARATrace", appauthor=False, roaming=False)


def ensure_local_directories(paths: LocalPaths | None = None) -> LocalPaths:
    paths = paths or get_local_paths()
    paths.root.mkdir(parents=True, exist_ok=True)
    for directory_name in SUBDIRECTORIES:
        getattr(paths, f"{directory_name}_dir").mkdir(parents=True, exist_ok=True)
    return paths


def get_default_database_url() -> str:
    return get_local_paths().database_url


def reset_paths_cache() -> None:
    get_local_paths.cache_clear()
