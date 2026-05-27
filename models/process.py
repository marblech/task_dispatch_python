from __future__ import annotations

import json
from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    Integer,
    String,
    Float,
    Text,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# 可选：保留你之前的全局变量
global task_list
task_list = []


class Base(DeclarativeBase):
    pass


class TaskConfig(Base):
    __tablename__ = "tasktable"

    # 业务里提供了字符串 id，因此这里用字符串主键
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    taskname: Mapped[str] = mapped_column(String(100), nullable=False)

    create_by: Mapped[Optional[str]] = mapped_column(String(50))
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    update_by: Mapped[Optional[str]] = mapped_column(String(50))
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime)

    port: Mapped[Optional[int]] = mapped_column(Integer)
    pid: Mapped[Optional[str]] = mapped_column(String(128))
    url: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[Optional[int]] = mapped_column(Integer)
    action: Mapped[Optional[int]] = mapped_column(Integer)
    
    region_str: Mapped[Optional[str]] = mapped_column(String(5000))
    
    cameras_str: Mapped[Optional[str]] = mapped_column(String(1000))
    
    resnet_file: Mapped[Optional[str]] = mapped_column(String(1000))
    yolo_file: Mapped[Optional[str]] = mapped_column(String(1000))
    ini_file: Mapped[Optional[str]] = mapped_column(String(1000))
    
    cam1_username: Mapped[Optional[str]] = mapped_column(String(1000))
    cam1_password: Mapped[Optional[str]] = mapped_column(String(1000))
    cam1_ip: Mapped[Optional[str]] = mapped_column(String(1000))
    udp_port: Mapped[Optional[int]] = mapped_column(Integer)
    cam2_username: Mapped[Optional[str]] = mapped_column(String(1000))
    cam2_password: Mapped[Optional[str]] = mapped_column(String(1000))
    cam2_ip: Mapped[Optional[str]] = mapped_column(String(1000))
    
    cam1_type: Mapped[Optional[int]] = mapped_column(Integer)
    cam1_source_url: Mapped[Optional[str]] = mapped_column(String(1000))
    cam2_type: Mapped[Optional[int]] = mapped_column(Integer)
    cam1_id: Mapped[str] = mapped_column(String(100))
    cam2_id: Mapped[str] = mapped_column(String(100))
    event_port: Mapped[Optional[int]] = mapped_column(Integer)
    test_mode: Mapped[Optional[int]] = mapped_column(Integer)
    log_file: Mapped[Optional[str]] = mapped_column(String(1000))
    
    # region: Mapped[Optional[str]] = mapped_column(String(5000))
    
    # cameras: Mapped[Optional[str]] = mapped_column(String(1000))

    # 关联：一个任务对应多边形点集合、多个摄像头
    # region: Mapped[List["Point"]] = relationship(
        # back_populates="task",
        # cascade="all, delete-orphan",
        # order_by="Point.order_index",
    # )
    # cameras: Mapped[List["Camera"]] = relationship(
        # back_populates="task",
        # cascade="all, delete-orphan",
    # )

    @staticmethod
    def _parse_dt(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        # 兼容 "YYYY-MM-DD HH:MM:SS"
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None

    @staticmethod
    def _to_int(v) -> Optional[int]:
        if v is None or v == "":
            return None
        try:
            return int(v)
        except Exception:
            return None

    @staticmethod
    def _to_float(v) -> Optional[float]:
        if v is None or v == "":
            return None
        try:
            return float(v)
        except Exception:
            return None
       
    @staticmethod
    def from_dict(data: dict) -> "TaskConfig":
        """
        从接口 JSON 构建 TaskConfig 实体（含子表 Point、Camera）
        兼容 region 为字符串(JSON)或列表；兼容 deviceurl/deviceUrl、deviceid/deviceId 键名差异。
        """
        task = TaskConfig(
            id=str(data.get("id")) if data.get("id") is not None else "",
            taskname=data.get("taskname", ""),

            create_by=data.get("createBy"),
            create_time=TaskConfig._parse_dt(data.get("createTime")),
            update_by=data.get("updateBy"),
            update_time=TaskConfig._parse_dt(data.get("updateTime")),
            cam1_source_url=data.get("cam1_source_url"),
            test_mode=TaskConfig._to_int(data.get("test_mode")),

            port=TaskConfig._to_int(data.get("port")),
            pid=str(data.get("pid")) if data.get("pid") not in (None, "") else None,
            url=data.get("url"),
            status=TaskConfig._to_int(data.get("status")),
            action=TaskConfig._to_int(data.get("action")),
            region_str = str(data.get("region")),
            cameras_str = str(data.get("camera"))
        )
        
        
  
        # region 既可能是字符串（内含 JSON），也可能是直接的列表
        region_raw = data.get("region")
        region_list = []
        if isinstance(region_raw, str):
            try:
                region_list = json.loads(region_raw) or []
            except Exception:
                region_list = []
        elif isinstance(region_raw, list):
            region_list = region_raw

        task.region = [
            Point(
                x=int(p.get("x", 0)),
                y=int(p.get("y", 0)),
                order_index=i,
            )
            for i, p in enumerate(region_list)
        ]

        cam_list = data.get("camera") or []
        task.cameras = [
            Camera(
                id = TaskConfig._to_int(c.get("id")),
                cameratype=TaskConfig._to_int(c.get("cameratype")),
                pan=TaskConfig._to_float(c.get("pan")),
                tilt=TaskConfig._to_float(c.get("tilt")),
                zoom=TaskConfig._to_float(c.get("zoom")),
                cmos=TaskConfig._to_float(c.get("cmos")),
                minfocus=TaskConfig._to_float(c.get("minfocus")),
                deviceurl=(c.get("deviceurl") or c.get("deviceUrl")),
                user=c.get("camUser"),
                password=c.get("camPassword"),
                ip=c.get("camIp"),
                deviceid=(c.get("deviceid") or c.get("deviceId")),
            )
            for c in cam_list
        ]

        return task


class Point(Base):
    __tablename__ = "task_region_point"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # task_id: Mapped[str] = mapped_column(
    #     ForeignKey("tasktable.id", ondelete="CASCADE"),
    #     index=True,
    #     nullable=False,
    # )
    x: Mapped[int] = mapped_column(Integer, nullable=False)
    y: Mapped[int] = mapped_column(Integer, nullable=False)
    # 为了保持多边形点顺序
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # task: Mapped["TaskConfig"] = relationship(back_populates="region")


class Camera(Base):
    __tablename__ = "camera"

    id: Mapped[int] = mapped_column(String, primary_key=True, autoincrement=True)
    # task_id: Mapped[str] = mapped_column(
    #     ForeignKey("tasktable.id", ondelete="CASCADE"),
    #     index=True,
    #     nullable=False,
    # )

    cameratype: Mapped[Optional[int]] = mapped_column(Integer)
    pan: Mapped[Optional[float]] = mapped_column(Float)
    tilt: Mapped[Optional[float]] = mapped_column(Float)
    zoom: Mapped[Optional[float]] = mapped_column(Float)
    cmos: Mapped[Optional[float]] = mapped_column(Float)
    minfocus: Mapped[Optional[float]] = mapped_column(Float)
    ip: Mapped[Optional[str]] = mapped_column(String(100))
    
    deviceurl: Mapped[Optional[str]] = mapped_column(String(255))
    user: Mapped[Optional[str]] = mapped_column(String(100))
    password: Mapped[Optional[str]] = mapped_column(String(100))
    deviceid: Mapped[Optional[str]] = mapped_column(String(100))

    # task: Mapped["TaskConfig"] = relationship(back_populates="cameras")