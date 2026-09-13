from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict

runtime_router = APIRouter()


@runtime_router.get("/runtime/{key_type}")
async def get_api(key_type: str):
    """
    Get the runtime information for a specific key type.

    Args:
        key_type (str): The type of the key (e.g., "api_call", "llm_call").

    Returns:
        dict: A dictionary containing the runtime information for the specified key type.
    """
    pass