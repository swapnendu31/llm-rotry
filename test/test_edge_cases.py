from datetime import datetime, timedelta
import json
import pytest
from fastapi.testclient import TestClient

from src.controller.controller_run import (
    estimate_request_tokens,
    extract_actual_tokens,
    record_token_consumption,
)
from src.helper.redis import get_window_key_and_ttl
from src.main import app
from src.services import engine


# ============================================================================
# Test Fixtures & Fakes
# ============================================================================

class FakeRedis:
    def __init__(self):
        self.hashes = {}
        self.strings = {}
        self.sets = {}

    def hset_many(self, key, values):
        current = self.hashes.setdefault(key, {})
        for field, value in values.items():
            current[field] = str(value)
        return len(values)

    def hgetall(self, key):
        return self.hashes.get(key, {}).copy()

    def sadd(self, key, *members):
        values = self.sets.setdefault(key, set())
        before = len(values)
        values.update(members)
        return len(values) - before

    def smembers(self, key):
        return self.sets.get(key, set()).copy()

    def get_key(self, key):
        return self.strings.get(key)

    def set_key(self, key, value, expire_seconds=None):
        self.strings[key] = str(value)
        return True

    def increment(self, key, amount=1):
        value = int(self.strings.get(key, "0")) + amount
        self.strings[key] = str(value)
        return value

    def exists(self, key):
        return (key in self.hashes) or (key in self.strings)

    def claim_time_window_quota(self, runtime_key, key_id, limits, tokens=0, now=None):
        now = now or datetime.utcnow()
        checks = []

        for limit_type in ("rpm", "rpd", "rpmon"):
            if limit_type in limits and limits[limit_type] is not None:
                usage_key, _ = get_window_key_and_ttl(key_id, limit_type, now)
                checks.append((usage_key, int(limits[limit_type]), 1))

        if tokens > 0:
            for limit_type in ("tpm", "tpd", "tpmon"):
                if limit_type in limits and limits[limit_type] is not None:
                    usage_key, _ = get_window_key_and_ttl(key_id, limit_type, now)
                    checks.append((usage_key, int(limits[limit_type]), tokens))

        for usage_key, limit, amount in checks:
            current = int(self.strings.get(usage_key, "0"))
            if current + amount > limit:
                return False, usage_key

        for usage_key, limit, amount in checks:
            current = int(self.strings.get(usage_key, "0"))
            self.strings[usage_key] = str(current + amount)

        if runtime_key:
            self.hashes.setdefault(runtime_key, {})["last_used"] = now.strftime("%Y-%m-%d %H:%M:%S")

        return True, None


@pytest.fixture
def mock_redis(monkeypatch):
    r = FakeRedis()
    monkeypatch.setattr(engine, "hset_many", r.hset_many)
    monkeypatch.setattr(engine, "hgetall", r.hgetall)
    monkeypatch.setattr(engine, "sadd", r.sadd)
    monkeypatch.setattr(engine, "smembers", r.smembers)
    monkeypatch.setattr(engine, "get_key", r.get_key)
    monkeypatch.setattr(engine, "set_key", r.set_key)
    monkeypatch.setattr(engine, "increment", r.increment)
    monkeypatch.setattr(engine, "exists", r.exists)
    monkeypatch.setattr(engine, "claim_time_window_quota", r.claim_time_window_quota)
    return r


@pytest.fixture
def client():
    headers = {"X-Auth-Key": "rotator_secret_key_123"}
    with TestClient(app, raise_server_exceptions=False, headers=headers) as c:
        yield c


def register_key(redis, provider, key_id, key_type, api_key, **limits):
    redis_key = f"{provider}-key:{key_id}"
    values = {
        "id": key_id,
        "provider": provider,
        "key_type": key_type,
        "api_key": api_key,
        **limits,
    }
    redis.hset_many(redis_key, values)
    redis.sadd(provider, redis_key)
    return redis_key


def get_usage(redis, key_id, limit_type, now=None):
    usage_key, _ = get_window_key_and_ttl(key_id, limit_type, now)
    return int(redis.get_key(usage_key) or 0)


# ============================================================================
# Category 1: Concurrency & Boundary Quota Exhaustion
# ============================================================================

def test_exact_boundary_quota_exhaustion_does_not_leak(mock_redis):
    """Verify when limit is exactly reached (e.g. 3/3), next request fails and counter stays at 3."""
    register_key(mock_redis, "test_p", "k1", "api_call", "key-val", rpm=3)

    assert engine.get_key_from_redis("test_p") == "key-val"
    assert engine.get_key_from_redis("test_p") == "key-val"
    assert engine.get_key_from_redis("test_p") == "key-val"
    assert get_usage(mock_redis, "k1", "rpm") == 3

    # 4th request must be rejected
    assert engine.get_key_from_redis("test_p") is None
    # Counter must NOT leak past boundary to 4
    assert get_usage(mock_redis, "k1", "rpm") == 3


