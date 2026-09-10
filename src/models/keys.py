from pydantic import BaseModel,Field, model_validator, PrivateAttr
from typing import Optional,Any
from enum import Enum
from datetime import datetime

class Key_Type(str, Enum):
    API_CALL = "api_call"
    LLM_CALL = "llm_call"

class RPM(BaseModel):
    rpm : Optional[int] = Field(description="The number of requests per minute")
    burst : Optional[int] = Field(description="The number of requests that can be made in a burst",default=None)
    @model_validator(mode="after")
    def brust_check(self):
        if self.burst is not None and self.burst > self.rpm:
            raise ValueError("Burst cannot be greater than RPM")


class RPD(BaseModel):
    rpd : Optional[int] = Field(description="The number of requests per day")
    burst : Optional[int] = Field(description="The number of requests tha t can be made in a burst",default=None)

    @model_validator(mode="after")
    def brust_check(self):
        if self.burst is not None and self.burst > self.rpd:
            raise ValueError("Burst cannot be greater than RPD")

class TPD(BaseModel):
    tpd : Optional[int] = Field(description="The number of tokens per day")
    burst : Optional[int] = Field(description="The number of tokens that can be used in a burst",default=None)

    @model_validator(mode="after")
    def brust_check(self):
        if self.burst is not None and self.burst > self.tpd:
            raise ValueError("Burst cannot be greater than TPD")

class TPM(BaseModel):
    tpm : Optional[int] = Field(description="The number of tokens per minute")
    burst : Optional[int] = Field(description="The number of tokens that can be used in a burst",default=None)

    @model_validator(mode="after")
    def brust_check(self):
        if self.burst is not None and self.burst > self.tpm:
            raise ValueError("Burst cannot be greater than TPM")

class Status(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class Keys(BaseModel):
    key_type : Key_Type = Field(description="The type of the key", default=Key_Type.LLM_CALL)
    api_url : str = Field(description="Api endpoint URL")
    provider : str = Field(description="The provider of the key")
    account_name : str = Field(description="The account name associated with the key")
    api_key : str = Field(description="The API key")            
    rpm : Optional[RPM] = Field(description="The RPM limits for the key",default=None)
    rpd : Optional[RPD] = Field(description="The RPD limits for the key",default=None)
    tpd : Optional[TPD] = Field(description="The TPD limits for the key",default=None)
    tpm : Optional[TPM] = Field(description="The TPM limits for the key",default=None)
    _reg_date : str = PrivateAttr(default_factory=datetime.now())
    status : Status = Field(description="Status of the key", default=Status.ACTIVE)


    @model_validator(mode="before")
    @classmethod
    def clean_field(cls, values:Any):
        if values.get("key_type") == "api_call":
            values.pop("tpd", None)
            values.pop("tpm", None)