from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


def _to_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except Exception:
        return None


@dataclass
class ArStreamConfig:
    arStreamUrl: Optional[str] = None
    arEventPort: Optional[int] = None
    speedValue: Optional[int] = None
    yuntaiType: Optional[int] = None
    camPort: Optional[int] = None
    camPassword: Optional[str] = None
    camName: Optional[str] = None
    camId: Optional[str] = None
    arStreamSwitch: Optional[int] = None
    modifyPerson: Optional[str] = None
    arStreamPort: Optional[int] = None
    modifyTime: Optional[int] = None
    camIp: Optional[str] = None
    arStreamStatus: Optional[int] = None
    camAccount: Optional[str] = None

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "ArStreamConfig":
        return ArStreamConfig(
            arStreamUrl=data.get("arStreamUrl"),
            arEventPort=_to_int(data.get("arEventPort")),
            speedValue=_to_int(data.get("speedValue")),
            yuntaiType=_to_int(data.get("yuntaiType")),
            camPort=_to_int(data.get("camPort")),
            camPassword=data.get("camPassword"),
            camName=data.get("camName"),
            camId=data.get("camId"),
            arStreamSwitch=_to_int(data.get("arStreamSwitch")),
            modifyPerson=data.get("modifyPerson"),
            arStreamPort=_to_int(data.get("arStreamPort")),
            modifyTime=_to_int(data.get("modifyTime")),
            camIp=data.get("camIp"),
            arStreamStatus=_to_int(data.get("arStreamStatus")),
            camAccount=data.get("camAccount"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "arStreamUrl": self.arStreamUrl,
            "arEventPort": self.arEventPort,
            "speedValue": self.speedValue,
            "yuntaiType": self.yuntaiType,
            "camPort": self.camPort,
            "camPassword": self.camPassword,
            "camName": self.camName,
            "camId": self.camId,
            "arStreamSwitch": self.arStreamSwitch,
            "modifyPerson": self.modifyPerson,
            "arStreamPort": self.arStreamPort,
            "modifyTime": self.modifyTime,
            "camIp": self.camIp,
            "arStreamStatus": self.arStreamStatus,
            "camAccount": self.camAccount,
        }
