import hmac

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.core.auth import hash_api_key
from agent.models import User


async def user_id_for_api_key(session: AsyncSession, token: str) -> int | None:
    result = await session.execute(
        select(User).where(User.api_key_hash.is_not(None), User.api_key_salt.is_not(None))
    )
    for user in result.scalars():
        if user.api_key_salt is None or user.api_key_hash is None:
            continue
        candidate = hash_api_key(token, user.api_key_salt)
        if hmac.compare_digest(candidate, user.api_key_hash):
            return user.id
    return None
