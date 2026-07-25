from __future__ import annotations

import httpx
import pytest

from naratrace.core.config import reset_settings_cache
from naratrace.core.paths import reset_paths_cache
from naratrace.main import create_app


@pytest.mark.asyncio
async def test_health_endpoint_initializes_local_runtime(tmp_path, monkeypatch):
    data_dir = tmp_path / "naratrace-data"
    monkeypatch.setenv("NARATRACE_DATA_DIR", str(data_dir))
    reset_settings_cache()
    reset_paths_cache()

    app = create_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/health")
            demo_response = await client.get("/demo/schultze-portrait.png")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["app"] == "NARATrace"
    assert payload["bind_host"] == "127.0.0.1"
    assert payload["bind_port"] == 8765
    assert payload["data_dir"] == str(data_dir.resolve())
    assert (data_dir / "database" / "naratrace.sqlite3").exists()
    assert demo_response.status_code == 200
    assert demo_response.headers["content-type"] == "image/png"
