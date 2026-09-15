from datetime import datetime, timedelta

from src.helper.redis import get_window_key_and_ttl
from src.services import engine


class FakeRedis:
    def __init__(self):
        self.hashes = {}
        self.strings = {}
        self.sets = {}

    def hset_many(self, key, values):
        current = self.hashes.setdefault(key, {})
        new_fields = 0
        for field, value in values.items():
            if field not in current:
                new_fields += 1
            current[field] = str(value)
        return new_fields

    def hset(self, key, field, value):
        return self.hset_many(key, {field: value})

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

    def set_key(self, key, value):
        self.strings[key] = str(value)
        return True

    def increment(self, key, amount=1):
        value = int(self.strings.get(key, "0")) + amount
        self.strings[key] = str(value)
        return value

    def exists(self, key):
        return key in self.hashes

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

        # Check all limits
        for usage_key, limit, amount in checks:
            current = int(self.strings.get(usage_key, "0"))
            if current + amount > limit:
                return False, usage_key

        # Increment all limits
        for usage_key, limit, amount in checks:
            current = int(self.strings.get(usage_key, "0"))
            self.strings[usage_key] = str(current + amount)

        if runtime_key:
            self.hashes.setdefault(runtime_key, {})["last_used"] = now.strftime("%Y-%m-%d %H:%M:%S")

        return True, None

    def release_time_window_quota(self, key_id, tokens=0, limits_checked=None, now=None):
        now = now or datetime.utcnow()
        limits_checked = limits_checked or ("rpm", "rpd", "rpmon")
        for limit_type in limits_checked:
            usage_key, _ = get_window_key_and_ttl(key_id, limit_type, now)
            current = int(self.strings.get(usage_key, "0"))
            self.strings[usage_key] = str(max(0, current - 1))

        if tokens > 0:
            for limit_type in ("tpm", "tpd", "tpmon"):
                usage_key, _ = get_window_key_and_ttl(key_id, limit_type, now)
                current = int(self.strings.get(usage_key, "0"))
                self.strings[usage_key] = str(max(0, current - tokens))



def add_key(redis, provider, key_id, key_type, api_key, **limits):
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


def get_usage(redis: FakeRedis, key_id: str, limit_type: str, now: datetime | None = None) -> int:
    usage_key, _ = get_window_key_and_ttl(key_id, limit_type, now)
    return int(redis.get_key(usage_key) or 0)


def setup_redis(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(engine, "hset_many", redis.hset_many)
    monkeypatch.setattr(engine, "hgetall", redis.hgetall)
    monkeypatch.setattr(engine, "sadd", redis.sadd)
    monkeypatch.setattr(engine, "smembers", redis.smembers)
    monkeypatch.setattr(engine, "get_key", redis.get_key)
    monkeypatch.setattr(engine, "set_key", redis.set_key)
    monkeypatch.setattr(engine, "increment", redis.increment)
    monkeypatch.setattr(engine, "exists", redis.exists)
    monkeypatch.setattr(engine, "claim_time_window_quota", redis.claim_time_window_quota)
    return redis


def test_api_key_is_selected_and_usage_counter_increases(monkeypatch):
    redis = setup_redis(monkeypatch)
    key = add_key(
        redis,
        "serper",
        "api-1",
        "api_call",
        "api-secret",
        rpm=2,
        rpd=4,
    )

    assert engine.get_key_from_redis("serper") == "api-secret"

    # Verifies Point 2: Usage is tracked in time-window counters
    assert get_usage(redis, "api-1", "rpm") == 1
    assert get_usage(redis, "api-1", "rpd") == 1

    # Runtime metadata stores operational info
    runtime = redis.hgetall(f"{key}-runtime")
    assert "last_used" in runtime


def test_llm_key_tracks_both_request_and_token_usage(monkeypatch):
    redis = setup_redis(monkeypatch)
    key = add_key(
        redis,
        "openai",
        "llm-1",
        "llm_call",
        "llm-secret",
        rpm=2,
        rpmon=10,
        tpm=100,
        tpd=1000,
        tpmon=5000,
    )

    assert engine.get_key_from_redis("openai", tokens=25) == "llm-secret"

    # Both request counters and token counters increment by respective amounts
    assert get_usage(redis, "llm-1", "rpm") == 1
    assert get_usage(redis, "llm-1", "rpmon") == 1
    assert get_usage(redis, "llm-1", "tpm") == 25
    assert get_usage(redis, "llm-1", "tpd") == 25
    assert get_usage(redis, "llm-1", "tpmon") == 25


def test_exhausted_key_rotates_to_the_next_key(monkeypatch):
    redis = setup_redis(monkeypatch)
    add_key(redis, "test", "a-exhausted", "api_call", "old-key", rpm=0)
    add_key(redis, "test", "b-ready", "api_call", "new-key", rpm=2)

    assert engine.get_key_from_redis("test") == "new-key"


def test_returns_none_when_every_key_is_exhausted(monkeypatch):
    redis = setup_redis(monkeypatch)
    add_key(redis, "test", "api-1", "api_call", "first", rpm=0)
    add_key(redis, "test", "api-2", "api_call", "second", rpm=0)

    assert engine.get_key_from_redis("test") is None


def test_llm_key_is_skipped_when_tokens_are_not_enough(monkeypatch):
    redis = setup_redis(monkeypatch)
    add_key(redis, "openai", "llm-small", "llm_call", "small-key", rpm=2, tpm=20)

    # 25 tokens requested > 20 tpm limit
    assert engine.get_key_from_redis("openai", tokens=25) is None
    assert get_usage(redis, "llm-small", "tpm") == 0


def test_automatic_quota_reset_in_next_time_window(monkeypatch):
    redis = setup_redis(monkeypatch)
    add_key(redis, "serper", "api-1", "api_call", "api-secret", rpm=1)

    t0 = datetime(2026, 9, 15, 12, 0, 0)
    t_next_minute = datetime(2026, 9, 15, 12, 1, 0)

    # First request at t0 succeeds (uses 1/1)
    monkeypatch.setattr(
        engine,
        "claim_time_window_quota",
        lambda runtime_key, key_id, limits, tokens=0, now=None: redis.claim_time_window_quota(
            runtime_key, key_id, limits, tokens=tokens, now=t0
        ),
    )
    assert engine.get_key_from_redis("serper") == "api-secret"

    # Second request in the same minute is exhausted
    assert engine.get_key_from_redis("serper") is None

    # Request in the next minute automatically uses the fresh window counter!
    monkeypatch.setattr(
        engine,
        "claim_time_window_quota",
        lambda runtime_key, key_id, limits, tokens=0, now=None: redis.claim_time_window_quota(
            runtime_key, key_id, limits, tokens=tokens, now=t_next_minute
        ),
    )
    assert engine.get_key_from_redis("serper") == "api-secret"


def test_quota_reservation_rollback_on_failed_dispatch(monkeypatch):
    redis = setup_redis(monkeypatch)
    add_key(redis, "serper", "api-1", "api_call", "api-secret", rpm=1)

    # 1. Quota reserved
    assert engine.get_key_from_redis("serper") == "api-secret"
    assert get_usage(redis, "api-1", "rpm") == 1

    # Key is now exhausted for this minute
    assert engine.get_key_from_redis("serper") is None

    # 2. Upstream network failed before request was sent -> release quota
    redis.release_time_window_quota("api-1")
    assert get_usage(redis, "api-1", "rpm") == 0

    # Key is available again immediately
    assert engine.get_key_from_redis("serper") == "api-secret"


