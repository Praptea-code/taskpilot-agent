from pydantic import BaseModel, ConfigDict

from agent.models import User


class UserCreate(BaseModel):
    name: str
    email: str
    timezone: str = "UTC"


class UserCreated(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    api_key: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    timezone: str


def to_user_read(user: User) -> UserRead:
    return UserRead(
        id=user.id,
        name=user.name,
        email=user.email,
        timezone=user.timezone,
    )
