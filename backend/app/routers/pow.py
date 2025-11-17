from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.quotas import PoWValidator

router = APIRouter(prefix="/pow", tags=["pow"])


class ChallengeOut(BaseModel):
    challenge: str
    difficulty: int
    ttl: int


@router.post("/challenge", response_model=ChallengeOut)
def get_pow_challenge(pow_validator: PoWValidator = Depends(PoWValidator)) -> dict[str, int | str]:
    """
    Создает и возвращает новую PoW-задачу для клиента.
    """
    return pow_validator.get_challenge()
