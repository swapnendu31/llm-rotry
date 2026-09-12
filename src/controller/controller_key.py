from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict

from src.helper.sql import delete_keys, get_all_keys, get_key, insert_keys, update_key
from src.models.keys import Key_Type, Keys, RPM, RPD, TPD, TPM, Status


key_router = APIRouter()


class KeyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key_type: Key_Type | None = None
    api_url: str | None = None
    provider: str | None = None
    account_name: str | None = None
    api_key: str | None = None
    rpmon: RPM | None = None
    rpm: RPM | None = None
    rpd: RPD | None = None
    tpd: TPD | None = None
    tpm: TPM | None = None
    tpmon: TPM | None = None
    status: Status | None = None


class BulkDelete(BaseModel):
    ids: list[str]


def _key_response(key: Keys) -> dict[str, Any]:
    return key.model_dump(mode="json", exclude_none=True)



@key_router.post("/new_reg", status_code=status.HTTP_201_CREATED)
def new_registration(keys: Keys | list[Keys]):
    """Backward-compatible endpoint accepting one key or a list."""
    values = keys if isinstance(keys, list) else [keys]
    ids = insert_keys(values)
    return {"ids": ids, "data": [_key_response(key) for key in values]}


@key_router.get("")
def read_keys(
    provider: str | None = Query(default=None),
    key_status: Status | None = Query(default=None, alias="status"),
):
    keys = get_all_keys()
    if provider is not None:
        keys = [key for key in keys if key.provider == provider]
    if key_status is not None:
        keys = [key for key in keys if key.status == key_status]
    return [_key_response(key) for key in keys]


@key_router.get("/{key_id}")
def read_key(key_id: str):
    key = get_key(key_id)
    if key is None:
        raise HTTPException(status_code=404, detail="Key not found")
    return _key_response(key)


@key_router.patch("/{key_id}")
def update_key_by_id(key_id: str, updates: KeyUpdate):
    data = updates.model_dump(mode="json", exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    if not update_key(key_id, data):
        raise HTTPException(status_code=404, detail="Key not found")
    return _key_response(get_key(key_id))


@key_router.delete("/{key_id}")
def delete_key(key_id: str):
    if delete_keys(key_id) == 0:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"message": "Key deleted", "id": key_id}


@key_router.post("/bulk-delete")
def delete_many_keys(request: BulkDelete):
    return {"deleted": delete_keys(request.ids)}


@key_router.delete("")
def delete_all_keys(confirm: bool = Query(default=False)):
    if not confirm:
        raise HTTPException(status_code=400, detail="Pass ?confirm=true to delete all keys")
    return {"deleted": delete_keys()}


@key_router.post("/{key_id}/activate")
def activate_key(key_id: str):
    if not update_key(key_id, {"status": Status.ACTIVE.value}):
        raise HTTPException(status_code=404, detail="Key not found")
    return _key_response(get_key(key_id))


@key_router.post("/{key_id}/deactivate")
def deactivate_key(key_id: str):
    if not update_key(key_id, {"status": Status.INACTIVE.value}):
        raise HTTPException(status_code=404, detail="Key not found")
    return _key_response(get_key(key_id))