def test_zero_quota_configured_is_immediately_rejected(mock_redis):
    """Verify keys explicitly configured with 0 RPM are immediately exhausted."""
    register_key(mock_redis, "test_p", "k_zero", "api_call", "zero-key", rpm=0)
    assert engine.get_key_from_redis("test_p") is None


def test_negative_tokens_raises_validation_error(mock_redis):
    """Negative tokens must raise ValueError or return None gracefully."""
    register_key(mock_redis, "openai", "k_llm", "llm_call", "sk-llm", rpm=10, tpm=100)
    # Direct rule call raises ValueError
    with pytest.raises(ValueError, match="tokens cannot be negative"):
        engine.rule_for_llm("openai-key:k_llm", tokens=-10)
    # Engine catch-all gracefully logs and returns None
    assert engine.get_key_from_redis("openai", tokens=-10) is None



def test_key_without_limits_is_unlimited(mock_redis):
    """Keys with no configured limits should never be artificially blocked."""
    register_key(mock_redis, "unlimited", "k_free", "api_call", "free-key")
    for _ in range(10):
        assert engine.get_key_from_redis("unlimited") == "free-key"


# ============================================================================
# Category 2: Multi-Tier Window Precedence & Window Transitions
# ============================================================================

def test_rpd_blocks_request_even_when_rpm_has_capacity(mock_redis):
    """RPD constraint must override and block requests even if RPM is wide open."""
    register_key(mock_redis, "daily_cap", "k1", "api_call", "secret", rpm=100, rpd=2)

    assert engine.get_key_from_redis("daily_cap") == "secret"
    assert engine.get_key_from_redis("daily_cap") == "secret"

    # Blocked by RPD (2/2 reached) despite RPM having 98 requests remaining
    assert engine.get_key_from_redis("daily_cap") is None


def test_tpm_blocks_request_even_when_rpm_has_capacity(mock_redis):
    """TPM constraint must block request when tokens exceed limit, even if request count is fine."""
    register_key(mock_redis, "token_cap", "k1", "llm_call", "secret", rpm=10, tpm=100)

    # First request consumes 60 tokens -> Allowed (60/100 used)
    assert engine.get_key_from_redis("token_cap", tokens=60) == "secret"

    # Second request requires 50 tokens (60 + 50 = 110 > 100) -> Blocked!
    assert engine.get_key_from_redis("token_cap", tokens=50) is None


def test_day_rollover_resets_rpd_while_month_continues_accumulating(mock_redis, monkeypatch):
    """Crossing UTC midnight must reset daily counters while monthly counters retain history."""
    register_key(mock_redis, "serper", "k1", "api_call", "secret", rpd=2, rpmon=10)

    day1 = datetime(2026, 9, 15, 23, 50, 0)
    day2 = datetime(2026, 9, 16, 0, 10, 0)

    # Day 1: Consume daily quota
    monkeypatch.setattr(
        engine,
        "claim_time_window_quota",
        lambda runtime_key, key_id, limits, tokens=0, now=None: mock_redis.claim_time_window_quota(
            runtime_key, key_id, limits, tokens=tokens, now=day1
        ),
    )
    assert engine.get_key_from_redis("serper") == "secret"
    assert engine.get_key_from_redis("serper") == "secret"
    assert engine.get_key_from_redis("serper") is None

    # Day 2: Day counter resets to 0, monthly counter continues accumulating
    monkeypatch.setattr(
        engine,
        "claim_time_window_quota",
        lambda runtime_key, key_id, limits, tokens=0, now=None: mock_redis.claim_time_window_quota(
            runtime_key, key_id, limits, tokens=tokens, now=day2
        ),
    )
    assert engine.get_key_from_redis("serper") == "secret"
    assert get_usage(mock_redis, "k1", "rpd", now=day2) == 1
    assert get_usage(mock_redis, "k1", "rpmon", now=day2) == 3


# ============================================================================
# Category 3: Token Estimation & Asymmetric Reconciliation Edge Cases
# ============================================================================

def test_multimodal_parts_character_estimation():
    """Verify estimation correctly traverses multimodal message content parts."""
    payload = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "a" * 200},
                    {"type": "image_url", "image_url": {"url": "http://img"}},
                    {"type": "text", "text": "b" * 200},
                ],
            }
        ],
        "max_tokens": 100,
    }
    # 400 text chars -> 100 base context * 1.05 = 105 tokens + 100 max = 205
    body_bytes = json.dumps(payload).encode("utf-8")
    assert estimate_request_tokens(body_bytes) == 205


