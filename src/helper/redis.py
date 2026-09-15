import os
import json
from datetime import datetime
from typing import Any

from redis import Redis
from redis.exceptions import RedisError


redis_client = Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    db=int(os.getenv("REDIS_DB", "0")),
    decode_responses=True,
)


CLAIM_TIME_WINDOW_QUOTA_SCRIPT = """
local runtime_key = KEYS[1]
local timestamp = ARGV[1]
local count = tonumber(ARGV[2]) or 0

-- 1. Check all candidate counters against their respective limits
for i = 0, count - 1 do
    local key = ARGV[3 + i * 4]
    local limit = tonumber(ARGV[4 + i * 4])
    local amount = tonumber(ARGV[5 + i * 4])

    local current = tonumber(redis.call('GET', key) or 0)
    if (current + amount) > limit then
        return {0, key}
    end
end

-- 2. All limits passed; atomically increment counters and set TTL if new
for i = 0, count - 1 do
    local key = ARGV[3 + i * 4]
    local amount = tonumber(ARGV[5 + i * 4])
    local ttl = tonumber(ARGV[6 + i * 4])

    local new_val = redis.call('INCRBY', key, amount)
    if new_val == amount and ttl > 0 then
        redis.call('EXPIRE', key, ttl)
    end
end

-- 3. Update runtime metadata last_used
if runtime_key and runtime_key ~= "" then
    redis.call('HSET', runtime_key, 'last_used', timestamp)
end

return {1, ""}
"""

RELEASE_TIME_WINDOW_QUOTA_SCRIPT = """
local count = tonumber(ARGV[1]) or 0
for i = 0, count - 1 do
    local key = ARGV[2 + i * 2]
    local amount = tonumber(ARGV[3 + i * 2])
    local current = tonumber(redis.call('GET', key) or 0)
    if current > 0 then
        local new_val = redis.call('DECRBY', key, amount)
        if new_val < 0 then
            redis.call('SET', key, 0)
        end
    end
end
return 1
"""



def _redis_value(value: Any) -> Any:
    """Convert complex Python values into a Redis-safe string."""
    if value is None or isinstance(value, (str, bytes, int, float)):
        return value
    return json.dumps(value, default=str)


# Connection and health
def get_client() -> Redis:
    return redis_client


def ping() -> bool:
    try:
        return bool(redis_client.ping())
    except RedisError:
        return False


def close() -> None:
    redis_client.close()


# String keys
def set_key(key: str, value: Any, expire_seconds: int | None = None) -> bool:
    """Set a value, optionally expiring it after the given number of seconds."""
    return bool(redis_client.set(key, value, ex=expire_seconds))


def get_key(key: str) -> str | None:
    return redis_client.get(key)


def get_keys(keys: list[str]) -> list[str | None]:
    return list(redis_client.mget(keys))


def delete_keys(*keys: str) -> int:
    return int(redis_client.delete(*keys))


def exists(key: str) -> bool:
    return bool(redis_client.exists(key))


# Expiration
def expire(key: str, seconds: int) -> bool:
    return bool(redis_client.expire(key, seconds))


def expire_at(key: str, timestamp: int) -> bool:
    return bool(redis_client.expireat(key, timestamp))


def ttl(key: str) -> int:
    """Return seconds remaining; -1 means no expiry, -2 means missing."""
    return int(redis_client.ttl(key))


def persist(key: str) -> bool:
    return bool(redis_client.persist(key))


# Hashes
def hset(key: str, field: str, value: Any) -> int:
    return int(redis_client.hset(key, field, str_convert(value)))


def str_convert(value: Any) -> str:
    """Convert a value to a string for Redis storage."""
    if isinstance(value, str):
        return value
    elif isinstance(value, (int, float)):
        return str(value)
    elif value is None:
        return ""
    else:
        return json.dumps(value, default=str)

def hset_many(key: str, values: dict[str, Any]) -> int:
    redis_values = {
        field: str_convert(value)
        for field, value in values.items()
        if value is not None
    }
    return int(redis_client.hset(key, mapping=redis_values))


def get_window_key_and_ttl(
    key_id: str, limit_type: str, now: datetime | None = None
) -> tuple[str, int]:
    """
    Generate the Redis usage counter key and safe TTL for a given window.
    Buffers are added to TTLs to prevent keys from prematurely dropping across window boundaries.
    """
    now = now or datetime.utcnow()
    if limit_type in ("rpm", "tpm"):
        tag = now.strftime("%Y%m%d%H%M")
        # Keep until end of current minute + 60s buffer
        ttl = max(1, (60 - now.second) + 60)
    elif limit_type in ("rpd", "tpd"):
        tag = now.strftime("%Y%m%d")
        seconds_left = 86400 - (now.hour * 3600 + now.minute * 60 + now.second)
        ttl = max(1, seconds_left + 3600)
    elif limit_type in ("rpmon", "tpmon"):
        tag = now.strftime("%Y%m")
        # 35 days safely outlasts any calendar month
        ttl = 35 * 86400
    else:
        raise ValueError(f"Unsupported limit type: {limit_type}")

    return f"usage:{key_id}:{limit_type}:{tag}", ttl


