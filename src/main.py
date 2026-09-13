from pathlib import Path
from typing import Optional
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
from contextlib import asynccontextmanager
import redis
from src.controller.controller_key import key_router
from src.helper.sql import check_status
from src.helper.redis import ping as redis_ping
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
    lifespan=lifespan_check
)


# Mount static frontend assets and serve dashboard
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", include_in_schema=False)
@app.get("/dashboard", include_in_schema=False)
async def serve_dashboard():
    return FileResponse(STATIC_DIR / "index.html")

app.add_api_route("/health", lambda: {"status": "ok"}, methods=["GET"])
app.include_router(key_router, prefix="/keys", tags=["Key Management"])

