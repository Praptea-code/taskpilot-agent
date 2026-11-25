from fastapi import Header, HTTPException


async def get_current_user_id(x_user_id: str | None = Header(default=None)) -> int:
    if x_user_id is None:
        raise HTTPException(status_code=401, detail="X-User-Id header is required")
    try:
        return int(x_user_id)
    except ValueError as error:
        raise HTTPException(status_code=401, detail="Invalid X-User-Id header") from error
