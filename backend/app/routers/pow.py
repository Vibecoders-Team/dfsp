from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.quotas import PoWValidator, get_pow_validator

router = APIRouter(prefix="/pow", tags=["pow"])


class ChallengeOut(BaseModel):
    challenge: str
    difficulty: int
    ttl: int


@router.post("/challenge", response_model=ChallengeOut)
def get_pow_challenge(pow_validator: Annotated[PoWValidator, Depends(get_pow_validator)]) -> dict[str, int | str]:
    """
    Create and return a new PoW challenge for the client.
    """
    return pow_validator.get_challenge()
