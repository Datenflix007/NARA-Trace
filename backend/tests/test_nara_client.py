from __future__ import annotations

import pytest

from naratrace.nara.client import NaraCatalogClient, NaraClientError


@pytest.mark.asyncio
async def test_search_records_falls_back_to_abbreviated_metadata_after_detail_500(monkeypatch):
    client = NaraCatalogClient(api_key="test-key")
    calls: list[dict[str, object]] = []

    async def fake_get(path: str, params: dict[str, object]):
        calls.append(dict(params))
        if len(calls) == 1:
            raise NaraClientError("NARA Catalog API meldet einen temporären Serverfehler.", 500)
        return {
            "body": {
                "hits": {
                    "total": {"value": 1, "relation": "eq"},
                    "hits": [
                        {
                            "_source": {
                                "record": {
                                    "naId": 123,
                                    "title": "Fallback metadata record",
                                }
                            }
                        }
                    ],
                }
            }
        }

    monkeypatch.setattr(client, "_get", fake_get)

    response = await client.search_records(
        {
            "q": "Schultze Naumburg",
            "limit": 50,
            "includeExtractedText": "true",
            "availableOnline": "true",
        }
    )

    assert len(calls) == 2
    assert calls[0]["includeExtractedText"] == "true"
    assert "includeExtractedText" not in calls[1]
    assert calls[1]["abbreviated"] == "true"
    assert response.total == 1
    assert response.items[0].record.naId == 123
    assert response.warnings
