import json
import math
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response

from src.helper.redis import record_token_consumption, release_time_window_quota
from src.services.engine import (
    get_key_from_redis,
    get_key_record_from_redis,
    set_cooldown,
)

runtime_router = APIRouter()
MAX_RETRIES = 3


def estimate_request_tokens(body_bytes: bytes, explicit_tokens: int = 0) -> int:
    """
    Estimate prompt tokens using static 4 chars/token + 5% safety margin,
    plus completion tokens (max_tokens from body or standard 1000 fallback).
    """
    if explicit_tokens > 0:
        return explicit_tokens

    if not body_bytes:
        return 0

    try:
        data = json.loads(body_bytes)
    except Exception:
        # If payload is non-JSON text, estimate purely from character count
        prompt_chars = len(body_bytes)
        return max(1, math.ceil((prompt_chars / 4.0) * 1.05))

    prompt_chars = 0
    completion_tokens = 1000

    if isinstance(data, dict):
        messages = data.get("messages")
        if isinstance(messages, list):
            for msg in messages:
                if isinstance(msg, dict):
                    content = msg.get("content")
                    if isinstance(content, str):
                        prompt_chars += len(content)
                    elif isinstance(content, list):
                        for part in content:
                            if isinstance(part, dict) and "text" in part:
                                prompt_chars += len(str(part["text"]))
        elif "prompt" in data:
            prompt = data["prompt"]
            if isinstance(prompt, str):
                prompt_chars += len(prompt)
            elif isinstance(prompt, list):
                prompt_chars += sum(len(p) for p in prompt if isinstance(p, str))

        max_tok = data.get("max_tokens") or data.get("max_completion_tokens")
        if max_tok is not None:
            try:
                completion_tokens = int(max_tok)
            except (ValueError, TypeError):
                pass

    # 4 chars per token with 5% safety margin on context
    context_tokens = math.ceil((prompt_chars / 4.0) * 1.05) if prompt_chars > 0 else 0
    return max(1, context_tokens + completion_tokens) if (prompt_chars > 0 or "messages" in data or "prompt" in data) else 0


def extract_actual_tokens(response_json: dict[str, Any]) -> int | None:
    """Extract actual total tokens from provider response usage block."""
    usage = response_json.get("usage")
    if isinstance(usage, dict):
        if usage.get("total_tokens") is not None:
            try:
                return int(usage["total_tokens"])
            except (ValueError, TypeError):
                pass
        prompt = usage.get("prompt_tokens") or 0
        completion = usage.get("completion_tokens") or 0
        if prompt or completion:
            try:
                return int(prompt) + int(completion)
            except (ValueError, TypeError):
                pass
    return None


@runtime_router.get("/acquire/{provider}")
def acquire_key(provider: str, tokens: int = Query(default=0, ge=0)):
    """API 1: Directly vend an active, non-exhausted API key for the provider."""
    api_key = get_key_from_redis(provider, tokens=tokens)
    if not api_key:
        raise HTTPException(
            status_code=429,
            detail=f"All keys for provider '{provider}' are currently exhausted or in cooldown.",
        )
    return {"provider": provider, "api_key": api_key}


