import os
import json
from typing import Any

from redis import Redis
from redis.exceptions import RedisError


redis_client = Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    db=int(os.getenv("REDIS_DB", "0")),
    decode_responses=True,
)


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
