import pytest
from fastapi.testclient import TestClient
from src.main import app


@pytest.fixture
def client():
    # Bypass lifespan database checks for unit tests with Auth Key configured
    headers = {"X-Auth-Key": "rotator_secret_key_123"}
    with TestClient(app, raise_server_exceptions=False, headers=headers) as c:
        yield c


def test_acquire_key_endpoint_success(monkeypatch, client):
    monkeypatch.setattr(
        "src.controller.controller_run.get_key_from_redis",
        lambda provider, tokens=0: "test-secret-key" if provider == "serper" else None,
    )

    resp = client.get("/acquire/serper")
    assert resp.status_code == 200
    assert resp.json() == {"provider": "serper", "api_key": "test-secret-key"}


def test_acquire_key_endpoint_exhausted(monkeypatch, client):
    monkeypatch.setattr(
        "src.controller.controller_run.get_key_from_redis",
        lambda provider, tokens=0: None,
    )

    resp = client.get("/acquire/exhausted-provider")
    assert resp.status_code == 429
    assert "exhausted or in cooldown" in resp.json()["detail"]


def test_proxy_endpoint_success(monkeypatch, client):
    fake_record = {
        "candidate_key": "openai-key:k1",
        "key_id": "k1",
        "api_key": "sk-test-123",
        "api_url": "https://api.openai.com/v1/chat/completions",
        "provider": "openai",
    }
    monkeypatch.setattr(
        "src.controller.controller_run.get_key_record_from_redis",
        lambda provider, tokens=0: fake_record,
    )

    class FakeResponse:
        status_code = 200
        content = b'{"result": "ok"}'
        headers = {"content-type": "application/json"}

    async def fake_request(*args, **kwargs):
        assert kwargs["headers"]["Authorization"] == "Bearer sk-test-123"
        return FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient.request", fake_request)

    resp = client.post("/proxy/openai", json={"model": "gpt-4o", "messages": []})
    assert resp.status_code == 200
    assert resp.json() == {"result": "ok"}


def test_proxy_endpoint_cooldown_on_429(monkeypatch, client):
    fake_record = {
        "candidate_key": "serper-key:k1",
        "key_id": "k1",
        "api_key": "serper-secret",
        "api_url": "https://google.serper.dev/search",
        "provider": "serper",
    }
    cooldowns_set = []

    monkeypatch.setattr(
        "src.controller.controller_run.get_key_record_from_redis",
        lambda provider, tokens=0: fake_record,
    )
    monkeypatch.setattr(
        "src.controller.controller_run.set_cooldown",
        lambda candidate_key, seconds=60: cooldowns_set.append((candidate_key, seconds)),
    )

    class Fake429Response:
        status_code = 429
        content = b'{"error": "rate limit exceeded"}'
        headers = {"content-type": "application/json"}

    async def fake_request(*args, **kwargs):
        return Fake429Response()

    monkeypatch.setattr("httpx.AsyncClient.request", fake_request)

    resp = client.post("/proxy/serper", json={"q": "test query"})
    assert resp.status_code == 429
    # Verified: Key placed on 60s cooldown!
    assert ("serper-key:k1", 60) in cooldowns_set