@runtime_router.post("/proxy/{provider}")
@runtime_router.post("/proxy/{provider}/{subpath:path}")
async def proxy_request(
    provider: str,
    request: Request,
    subpath: str = "",
    tokens: int = Query(default=0, ge=0),
):
    """
    API 2: Smart reverse proxy gateway with:
    - 4 chars/token + 5% context estimation + completion headroom
    - Automatic token refunding on successful response
    - JSONDecodeError detection (incomplete/corrupt responses) with automatic retry
    """
    body = await request.body()
    reserved_tokens = estimate_request_tokens(body, explicit_tokens=tokens)

    last_error_detail = "Failed to complete request."

    for attempt in range(MAX_RETRIES):
        record = get_key_record_from_redis(provider, tokens=reserved_tokens)
        if not record:
            raise HTTPException(
                status_code=429,
                detail=f"All keys for provider '{provider}' are currently exhausted or in cooldown.",
            )

        target_url = record["api_url"]
        if not target_url:
            release_time_window_quota(record["key_id"], tokens=reserved_tokens)
            raise HTTPException(
                status_code=400,
                detail=f"No api_url configured for provider '{provider}'.",
            )

        if subpath:
            target_url = target_url.rstrip("/") + "/" + subpath.lstrip("/")

        forward_headers = dict(request.headers)
        forward_headers.pop("host", None)
        forward_headers["Authorization"] = f"Bearer {record['api_key']}"
        forward_headers["X-API-KEY"] = record["api_key"]

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                upstream_resp = await client.request(
                    method=request.method,
                    url=target_url,
                    headers=forward_headers,
                    content=body,
                    params=dict(request.query_params),
                )
        except httpx.RequestError as exc:
            # Network connection error before receiving response -> refund and retry next key
            release_time_window_quota(record["key_id"], tokens=reserved_tokens)
            set_cooldown(record["candidate_key"], seconds=30)
            last_error_detail = f"Upstream network error: {exc}"
            continue

        # If provider returned 429, put key on 60s cooldown, refund quota, and retry
        if upstream_resp.status_code == 429:
            set_cooldown(record["candidate_key"], seconds=60)
            release_time_window_quota(record["key_id"], tokens=reserved_tokens)
            last_error_detail = "Provider rate limit (429) hit."
            if attempt < MAX_RETRIES - 1:
                continue
            return Response(
                content=upstream_resp.content,
                status_code=429,
                headers=dict(upstream_resp.headers),
                media_type=upstream_resp.headers.get("content-type"),
            )

        # If provider returned 502/503/504 gateway crash, put key on 30s cooldown, refund, and retry
        if upstream_resp.status_code in (502, 503, 504):
            set_cooldown(record["candidate_key"], seconds=30)
            release_time_window_quota(record["key_id"], tokens=reserved_tokens)
            last_error_detail = f"Provider gateway error ({upstream_resp.status_code})."
            if attempt < MAX_RETRIES - 1:
                continue
            return Response(
                content=upstream_resp.content,
                status_code=upstream_resp.status_code,
                headers=dict(upstream_resp.headers),
                media_type=upstream_resp.headers.get("content-type"),
            )


        # Validate response JSON integrity (check for incomplete/truncated JSON)
        try:
            resp_json = json.loads(upstream_resp.content)
            is_valid_json = True
        except (json.JSONDecodeError, UnicodeDecodeError):
            is_valid_json = False

        if not is_valid_json and upstream_resp.status_code == 200:
            # Incomplete / truncated JSON received on 200 OK -> refund quota, cool down key, retry!
            release_time_window_quota(record["key_id"], tokens=reserved_tokens)
            set_cooldown(record["candidate_key"], seconds=30)
            last_error_detail = "Incomplete or malformed JSON received from provider."
            continue

        # If valid JSON, reconcile tokens: adjust Redis counters to match actual usage exactly
        if is_valid_json and reserved_tokens > 0:
            actual_tokens = extract_actual_tokens(resp_json)
            if actual_tokens is not None:
                delta = actual_tokens - reserved_tokens
                record_token_consumption(record["key_id"], delta=delta)

        # Exclude hop-by-hop headers from response back to client
        excluded_headers = {
            "content-encoding", "content-length", "transfer-encoding", "connection"
        }
        response_headers = {
            k: v for k, v in upstream_resp.headers.items() if k.lower() not in excluded_headers
        }

        return Response(
            content=upstream_resp.content,
            status_code=upstream_resp.status_code,
            headers=response_headers,
            media_type=upstream_resp.headers.get("content-type"),
        )

    # If all retry attempts failed
    raise HTTPException(status_code=502, detail=f"All retry attempts failed: {last_error_detail}")