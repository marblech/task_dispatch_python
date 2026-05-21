from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Any, Dict
import json

# 复用你现有的 ORM 实体
from .process import TaskConfig, Point, Camera


def _to_int(v) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except Exception:
        return None


def _to_float(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except Exception:
        return None


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


@dataclass
class PointDTO:
    x: int
    y: int

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "PointDTO":
        return PointDTO(
            x=int(data.get("x", 0)),
            y=int(data.get("y", 0)),
        )


@dataclass
class CameraDTO:
    cameratype: Optional[int] = None
    pan: Optional[float] = None
    tilt: Optional[float] = None
    zoom: Optional[float] = None
    cmos: Optional[float] = None
    minfocus: Optional[float] = None

    deviceurl: Optional[str] = None
    user: Optional[str] = None
    password: Optional[str] = None
    deviceid: Optional[str] = None
    ip: Optional[str] = None

    # 原始 JSON 中还可能有 id、videoCameraLinkageActionId 等字段，这里按需忽略

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "CameraDTO":
        return CameraDTO(
            cameratype=_to_int(data.get("cameratype")),
            pan=_to_float(data.get("pan")),
            tilt=_to_float(data.get("tilt")),
            zoom=_to_float(data.get("zoom")),
            cmos=_to_float(data.get("cmos")),
            minfocus=_to_float(data.get("minfocus")),
            deviceurl=(data.get("deviceurl") or data.get("deviceUrl")),
            user=data.get("camUser"),
            password=data.get("camPassword"),
            deviceid=(data.get("deviceid") or data.get("deviceId")),
            ip=data.get("camIp"),
        )


@dataclass
class TaskDTO:
    id: str
    taskname: str

    createBy: Optional[str] = None
    createTime: Optional[datetime] = None
    updateBy: Optional[str] = None
    updateTime: Optional[datetime] = None

    port: Optional[int] = None
    pid: Optional[str] = None
    url: Optional[str] = None
    status: Optional[int] = None
    action: Optional[int] = None

    region: List[PointDTO] = field(default_factory=list)
    camera: List[CameraDTO] = field(default_factory=list)

    @staticmethod
    def _parse_region(region_raw: Any) -> List[PointDTO]:
        # region 既可能是字符串（内含 JSON 数组），也可能就是列表
        points = []
        if isinstance(region_raw, str):
            try:
                region_list = json.loads(region_raw) or []
            except Exception:
                region_list = []
        elif isinstance(region_raw, list):
            region_list = region_raw
        else:
            region_list = []

        for p in region_list:
            points.append(PointDTO.from_dict(p))
        return points

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "TaskDTO":
        return TaskDTO(
            id=str(data.get("id")) if data.get("id") is not None else "",
            taskname=data.get("taskname", ""),

            createBy=data.get("createBy"),
            createTime=_parse_dt(data.get("createTime")),
            updateBy=data.get("updateBy"),
            updateTime=_parse_dt(data.get("updateTime")),

            port=_to_int(data.get("port")),
            pid=str(data.get("pid")) if data.get("pid") not in (None, "") else None,
            url=data.get("url"),
            status=_to_int(data.get("status")),
            action=_to_int(data.get("action")),

            region=TaskDTO._parse_region(data.get("region")),
            camera=[CameraDTO.from_dict(c) for c in (data.get("camera") or [])],
        )

    def to_orm(self) -> TaskConfig:
        """
        转换为 SQLAlchemy ORM 实体（TaskConfig + 子表 Point/Camera）。
        注意：只是构建对象，未入库。需要使用 Session.add()/commit() 保存。
        """
        task = TaskConfig(
            id=self.id,
            taskname=self.taskname,

            create_by=self.createBy,
            create_time=self.createTime,
            update_by=self.updateBy,
            update_time=self.updateTime,

            port=self.port,
            pid=self.pid,
            url=self.url,
            status=self.status,
            action=self.action,
        )
        
        task.region = [
            Point(x=p.x, y=p.y, order_index=i) for i, p in enumerate(self.region)
        ]

        task.cameras = [
            Camera(
                cameratype=c.cameratype,
                pan=c.pan,
                tilt=c.tilt,
                zoom=c.zoom,
                cmos=c.cmos,
                minfocus=c.minfocus,
                deviceurl=c.deviceurl,
                user=c.user,
                password=c.password,
                deviceid=c.deviceid,
                ip=c.ip,
            )
            for c in self.camera
        ]

        return task


@dataclass
class ResponseEnvelope:
    success: bool
    message: str
    code: int
    count: int
    result: List[TaskDTO] = field(default_factory=list)
    timestamp: Optional[int] = None

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "ResponseEnvelope":
        return ResponseEnvelope(
            success=bool(data.get("success")),
            message=str(data.get("message", "")),
            code=int(data.get("code", 0)),
            count=int(data.get("count", 0)),
            result=[TaskDTO.from_dict(x) for x in (data.get("result") or [])],
            timestamp=_to_int(data.get("timestamp")),
        )

    def to_orm_tasks(self) -> List[TaskConfig]:
        return [t.to_orm() for t in self.result]