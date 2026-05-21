from __future__ import annotations

import json
from datetime import datetime
from typing import Optional, List

from sqlalchemy import Integer, Text, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# 可选：保留你之前的全局变量
global task_list
task_list = []


class Base(DeclarativeBase):
    pass



class TaskReturn(Base):
    __tablename__ = 'task_return'
    
    pid: Mapped[str] = mapped_column(String(128), primary_key=True)
    id: Mapped[int] = mapped_column(Integer)
    camId:Mapped[str] = mapped_column(String(128))
    stream_url: Mapped[str] = mapped_column(Text)
    stream_port: Mapped[int] = mapped_column(Integer)  
    event_port: Mapped[int] = mapped_column(Integer)  
    
    def to_dict(self):
        return {
            "pid": self.pid,
            "camId": self.camId,
            "id": self.id,
            "arStreamUrl": self.stream_url,
            "arEventPort": self.event_port,
            "arStreamPort": self.stream_port,
            "stream_url": self.stream_url,
            "stream_port": self.stream_port,
            "event_port": self.event_port           
        }