def test_empty_payload_and_malformed_json_fallback_estimation():
    """Empty or non-dictionary JSON must handle gracefully without crashing."""
    assert estimate_request_tokens(b"") == 0
    # Malformed text uses raw character length fallback
    assert estimate_request_tokens(b"raw text prompt") > 0


def test_extract_actual_tokens_handles_missing_and_alternate_keys():
    """Handles prompt + completion split when total_tokens key is missing."""
    assert extract_actual_tokens({}) is None
    assert extract_actual_tokens({"usage": {"total_tokens": 42}}) == 42
    # Fallback to sum of prompt + completion
    assert extract_actual_tokens({"usage": {"prompt_tokens": 30, "completion_tokens": 70}}) == 100


# ============================================================================
# Category 4: Circuit Breaker & Cooldown Mechanics
# ============================================================================

def test_cooldown_skips_cooling_key_and_selects_healthy_sibling(mock_redis):
    """When Key 1 is cooling down, the router immediately rotates to Key 2."""
    register_key(mock_redis, "openai", "k1", "llm_call", "sk-1", rpm=10)
    register_key(mock_redis, "openai", "k2", "llm_call", "sk-2", rpm=10)

    # Place Key 1 in cooldown
    engine.set_cooldown("openai-key:k1", seconds=60)

    # Key 2 must be selected without downtime
    assert engine.get_key_from_redis("openai") == "sk-2"


def test_all_keys_in_cooldown_returns_none_gracefully(mock_redis):
    """When all candidate keys are cooling down, returns None without crashing."""
    register_key(mock_redis, "openai", "k1", "llm_call", "sk-1", rpm=10)
    register_key(mock_redis, "openai", "k2", "llm_call", "sk-2", rpm=10)

    engine.set_cooldown("openai-key:k1", seconds=60)
    engine.set_cooldown("openai-key:k2", seconds=60)

    assert engine.get_key_from_redis("openai") is None


# ============================================================================
# Category 5: Upstream Failure Modes & Error Recovery
# ============================================================================

def test_upstream_503_cools_down_key_and_rotates(monkeypatch, client):
    """503 Gateway Crash places candidate key on cooldown and fails over to backup key."""
    key1 = {"candidate_key": "p:k1", "key_id": "k1", "api_key": "sk-1", "api_url": "http://api", "provider": "test_p"}
    key2 = {"candidate_key": "p:k2", "key_id": "k2", "api_key": "sk-2", "api_url": "http://api", "provider": "test_p"}
    pool = [key1, key2]
    cooldowns = []

    monkeypatch.setattr("src.controller.controller_run.get_key_record_from_redis", lambda p, tokens=0: pool.pop(0) if pool else None)
    monkeypatch.setattr("src.controller.controller_run.set_cooldown", lambda k, seconds=30: cooldowns.append(k))

    call_num = 0

    class Fake503:
        status_code = 503
        content = b"Service Unavailable"
        headers = {"content-type": "text/plain"}

    class Fake200:
        status_code = 200
        content = b'{"status": "recovered"}'
        headers = {"content-type": "application/json"}

    async def fake_req(*args, **kwargs):
        nonlocal call_num
        call_num += 1
        return Fake503() if call_num == 1 else Fake200()

    monkeypatch.setattr("httpx.AsyncClient.request", fake_req)

    resp = client.post("/proxy/test_p", json={"msg": "hello"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "recovered"}
    assert "p:k1" in cooldowns


def test_upstream_empty_body_retried_on_next_key(monkeypatch, client):
    """Empty body (0 bytes on 200 OK) is treated as incomplete JSON and retried."""
    key1 = {"candidate_key": "p:k1", "key_id": "k1", "api_key": "sk-1", "api_url": "http://api", "provider": "test_p"}
    key2 = {"candidate_key": "p:k2", "key_id": "k2", "api_key": "sk-2", "api_url": "http://api", "provider": "test_p"}
    pool = [key1, key2]

    monkeypatch.setattr("src.controller.controller_run.get_key_record_from_redis", lambda p, tokens=0: pool.pop(0) if pool else None)
    monkeypatch.setattr("src.controller.controller_run.set_cooldown", lambda k, seconds=30: None)

    call_count = 0

    class Empty200:
        status_code = 200
        content = b""
        headers = {"content-type": "application/json"}

    class Valid200:
        status_code = 200
        content = b'{"success": true}'
        headers = {"content-type": "application/json"}

    async def fake_req(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return Empty200() if call_count == 1 else Valid200()

    monkeypatch.setattr("httpx.AsyncClient.request", fake_req)

    resp = client.post("/proxy/test_p", json={"q": "test"})
    assert resp.status_code == 200
    assert resp.json() == {"success": True}
    assert call_count == 2
