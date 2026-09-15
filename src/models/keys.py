from pydantic import BaseModel,Field, model_validator, PrivateAttr
from typing import Optional,Any
import uuid
from enum import Enum
from datetime import datetime

class Key_Type(str, Enum):
    API_CALL = "api_call"
    LLM_CALL = "llm_call"

class RPM(BaseModel):
    rpm : Optional[int] = Field(default=None, description="The number of requests per minute")
    burst : Optional[int] = Field(description="The number of requests that can be made in a burst",default=None)
    @model_validator(mode="after")
    def brust_check(self):
        if self.burst is not None and self.rpm is not None and self.burst > self.rpm:
            raise ValueError("Burst cannot be greater than RPM")
        return self


class RPD(BaseModel):
    rpd : Optional[int] = Field(default=None, description="The number of requests per day")
    burst : Optional[int] = Field(description="The number of requests tha t can be made in a burst",default=None)

    @model_validator(mode="after")
    def brust_check(self):
        if self.burst is not None and self.rpd is not None and self.burst > self.rpd:
            raise ValueError("Burst cannot be greater than RPD")
        return self

class TPD(BaseModel):
    tpd : Optional[int] = Field(default=None, description="The number of tokens per day")
    burst : Optional[int] = Field(description="The number of tokens that can be used in a burst",default=None)

    @model_validator(mode="after")
    def brust_check(self):
        if self.burst is not None and self.tpd is not None and self.burst > self.tpd:
            raise ValueError("Burst cannot be greater than TPD")
        return self

class TPM(BaseModel):
    tpm : Optional[int] = Field(default=None, description="The number of tokens per minute")
    burst : Optional[int] = Field(description="The number of tokens that can be used in a burst",default=None)

    @model_validator(mode="after")
    def brust_check(self):
        if self.burst is not None and self.tpm is not None and self.burst > self.tpm:
            raise ValueError("Burst cannot be greater than TPM")
        return self

class Status(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class Keys(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Database ID")
    key_type : Key_Type = Field(description="The type of the key", default=Key_Type.LLM_CALL)
    api_url : str = Field(description="Api endpoint URL")
    provider : str = Field(description="The provider of the key")
    account_name : str = Field(description="The account name associated with the key")
    api_key : str = Field(description="The API key")            
    rpmon : Optional[int] = Field(description="The number of requests per month", default=None)
    rpm : Optional[int] = Field(description="The number of requests per minute", default=None)
    rpd : Optional[int] = Field(description="The request limits for the key per day", default=None)
    tpd : Optional[int] = Field(description="The token limits for the key per day", default=None)
    tpm : Optional[int] = Field(description="The token limits for the key per minute", default=None)
    tpmon : Optional[int] = Field(description="The token limits for the key per month", default=None)
    _reg_date : datetime = PrivateAttr(default_factory=datetime.now)
    status : Status = Field(description="Status of the key", default=Status.ACTIVE)


    @model_validator(mode="before")
    @classmethod
    def clean_field(cls, values: Any):
        def _clean_single(v: dict[str, Any]):
            if v.get("key_type") == "api_call":
                v.pop("tpd", None)
                v.pop("tpm", None)
                v.pop("tpmon", None)
            return v

        if isinstance(values, dict):
            return _clean_single(values)
        elif isinstance(values, list):
            return [_clean_single(v) if isinstance(v, dict) else v for v in values]
        return values
