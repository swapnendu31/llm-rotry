import os
import secrets
from typing import Callable, Iterable
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

LOCAL_IPS = {"127.0.0.1", "::1", "localhost", "testclient"}
security = HTTPBasic()


def get_client_ip(request: Request) -> str:
    """
    Extract the effective client IP address.
    If the direct client is a local proxy and X-Forwarded-For is provided,
    check the original client IP to prevent external proxy bypass.
    """
    if not request.client:
        return "127.0.0.1"

    direct_host = request.client.host
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for and direct_host in {"127.0.0.1", "::1", "localhost", "testclient"}:
        client_candidate = forwarded_for.split(",")[0].strip()
        if client_candidate:
            return client_candidate

    return direct_host


def is_local_ip(ip: str) -> bool:
    """Check if the provided IP or hostname corresponds to localhost."""
    return ip in LOCAL_IPS


def verify_local_client(request: Request) -> None:
    """
    Verify that the incoming request is originating from localhost (127.0.0.1).
    Raises HTTP 403 Forbidden if accessed from an external IP.
    """
    client_ip = get_client_ip(request)
    if not is_local_ip(client_ip):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: This endpoint is only accessible locally (127.0.0.1).",
        )


def verify_admin_basic_auth(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    """
    Verify HTTP Basic Authentication against configured admin credentials in .env.
    Raises HTTP 401 Unauthorized if invalid or missing.
    """
    correct_username = os.getenv("DASHBOARD_USERNAME", "admin")
    correct_password = os.getenv("DASHBOARD_PASSWORD", "admin")

    is_correct_user = secrets.compare_digest(
        credentials.username.encode("utf-8"),
        correct_username.encode("utf-8"),
    )
    is_correct_password = secrets.compare_digest(
        credentials.password.encode("utf-8"),
        correct_password.encode("utf-8"),
    )

    if not (is_correct_user and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def verify_auth_key(request: Request) -> str:
    """
    Verify the pre-shared secret AUTH_KEY for runtime endpoints (/acquire, /proxy).
    Accepts the auth key from:
      - Header 'X-Auth-Key: <key>'
      - Header 'X-API-Key: <key>'
      - Header 'Authorization: Bearer <key>' or 'Authorization: <key>'
    """
    configured_key = os.getenv("AUTH_KEY", "rotator_secret_key_123")

    auth_header = request.headers.get("authorization")
    token = None
    if auth_header:
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
        else:
            token = auth_header.strip()

    provided_key = (
        request.headers.get("x-auth-key")
        or request.headers.get("x-api-key")
        or token
    )

    if not provided_key or not secrets.compare_digest(
        provided_key.encode("utf-8"), configured_key.encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Auth Key. Pass via 'X-Auth-Key', 'X-API-Key', or 'Authorization: Bearer <key>'.",
        )
    return provided_key


def verify_admin_local_access(
    request: Request,
    credentials: HTTPBasicCredentials = Depends(security),
) -> str:
    """
    Double-layer protection: Enforces both local-only IP access (127.0.0.1)
    and valid admin Basic Auth.
    """
    verify_local_client(request)
    return verify_admin_basic_auth(credentials)


def check_allowed_origin(allowed_origins: Iterable[str] | None = None) -> Callable[[Request], None]:
    """
    Factory dependency to verify request Origin or Referer header against an allowed list.
    """
    def dependency(request: Request) -> None:
        origin = request.headers.get("origin") or request.headers.get("referer")
        if not origin:
            return  # Direct non-browser requests or same-origin without origin header
        if allowed_origins is not None:
            if not any(origin.startswith(allowed) for allowed in allowed_origins):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Forbidden: Origin '{origin}' is not allowed.",
                )
    return dependency
