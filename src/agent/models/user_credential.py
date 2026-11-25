from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from agent.models.base import Base, TimestampMixin


class UserCredential(TimestampMixin, Base):
    __tablename__ = "user_credentials"
    __table_args__ = (UniqueConstraint("user_id", "service", name="uq_user_credentials_service"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    service: Mapped[str] = mapped_column(String(64))
    encrypted_value: Mapped[str] = mapped_column(Text)
