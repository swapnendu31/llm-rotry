from pydantic import BaseModel, Field, model_validator, PrivateAttr
from datetime import datetime
from typing import Optional, Any



class runtime(BaseModel):
    rpm: Optional[int] = Field(default=None, description="Number of requests per minute its has served")
    rpd: Optional[int] = Field(default=None, description="Number of requests per day its has served")
    tpm: Optional[int] = Field(default=None, description="Number of tokens per minute its has served")
    tpd: Optional[int] = Field(default=None, description="Number of tokens per day its has served")
    tpmon: Optional[int] = Field(default=None, description="Number of tokens per month its has served")    
    rpmon: Optional[int] = Field(default=None, description="Number of requests per month its has served")
    last_used: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"), description="The last time the key was used")
    ttl: int | None = Field(default=None, description="Time to live for the key in seconds")