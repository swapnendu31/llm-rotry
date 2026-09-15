from pydantic import BaseModel, Field
from datetime import datetime


class Runtime(BaseModel):
    """Short-lived operational metadata about a key, separate from usage counters."""

    key_id: str
    last_used: str | None = None
    cooldown_until: str | None = None
    failure_count: int = Field(default=0, ge=0)

