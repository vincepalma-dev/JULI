"""Data route: delete everything JULI stores (see juli.data)."""

from fastapi import APIRouter, HTTPException

from juli import data
from juli.api.models import DeleteAllRequest
from juli.bus import message_bus

router = APIRouter(prefix="/data")


@router.post("/delete-all")
def delete_all(_: DeleteAllRequest) -> dict:
    """Projects, run history, workspace files, settings, and the keys and tokens in the keychain."""
    result = message_bus.delete_all(data.delete_all)
    if result is None:
        raise HTTPException(409, "A task is running. Stop it first.")
    return result
