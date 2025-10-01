# backend/app/api/auth.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..repos import user_repo
from ..schemas import auth as auth_schemas
from ..security import jwt as jwt_security
from ..services import auth_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/challenge", response_model=auth_schemas.ChallengeResponse)
def get_challenge(request: auth_schemas.ChallengeRequest):
    nonce, exp = auth_service.create_auth_challenge(request.eth_address)
    return {"nonce": nonce, "exp": exp}


@router.post("/register", response_model=auth_schemas.TokenResponse)
def register_user(
    request: auth_schemas.RegisterRequest,
    db: Session = Depends(get_db),
):
    existing_user = user_repo.get_by_eth_address(db, request.eth_address)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this Ethereum address already exists.",
        )

    is_valid = auth_service.verify_signature_and_consume_nonce(
        eth_address=request.eth_address,
        nonce=request.nonce,
        signature=request.signature,
    )
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature or expired/invalid nonce.",
        )

    new_user = auth_service.register_new_user(db, request)

    access_token = jwt_security.create_access_token(subject=new_user.id)
    refresh_token = jwt_security.create_refresh_token(subject=new_user.id)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
    }