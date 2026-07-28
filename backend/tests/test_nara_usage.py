from __future__ import annotations

import httpx
import pytest

from naratrace.core.config import reset_settings_cache
from naratrace.core.paths import reset_paths_cache
from naratrace.main import create_app
from naratrace.nara.usage import record_nara_api_request


@pytest.mark.asyncio
async def test_settings_report_local_nara_api_key_usage(tmp_path, monkeypatch):
    monkeypatch.setenv("NARATRACE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("NARA_API_KEY", "usage-test-key")
    monkeypatch.setenv("NARATRACE_NARA_MONTHLY_REQUEST_LIMIT", "5")
    monkeypatch.setattr("naratrace.core.secrets._read_keyring_value", lambda: None)
    reset_settings_cache()
    reset_paths_cache()

    app = create_app()
    async with app.router.lifespan_context(app):
        record_nara_api_request("usage-test-key")
        record_nara_api_request("usage-test-key")

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/settings")

    assert response.status_code == 200
    usage = response.json()["nara_api_usage"]
    assert usage["request_count"] == 2
    assert usage["request_limit"] == 5
    assert usage["percent_used"] == 40
    assert usage["counted_locally"] is True
