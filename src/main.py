from pathlib import Path
from typing import Optional
from fastapi import Depends, FastAPI, Request
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
from contextlib import asynccontextmanager
import redis
from src.controller.controller_key import key_router
from src.controller.controller_run import runtime_router
from src.helper.sql import check_status
from src.helper.redis import ping as redis_ping
from src.helper.security import (
    verify_admin_local_access,
    verify_auth_key,
    verify_local_client,
)
from src.services.engine import startup

STATIC_DIR = Path(__file__).resolve().parent / "static"

@asynccontextmanager
async def lifespan_check(app: FastAPI):
    """
    Lifespan context manager for FastAPI application. This function checks the availability of Redis and SQLite databases during
    the startup phase of the application. If either database is unavailable, it raises an exception, preventing the application 
    from starting.
    """

    try:

        if not isinstance(redis_ping(), bool) and redis_ping() is not True:
            raise ValueError("Error: Redis is not available or cannot execute queries.")
        if check_status() == False:
            raise ValueError("Error: SQLite is not available or cannot execute queries.")

        startup()
        print("Application is started ready.")
        yield

        print("shutting down")

    except Exception as e:
        raise Exception(f"Error on startup: {e}")



app = FastAPI(
    title="LLM-rotry",
    description="API rotory for llm models",
    version="0.0.1",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan_check,
)


# Local-only API Documentation (Accessible only via 127.0.0.1 / localhost)
@app.get("/docs", include_in_schema=False, dependencies=[Depends(verify_local_client)])
async def get_swagger_docs():
    return get_swagger_ui_html(openapi_url="/openapi.json", title="LLM-rotry - Swagger UI")


@app.get("/redoc", include_in_schema=False, dependencies=[Depends(verify_local_client)])
async def get_redoc_docs():
    return get_redoc_html(openapi_url="/openapi.json", title="LLM-rotry - ReDoc")


@app.get("/openapi.json", include_in_schema=False, dependencies=[Depends(verify_local_client)])
async def get_openapi_schema(request: Request):
    verify_local_client(request)
    return get_openapi(title=app.title, version=app.version, routes=app.routes)


# Mount static frontend assets
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Dashboard: Requires local access (127.0.0.1) AND Admin Basic Authentication
@app.get("/", include_in_schema=False, dependencies=[Depends(verify_admin_local_access)])
@app.get("/dashboard", include_in_schema=False, dependencies=[Depends(verify_admin_local_access)])
async def serve_dashboard():
    return FileResponse(STATIC_DIR / "index.html")

app.add_api_route("/health", lambda: {"status": "ok"}, methods=["GET"])

# Key Management: Dashboard REST API restricted to local access + Admin Basic Auth
app.include_router(
    key_router,
    prefix="/keys",
    tags=["Key Management"],
    dependencies=[Depends(verify_admin_local_access)],
)

# Rotation & Proxy: Protected by Auth Key (X-Auth-Key, X-API-Key, or Authorization: Bearer <key>)
app.include_router(
    runtime_router,
    tags=["Rotation & Proxy"],
    dependencies=[Depends(verify_auth_key)],
)