def claim_time_window_quota(
    runtime_key: str,
    key_id: str,
    limits: dict[str, int | None],
    tokens: int = 0,
    now: datetime | None = None,
) -> tuple[bool, str | None]:
    """
    Atomically checks all active time-window limits and increments usage counters if allowed.
    Returns (True, None) on success, or (False, exhausted_key) if any limit would be exceeded.
    """
    now = now or datetime.utcnow()
    timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")

    checks: list[tuple[str, int, int, int]] = []

    # 1. Request limits: each request consumes 1 unit
    for limit_type in ("rpm", "rpd", "rpmon"):
        limit_val = limits.get(limit_type)
        if limit_val is not None:
            usage_key, ttl = get_window_key_and_ttl(key_id, limit_type, now)
            checks.append((usage_key, int(limit_val), 1, ttl))

    # 2. Token limits: consume token count if requested
    if tokens > 0:
        for limit_type in ("tpm", "tpd", "tpmon"):
            limit_val = limits.get(limit_type)
            if limit_val is not None:
                usage_key, ttl = get_window_key_and_ttl(key_id, limit_type, now)
                checks.append((usage_key, int(limit_val), tokens, ttl))

    # If no limits configured for this key, simply update last_used
    if not checks:
        if runtime_key:
            hset(runtime_key, "last_used", timestamp_str)
        return True, None

    # Pack arguments for Lua script: [timestamp, count, key1, limit1, amount1, ttl1, ...]
    argv: list[Any] = [timestamp_str, len(checks)]
    for usage_key, limit, amount, ttl in checks:
        argv.extend([usage_key, limit, amount, ttl])

    result = redis_client.eval(CLAIM_TIME_WINDOW_QUOTA_SCRIPT, 1, runtime_key, *argv)
    allowed, exhausted_key = result[0], result[1]
    return bool(allowed), exhausted_key or None


def release_time_window_quota(
    key_id: str,
    tokens: int = 0,
    limits_checked: tuple[str, ...] | None = None,
    now: datetime | None = None,
) -> None:
    """
    Rolls back quota reservation if a request fails before network dispatch.
    """
    now = now or datetime.utcnow()
    limits_checked = limits_checked or ("rpm", "rpd", "rpmon")
    releases: list[tuple[str, int]] = []

    for limit_type in limits_checked:
        usage_key, _ = get_window_key_and_ttl(key_id, limit_type, now)
        releases.append((usage_key, 1))

    if tokens > 0:
        for limit_type in ("tpm", "tpd", "tpmon"):
            usage_key, _ = get_window_key_and_ttl(key_id, limit_type, now)
            releases.append((usage_key, tokens))

    argv: list[Any] = [len(releases)]
    for usage_key, amount in releases:
        argv.extend([usage_key, amount])

    redis_client.eval(RELEASE_TIME_WINDOW_QUOTA_SCRIPT, 0, *argv)


def record_token_consumption(key_id: str, delta: int, now: datetime | None = None) -> None:
    """
    Adjust token consumption in Redis after actual usage is known.
    - If delta < 0 (actual < reserved): refunds unused tokens without touching request limits.
    - If delta > 0 (actual > reserved): records additional tokens consumed.
    """
    if delta == 0:
        return
    now = now or datetime.utcnow()
    if delta < 0:
        # Refund unused tokens (limits_checked=() ensures request limits are not altered)
        release_time_window_quota(key_id, tokens=abs(delta), limits_checked=(), now=now)
    else:
        # Add additional tokens to active token window counters
        for limit_type in ("tpm", "tpd", "tpmon"):
            usage_key, ttl = get_window_key_and_ttl(key_id, limit_type, now)
            val = redis_client.incrby(usage_key, delta)
            if val == delta:
                redis_client.expire(usage_key, ttl)


def claim_runtime_quota(runtime_key: str, tokens: int = 0) -> tuple[bool, str | None]:
    """Backward-compatible alias for simple callers."""
    return True, None


def hget(key: str, field: str) -> str | None:
    return redis_client.hget(key, field)


def hget_many(key: str, fields: list[str]) -> list[str | None]:
    return list(redis_client.hmget(key, fields))


def hgetall(key: str) -> dict[str, str]:
    return dict(redis_client.hgetall(key))


def hexists(key: str, field: str) -> bool:
    return bool(redis_client.hexists(key, field))


def hdelete(key: str, *fields: str) -> int:
    return int(redis_client.hdel(key, *fields))


def hincrby(key: str, field: str, amount: int = 1) -> int:
    """Atomically increment an integer field in a Redis hash."""
    return int(redis_client.hincrby(key, field, amount))


def hkeys(key: str) -> list[str]:
    return list(redis_client.hkeys(key))


def hvalues(key: str) -> list[str]:
    return list(redis_client.hvals(key))


# Sets
def sadd(key: str, *members: str) -> int:
    """Add members to a Redis set; return the number of new members."""
    return int(redis_client.sadd(key, *members))


def smembers(key: str) -> set[str]:
    return set(redis_client.smembers(key))


def sismember(key: str, member: str) -> bool:
    return bool(redis_client.sismember(key, member))


def srem(key: str, *members: str) -> int:
    return int(redis_client.srem(key, *members))


def scard(key: str) -> int:
    return int(redis_client.scard(key))


# Counters
def increment(key: str, amount: int = 1) -> int:
    return int(redis_client.incrby(key, amount))


def decrement(key: str, amount: int = 1) -> int:
    return int(redis_client.decrby(key, amount))


# Key discovery and atomic grouping
def scan_keys(pattern: str = "*", count: int = 100) -> list[str]:
    return list(redis_client.scan_iter(match=pattern, count=count))


def flush_database() -> bool:
    """Delete every key in the selected Redis database. Use with caution."""
    return bool(redis_client.flushdb())


def pipeline():
    """Return a Redis pipeline for grouping commands atomically."""
    return redis_client.pipeline()
