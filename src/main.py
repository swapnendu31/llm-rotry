from typing import Optional
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
from contextlib import asynccontextmanager
import redis
from controller.controller_key import key_router
from src.helper.sql import check_status

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


app.add_api_route("/health", lambda: {"status": "ok"}, methods=["GET"])
app.include_router(key_router, prefix="/keys", tags=["Key Management"])