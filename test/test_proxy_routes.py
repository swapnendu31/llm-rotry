import itertools
from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient

from src.controller import controller_run
from src.controller.controller_run import get_next_proxy, PROXY_ROUTES, ROUTE_1_PROXY, ROUTE_2_PROXY
from src.main import app


def test_proxy_route_cycle_sequence():
    """Verify that get_next_proxy() cycles accurately across all 3 routes."""
    # Reset the route cycle to start cleanly from index 0
    controller_run._route_cycle = itertools.cycle(PROXY_ROUTES)

    assert get_next_proxy() is None
    assert get_next_proxy() == ROUTE_1_PROXY
    assert get_next_proxy() == ROUTE_2_PROXY
    # Next should loop back to None (own IP)
    assert get_next_proxy() is None
    assert get_next_proxy() == ROUTE_1_PROXY
    assert get_next_proxy() == ROUTE_2_PROXY


@pytest.mark.asyncio
async def test_proxy_client_receives_correct_route():
    """Verify httpx.AsyncClient is invoked with the expected proxy on consecutive requests."""
    controller_run._route_cycle = itertools.cycle(PROXY_ROUTES)

    observed_proxies = []

    # Mock get_key_record_from_redis so a key is returned
    fake_record = {
        "candidate_key": "openai-key:1",
        "key_id": "1",
        "api_key": "sk-test-123",
        "api_url": "https://api.openai.com/v1",
        "provider": "openai",
    }

    # Mock response
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.content = b'{"status": "ok"}'
    mock_resp.headers = {"content-type": "application/json"}

    original_async_client = controller_run.httpx.AsyncClient

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            observed_proxies.append(kwargs.get("proxy"))
            self._client = AsyncMock()
            self._client.request = AsyncMock(return_value=mock_resp)

        async def __aenter__(self):
            return self._client

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    with patch("src.controller.controller_run.get_key_record_from_redis", return_value=fake_record), \
         patch("src.controller.controller_run.httpx.AsyncClient", new=MockAsyncClient):
        
        client = TestClient(app)

        # Request 1 (Direct -> proxy is None)
        res1 = client.post("/proxy/openai/chat/completions", headers={"X-Auth-Key": "rotator_secret_key_123"}, json={})
        assert res1.status_code == 200

        # Request 2 (Route 1)
        res2 = client.post("/proxy/openai/chat/completions", headers={"X-Auth-Key": "rotator_secret_key_123"}, json={})
        assert res2.status_code == 200

        # Request 3 (Route 2)
        res3 = client.post("/proxy/openai/chat/completions", headers={"X-Auth-Key": "rotator_secret_key_123"}, json={})
        assert res3.status_code == 200

        # Request 4 (Direct -> loops back to None)
        res4 = client.post("/proxy/openai/chat/completions", headers={"X-Auth-Key": "rotator_secret_key_123"}, json={})
        assert res4.status_code == 200

    assert observed_proxies == [
        None,
        ROUTE_1_PROXY,
        ROUTE_2_PROXY,
        None,
    ]


@pytest.mark.asyncio
async def test_keyless_endpoint_omits_authorization_header():
    """Verify that when a key has an empty api_key, no Authorization or X-API-KEY header is attached."""
    fake_record = {
        "candidate_key": "local-llm-key:1",
        "key_id": "1",
        "api_key": "",
        "api_url": "http://127.0.0.1:8000/v1",
        "provider": "local-llm",
    }

    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.content = b'{"status": "ok"}'
    mock_resp.headers = {"content-type": "application/json"}

    captured_headers = {}

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            self._client = AsyncMock()
            async def fake_request(*req_args, **req_kwargs):
                captured_headers.update(req_kwargs.get("headers", {}))
                return mock_resp
            self._client.request = fake_request

        async def __aenter__(self):
            return self._client

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    with patch("src.controller.controller_run.get_key_record_from_redis", return_value=fake_record), \
         patch("src.controller.controller_run.httpx.AsyncClient", new=MockAsyncClient):
        client = TestClient(app)
        res = client.post("/proxy/local-llm/chat/completions", headers={"X-Auth-Key": "rotator_secret_key_123"}, json={})
        assert res.status_code == 200
        assert "Authorization" not in captured_headers
        assert "X-API-KEY" not in captured_headers
