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


def setup_redis(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(engine, "hset_many", redis.hset_many)
    monkeypatch.setattr(engine, "hset", redis.hset)
    monkeypatch.setattr(engine, "hgetall", redis.hgetall)
    monkeypatch.setattr(engine, "sadd", redis.sadd)
    monkeypatch.setattr(engine, "smembers", redis.smembers)
    monkeypatch.setattr(engine, "get_key", redis.get_key)
    monkeypatch.setattr(engine, "set_key", redis.set_key)
    monkeypatch.setattr(engine, "increment", redis.increment)
    monkeypatch.setattr(engine, "exists", redis.exists)
    return redis


def test_api_key_is_selected_and_request_limit_decreases(monkeypatch):
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

    runtime = redis.hgetall(f"{key}-runtime")
    assert runtime["rpm"] == "1"
    assert runtime["rpd"] == "3"


def test_llm_key_decreases_request_and_token_limits(monkeypatch):
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

    runtime = redis.hgetall(f"{key}-runtime")
    assert runtime["rpm"] == "1"
    assert runtime["rpmon"] == "9"
    assert runtime["tpm"] == "75"
    assert runtime["tpd"] == "975"
    assert runtime["tpmon"] == "4975"


def test_exhausted_key_uses_the_next_key(monkeypatch):
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
    key = add_key(redis, "openai", "llm-small", "llm_call", "small-key", rpm=2, tpm=20)

    assert engine.get_key_from_redis("openai", tokens=25) is None

    runtime = redis.hgetall(f"{key}-runtime")
    assert runtime["rpm"] == "2"
    assert runtime["tpm"] == "20"
