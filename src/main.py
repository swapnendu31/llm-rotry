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

STATIC_DIR = Path(__file__).resolve().parent / "static"

@asynccontextmanager
async def lifespan_check(app: FastAPI):
    """
    Lifespan context manager for FastAPI application. This function checks the availability of Redis and SQLite databases during
    the startup phase of the application. If either database is unavailable, it raises an exception, preventing the application 
    from starting.
    """

    try:

        client = redis.Redis(host='localhost', port=6379, db=0)
        a = client.ping()
        if not isinstance(a, bool):
            raise ValueError("Expected a boolean value from Redis ping")
        if a is not True:
            raise ValueError("Redis is not available.")

        if check_status() == False:
            raise ValueError("SQLite is not available or cannot execute queries.")

        print("ready for requests")
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


