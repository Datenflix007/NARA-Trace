from __future__ import annotations

from naratrace.core.config import reset_settings_cache
from naratrace.core.paths import SUBDIRECTORIES, ensure_local_directories, get_local_paths, reset_paths_cache


def test_local_data_directories_are_created_outside_repo(tmp_path, monkeypatch):
    data_dir = tmp_path / "local-data"
    monkeypatch.setenv("NARATRACE_DATA_DIR", str(data_dir))
    reset_settings_cache()
    reset_paths_cache()

    paths = ensure_local_directories()

    assert paths.root == data_dir.resolve()
    for name in SUBDIRECTORIES:
        assert (paths.root / name).is_dir()
    assert paths.database_file == data_dir.resolve() / "database" / "naratrace.sqlite3"
    assert paths.database_url.startswith("sqlite:///")

    cached_paths = get_local_paths()
    assert cached_paths.root == paths.root