def test_estimate_request_tokens_calculation():
    from src.controller.controller_run import estimate_request_tokens
    import json

    # 400 characters in prompt -> 400/4 = 100 base tokens -> 100 * 1.05 = 105 tokens
    # max_tokens = 500 -> total = 105 + 500 = 605
    payload = {
        "messages": [{"role": "user", "content": "a" * 400}],
        "max_tokens": 500,
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    assert estimate_request_tokens(body_bytes) == 605


def test_proxy_endpoint_token_refund_on_success(monkeypatch, client):
    fake_record = {
        "candidate_key": "openai-key:k1",
        "key_id": "k1",
        "api_key": "sk-test",
        "api_url": "https://api.openai.com/v1/chat/completions",
        "provider": "openai",
    }
    reconciled = []

    monkeypatch.setattr(
        "src.controller.controller_run.get_key_record_from_redis",
        lambda provider, tokens=0: fake_record,
    )
    monkeypatch.setattr(
        "src.controller.controller_run.record_token_consumption",
        lambda key_id, delta, now=None: reconciled.append((key_id, delta)),
    )

    class FakeLLMResponse:
        status_code = 200
        content = b'{"id": "c1", "choices": [], "usage": {"prompt_tokens": 50, "completion_tokens": 50, "total_tokens": 100}}'
        headers = {"content-type": "application/json"}

    async def fake_request(*args, **kwargs):
        return FakeLLMResponse()

    monkeypatch.setattr("httpx.AsyncClient.request", fake_request)

    # 400 chars -> 105 context tokens + 500 max_tokens = 605 reserved
    payload = {"messages": [{"role": "user", "content": "a" * 400}], "max_tokens": 500}
    resp = client.post("/proxy/openai", json=payload)
    assert resp.status_code == 200

    # 100 actual - 605 reserved = -505 tokens (refunded)
    assert reconciled == [("k1", -505)]


def test_proxy_endpoint_token_extra_consumed_on_success(monkeypatch, client):
    fake_record = {
        "candidate_key": "openai-key:k1",
        "key_id": "k1",
        "api_key": "sk-test",
        "api_url": "https://api.openai.com/v1/chat/completions",
        "provider": "openai",
    }
    reconciled = []

    monkeypatch.setattr(
        "src.controller.controller_run.get_key_record_from_redis",
        lambda provider, tokens=0: fake_record,
    )
    monkeypatch.setattr(
        "src.controller.controller_run.record_token_consumption",
        lambda key_id, delta, now=None: reconciled.append((key_id, delta)),
    )

    class FakeLLMResponse:
        status_code = 200
        content = b'{"id": "c1", "choices": [], "usage": {"total_tokens": 700}}'
        headers = {"content-type": "application/json"}

    async def fake_request(*args, **kwargs):
        return FakeLLMResponse()

    monkeypatch.setattr("httpx.AsyncClient.request", fake_request)

    # 400 chars -> 605 reserved, but actual used is 700 tokens!
    payload = {"messages": [{"role": "user", "content": "a" * 400}], "max_tokens": 500}
    resp = client.post("/proxy/openai", json=payload)
    assert resp.status_code == 200

    # 700 actual - 605 reserved = +95 tokens (added to Redis usage counters)
    assert reconciled == [("k1", 95)]



def test_proxy_endpoint_retry_on_incomplete_json(monkeypatch, client):
    key1 = {"candidate_key": "openai-key:k1", "key_id": "k1", "api_key": "sk-1", "api_url": "https://api.openai.com", "provider": "openai"}
    key2 = {"candidate_key": "openai-key:k2", "key_id": "k2", "api_key": "sk-2", "api_url": "https://api.openai.com", "provider": "openai"}

    records = [key1, key2]
    cooldowns = []

    def fake_get_record(provider, tokens=0):
        if records:
            return records.pop(0)
        return None

    monkeypatch.setattr("src.controller.controller_run.get_key_record_from_redis", fake_get_record)
    monkeypatch.setattr("src.controller.controller_run.set_cooldown", lambda k, seconds=30: cooldowns.append(k))

    call_count = 0

    class IncompleteResponse:
        status_code = 200
        # Malformed / truncated JSON missing closing quotes/braces
        content = b'{"id": "c1", "choices": [{"text": "cut off mid stream'
        headers = {"content-type": "application/json"}

    class SuccessResponse:
        status_code = 200
        content = b'{"id": "c2", "choices": [], "usage": {"total_tokens": 50}}'
        headers = {"content-type": "application/json"}

    async def fake_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return IncompleteResponse()
        return SuccessResponse()

    monkeypatch.setattr("httpx.AsyncClient.request", fake_request)

    resp = client.post("/proxy/openai", json={"messages": [{"role": "user", "content": "hello"}]})
    assert resp.status_code == 200
    assert resp.json()["id"] == "c2"

    # Attempt 1 failed with incomplete JSON -> k1 placed on cooldown
    assert "openai-key:k1" in cooldowns
    # Attempt 2 called the API again with k2 and succeeded!
    assert call_count == 2

