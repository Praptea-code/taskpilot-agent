from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.api.deps import get_current_user_id
from agent.config import get_settings
from agent.core.credentials import encrypt_credential
from agent.db.session import get_session
from agent.models import UserCredential
from agent.schemas.credentials import CredentialCreate, CredentialRead

router = APIRouter(prefix="/users/me/credentials", tags=["credentials"])


@router.post("", response_model=CredentialRead, status_code=status.HTTP_201_CREATED)
async def save_credential(
    payload: CredentialCreate,
    session: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id),
) -> UserCredential:
    key = get_settings().credentials_key
    if not key:
        raise HTTPException(status_code=503, detail="Credentials encryption key is not set")
    result = await session.execute(
        select(UserCredential).where(
            UserCredential.user_id == user_id,
            UserCredential.service == payload.service,
        )
    )
    credential = result.scalar_one_or_none()
    encrypted = encrypt_credential(payload.value, key)
    if credential is None:
        credential = UserCredential(
            user_id=user_id,
            service=payload.service,
            encrypted_value=encrypted,
        )
        session.add(credential)
    else:
        credential.encrypted_value = encrypted
    await session.commit()
    await session.refresh(credential)
    return credential


@router.get("", response_model=list[CredentialRead])
async def list_credentials(
    session: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id),
) -> list[UserCredential]:
    result = await session.execute(
        select(UserCredential)
        .where(UserCredential.user_id == user_id)
        .order_by(UserCredential.id)
    )
    return list(result.scalars().all())
