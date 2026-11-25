from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.core.auth import generate_api_key
from agent.db.session import get_session
from agent.models import User
from agent.schemas.users import UserCreate, UserCreated

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserCreated, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate, session: AsyncSession = Depends(get_session)
) -> UserCreated:
    existing = await session.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Email already registered")
    token, salt, key_hash = generate_api_key()
    user = User(
        name=payload.name,
        email=payload.email,
        timezone=payload.timezone,
        api_key_salt=salt,
        api_key_hash=key_hash,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return UserCreated(
        id=user.id,
        name=user.name,
        email=user.email,
        api_key=token,
    )
