# backend/app/schemas/auth.py

from pydantic import BaseModel, Field
from datetime import datetime

class ChallengeRequest(BaseModel):
    eth_address: str = Field(..., pattern=r"^0x[a-fA-F0-9]{40}$")

class ChallengeResponse(BaseModel):
    nonce: str
    exp: datetime

class RegisterRequest(BaseModel):
    eth_address: str = Field(..., pattern=r"^0x[a-fA-F0-9]{40}$")
    display_name: str = Field(..., min_length=1, max_length=50)
    rsa_public_spki_pem: str
    nonce: str
    signature: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"