from datetime import datetime
import json

from src.helper.redis import (
    claim_time_window_quota,
    exists,
    get_key,
    hgetall,
    hset_many,
    increment,
    sadd,
    set_key,
    smembers,
)
from src.helper.sql import get_all_keys
from src.models.runtime import Runtime

REQUEST_LIMITS = ("rpm", "rpd", "rpmon")
TOKEN_LIMITS = ("tpm", "tpd", "tpmon")


def _extract_limits(key_info: dict[str, str], fields: tuple[str, ...]) -> dict[str, int]:
    limits: dict[str, int] = {}
    for field in fields:
        raw_val = key_info.get(field)
        if raw_val not in (None, "", "None"):
            try:
                limits[field] = int(raw_val)
            except (ValueError, TypeError):
                continue
    return limits


def startup():
    try:
        keys = get_all_keys()
        provider_set = {}
        for i in keys:
            key = json.loads(i.model_dump_json())
            provider = key.get("provider")
            key["loaded_at"] = datetime.now().strftime("%Y-%m-%d--%H:%M:%S")
            hset_many(f"{provider}-key:{key.get('id')}", key)
            if provider not in provider_set:
                provider_set[provider] = [f"{provider}-key:{key.get('id')}"]
            else:
                provider_set[provider].append(f"{provider}-key:{key.get('id')}")

        for key, value in provider_set.items():
            sadd(key, *value)
        get_key_from_redis("Serper")
    except Exception as e:
        raise RuntimeError(f"Error during startup: {e}") from e


def set_runtime(key: str):
    """Initialize lightweight runtime metadata for a candidate key."""
    key_info = hgetall(key)
    key_id = key_info.get("id") or key.split(":")[-1]
    runtime_data = Runtime(key_id=key_id).model_dump(mode="json", exclude_none=True)
    hset_many(f"{key}-runtime", runtime_data)


def rule_for_api(key: str, key_info: dict[str, str] | None = None) -> str | None:
    info = key_info or hgetall(key)
    if not info:
        return None

    limits = _extract_limits(info, REQUEST_LIMITS)
    key_id = info.get("id") or key.split(":")[-1]

    allowed, _ = claim_time_window_quota(
        runtime_key=f"{key}-runtime",
        key_id=key_id,
        limits=limits,
        tokens=0,
    )
    if not allowed:
        return None
    return info.get("api_key")


def rule_for_llm(key: str, tokens: int, key_info: dict[str, str] | None = None) -> str | None:
    if tokens < 0:
        raise ValueError("tokens cannot be negative")

    info = key_info or hgetall(key)
    if not info:
        return None

    limits = _extract_limits(info, REQUEST_LIMITS + TOKEN_LIMITS)
    key_id = info.get("id") or key.split(":")[-1]

    allowed, _ = claim_time_window_quota(
        runtime_key=f"{key}-runtime",
        key_id=key_id,
        limits=limits,
        tokens=tokens,
    )
    if not allowed:
        return None
    return info.get("api_key")


def select_get_key(key: str, tokens: int = 0):
    key_info = hgetall(key)
    if not key_info:
        return None

    key_type = key_info.get("key_type")
    if key_type == "api_call":
        return rule_for_api(key, key_info=key_info)

    if key_type == "llm_call":
        return rule_for_llm(key, tokens=tokens, key_info=key_info)

    return None




def set_cooldown(candidate_key: str, seconds: int = 60) -> None:
    """Temporarily cool down a key that received a 429."""
    set_key(f"cooldown:{candidate_key}", "rate_limited", expire_seconds=seconds)


def get_key_record_from_redis(provider: str, tokens: int = 0) -> dict[str, str] | None:
    """
    Select an active key record for the provider, respecting cooldowns and quota limits.
    Returns dict with candidate_key, key_id, api_key, and api_url.
    """
    try:
        pos = get_key(provider + "-count")
        if pos is None:
            pos = 0
            set_key(provider + "-count", pos)
        else:
            pos = increment(provider + "-count", 1)

        keys = sorted(smembers(provider))
        if not keys:
            print(f"No keys found for provider {provider}")
            return None

        start_index = pos % len(keys)
        for offset in range(len(keys)):
            candidate_key = keys[(start_index + offset) % len(keys)]

            # Skip candidate if currently cooling down
            if exists(f"cooldown:{candidate_key}"):
                continue

            runtime_key = f"{candidate_key}-runtime"
            if not exists(runtime_key):
                set_runtime(candidate_key)

            api_auth = select_get_key(candidate_key, tokens=tokens)
            if api_auth is not None:
                info = hgetall(candidate_key)
                return {
                    "candidate_key": candidate_key,
                    "key_id": info.get("id") or candidate_key.split(":")[-1],
                    "api_key": api_auth,
                    "api_url": info.get("api_url", ""),
                    "provider": provider,
                }

        print(f"All keys for provider {provider} are exhausted")
        return None

    except Exception as e:
        print(f"Error retrieving keys for provider {provider}: {e}")
        return None


def get_key_from_redis(provider: str, tokens: int = 0) -> str | None:
    record = get_key_record_from_redis(provider, tokens=tokens)
    return record["api_key"] if record else None

