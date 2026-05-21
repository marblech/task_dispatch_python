from __future__ import annotations

from typing import Optional

from sqlalchemy import Integer, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UserTable(Base):
    __tablename__ = "usertable"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    user_pwd: Mapped[str] = mapped_column(Text, nullable=False)
    salt: Mapped[Optional[str]] = mapped_column(Text, default="")
    add_time: Mapped[Optional[str]] = mapped_column(Text)
    update_time: Mapped[Optional[str]] = mapped_column(Text)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "user_pwd": self.user_pwd,
            "salt": self.salt,
            "add_time": self.add_time,
            "update_time": self.update_time,
        }
