from src.helper.sql import get_all_keys
from src.helper.redis import hset, hset_many, sadd, smembers, get_key, set_key, increment, exists, hgetall
import json
from datetime import datetime
from src.models.runtime import runtime

def startup():
    try:
        keys = get_all_keys()
        provider_set = {}
        for i in keys:
            key = json.loads(i.model_dump_json())
            provider = key.get("provider")
            key["loaded_at"] = datetime.now().strftime("%Y-%m-%d--%H:%M:%S")
            # print(f"Loading key {key}\n")
            hset_many(f"{provider}-key:{key.get('id')}", key)
            if provider not in provider_set:
                provider_set[provider] = [f"{provider}-key:{key.get('id')}"]
            else:
                provider_set[provider].append(f"{provider}-key:{key.get('id')}")
        # print(f"Loaded keys into Redis: {provider_set}")
        for key,value in provider_set.items():
            # print(f"Adding provider {key} with keys {value} to Redis set")
            sadd(key, *value)
        get_key_from_redis("Serper")
    except Exception as e:
        raise RuntimeError(f"Error during startup: {e}") from e

def set_runtime(key: str):
    key_info = hgetall(key)
    # print("key info :",key_info, "for ",key)
    if key_info['key_type'] == 'api_call':
        key_runtime_set = runtime().model_dump(mode="json")
        # print("model ",key_runtime_set)
        key_runtime_set['rpm'] = key_info.get('rpm')
        key_runtime_set['rpd'] = key_info.get('rpd')
        key_runtime_set['rpmon'] = key_info.get("rpmon")
        for i in list(key_runtime_set):
            if key_runtime_set[i] == None or key_runtime_set[i] == 'None':
                del key_runtime_set[i]
        # print(key)
        a = hset_many(key+"-runtime",key_runtime_set)
        # print(a)
        # print(exists("Serper-key:k-vl226d7b-runtime"))

    else:
        key_runtime_set = runtime().model_dump(mode="json")
        # print("model ",key_runtime_set)
        key_runtime_set['rpm'] = key_info.get('rpm')
        key_runtime_set['rpd'] = key_info.get('rpd')
        key_runtime_set['rpmon'] = key_info.get("rpmon")
        key_runtime_set['tpm'] = key_info.get('tpm')
        key_runtime_set['tpd'] = key_info.get('tpd')
        key_runtime_set['tpmon'] = key_info.get('tpmon')

        for i in list(key_runtime_set):
            if key_runtime_set[i] == None or key_runtime_set[i] == 'None':
                del key_runtime_set[i]
        # print(key_runtime_set)
        hset_many(key+"-runtime",key_runtime_set)

REQUEST_LIMITS = ("rpm", "rpd", "rpmon")
TOKEN_LIMITS = ("tpm", "tpd", "tpmon")


def _has_capacity(key_runtime: dict[str, str], fields: tuple[str, ...], amount: int) -> bool:
    for field in fields:
        value = key_runtime.get(field)
        if value not in (None, "", "None") and int(value) < amount:
            return False
    return True


def _consume_capacity(key: str, key_runtime: dict[str, str], fields: tuple[str, ...], amount: int) -> None:
    updates = {}
    for field in fields:
        value = key_runtime.get(field)
        if value not in (None, "", "None"):
            updates[field] = int(value) - amount
    if updates:
        hset_many(f"{key}-runtime", updates)


def rule_for_api(key_runtime: dict[str, str], key: str):
    if not _has_capacity(key_runtime, REQUEST_LIMITS, 1):
        return None
    _consume_capacity(key, key_runtime, REQUEST_LIMITS, 1)
    hset(f"{key}-runtime", "last_used", datetime.now().strftime("%Y-%m-%d--%H:%M:%S"))
    return hgetall(key).get("api_key")


def rule_for_llm(key_runtime: dict[str, str], key: str, tokens: int):
    if not _has_capacity(key_runtime, REQUEST_LIMITS, 1):
        return None
    if tokens > 0 and not _has_capacity(key_runtime, TOKEN_LIMITS, tokens):
        return None

    _consume_capacity(key, key_runtime, REQUEST_LIMITS, 1)
    if tokens > 0:
        _consume_capacity(key, key_runtime, TOKEN_LIMITS, tokens)
    hset(f"{key}-runtime", "last_used", datetime.now().strftime("%Y-%m-%d--%H:%M:%S"))
    return hgetall(key).get("api_key")


def select_get_key(key: str, tokens: int = 0):
    key_info = hgetall(key)
    if not key_info:
        return None

    if key_info['key_type'] == "api_call":
        key_runtime = hgetall(key+'-runtime')
        return rule_for_api(key_runtime, key)

    if key_info['key_type'] == "llm_call":
        key_runtime = hgetall(key+'-runtime')
        return rule_for_llm(key_runtime, key, tokens)

    return None



def get_key_from_redis(provider: str, tokens: int = 0):
    try:
        pos = get_key(provider+"-count")
        if pos is None:
            pos = 0
            set_key(provider+"-count", pos)
        else:
            pos = increment(provider+"-count", 1)

        # Redis sets are unordered; sorting keeps round-robin selection stable.
        keys = sorted(smembers(provider))
        if not keys:
            print(f"No keys found for provider {provider}")
            return None

        start_index = pos % len(keys)
        for offset in range(len(keys)):
            candidate_key = keys[(start_index + offset) % len(keys)]
            runtime_key = f"{candidate_key}-runtime"

            if not exists(runtime_key):
                set_runtime(candidate_key)

            api_auth = select_get_key(candidate_key, tokens=tokens)
            if api_auth is not None:
                return api_auth

        print(f"All keys for provider {provider} are exhausted")
        return None


    except Exception as e:
        print(f"Error retrieving keys for provider {provider}: {e}")
        return "check logs for error"
