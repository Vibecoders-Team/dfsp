# backend/app/repos/user_repo.py

import uuid
from sqlalchemy.orm import Session

from ..db import models as db_models
from ..schemas import auth as auth_schemas

def get_by_eth_address(db: Session, eth_address: str) -> db_models.User | None:
    """Находит пользователя по адресу Ethereum."""
    return db.query(db_models.User).filter(db_models.User.eth_address == eth_address.lower()).first()

def create(db: Session, request: auth_schemas.RegisterRequest) -> db_models.User:
    """Создаёт нового пользователя в базе данных."""
    new_user = db_models.User(
        id=uuid.uuid4(),
        eth_address=request.eth_address.lower(),
        display_name=request.display_name,
        rsa_public_spki_pem=request.rsa_public_spki_pem,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user