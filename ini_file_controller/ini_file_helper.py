import configparser
from pathlib import Path
from typing import Dict, Any, Optional
import os
import shutil

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.ini"

_DEFAULT_TEMPLATE = """[cam_list]
scan=ScanCam
track=TrackCam
isdebugstream=

[ScanCam2]
id=d9ca44d7-cff4-4cdf-9782-b7c0crtyh545
#id=d9ca44d7-cff4-4cdf-9782-b7c0c0345ksf
ip=10.80.0.247
port=8000
realip=10.80.0.247
realport=8000
realusername=admin
realpwd=Hg123456
type=2
username=admin
password=Hg123456
channelid=1
streamtype=1
northangle=0
geoscope=22.755869,113.504878,22.784760,113.658963
cam_longitude=113.563544
cam_latitude=22.745222
cam_height=28.5
min_focal=4.8
cmos_len=2.8
#cmos_len=0.005714285714285714
direction=0
t_offset=0
#rtsp_url=rtspsrc location=rtsp://admin:DS123456@172.24.171.197/ch1/sub/h264/stream latency=0 ! rtph264depay ! nvv4l2decoder ! nvvidconv ! video/x-raw, format=BGRx ! videoconvert ! video/x-raw, format=BGR ! appsink sync=false
rtsp_url=rtsp://admin:Hg123456@10.80.0.247/third/h264/stream
stream_width=1920
stream_height=1080

[AISFusionParam]
cam_longitude=113.563544
cam_latitude=22.745222
cam_height=28.5
min_focal=6.6e-3
cmos_len=0.005714285714285714
cam_p=215
cam_t=5.5
cam_z=3

[ShipDetect]
fonttype=/usr/share/fonts/NotoSansCJK-Bold.ttc
name_file=/data/cam_qt_test/build-untitled-Desktop_Qt_5_12_11_GCC_64bit-Debug/coco.names
cfg_file=/data/cam_qt_test/build-untitled-Desktop_Qt_5_12_11_GCC_64bit-Debug/yolov4-mish-416.cfg
weight_file=/data/cam_qt_test/build-untitled-Desktop_Qt_5_12_11_GCC_64bit-Debug/yolov4-mish-416.weights

[LicenseDetect]
fonttype=/usr/share/fonts/NotoSansCJK-Bold.ttc
name_file=/home/nfha4/camVisionCC/untitled1/lic_model/obj_license.names
cfg_file=/home/nfha4/camVisionCC/untitled1/lic_model/yolo-obj_license.cfg
weight_file=/home/nfha4/camVisionCC/untitled1/lic_model/yolo-obj_license_final.weights

[OCR_Setting]
char_list_file=/data/hh_vision_lib/video_app/hh_vision_lib/ppocr/ppocr_keys_v1.txt
rec_model_dir=/data/PaddleOCR-2.7.5/deploy/cpp_infer/build/rec
det_model_dir=/data/PaddleOCR-2.7.5/deploy/cpp_infer/build/det
cls_model_dir=/home/nfha4/camVisionCC/untitled1/paddle_model/cls

[ScanCam]
id=d9ca44d7-cff4-4cdf-9782-b7c0c0345ksf
#id=d9ca44d7-cff4-4cdf-9782-b7c0crtyh545
ip=172.17.88.55
port=8000
realip=172.17.88.55
realport=8000
realusername=testtesttest
realpwd=testtesttest
type=2
username=testtesttest
password=testtesttest
channelid=1
streamtype=1
northangle=0
geoscope=22.755869,113.504878,22.784760,113.658963
cam_longitude=113.563544
cam_latitude=22.745222
cam_height=28.5
#这里使用毫米为单位，如4.7mm，值为4.7
min_focal=2.8
#这里的cmos_len使用的是1/n英寸的n来表示，如1/2.8英寸，值为2.8。对于>=1英寸的cmos 需要额外处理不能在这里配置。
cmos_len=2.8
pan_direction=0
tilt_direction=0
t_offset=0
#rtsp_url=rtspsrc location=rtsp://admin:Hg123456@10.80.0.247/third/h264/stream latency=10 ! decodebin ! videoconvert ! appsink sync=false
rtsp_url=rtsp://admin:haige750@172.17.88.55/h264/ch1/sub/av_stream
stream_width=704
stream_height=576

[TrackCam]
id=d9ca44d7-cff4-4cdf-9782-b72345fdsd2e
ip=172.24.62.52
port=8000
realip=172.24.62.52
realport=8000
realusername=admin
realpwd=haige750
type=1
username=admin
password=haige750
channelid=1
streamtype=1
rtsp_url=rtsp://admin:haige750@172.17.88.55/h264/ch1/sub/av_stream
stream_width=1920
stream_height=1080
pan_direction=0
tilt_direction=0

[InvadeDetect]
invadeClassId=67
isOn=1

[Radar1]
id=d9ca44d7-cff4-4cdf-9782-b7c0c034rty2
ip=172.24.171.199
port=5000

[ModelSettings]
model_path=libs/libowf_detect_person.so
plate_detect.trt=/home/nvidia/code/svn/smart_traffic_cpp/trt_model/plate_detect.trt
plate_rec = /home/nvidia/code/svn/smart_traffic_cpp/trt_model/plate_rec.trt
name_file=labels/label_person.txt
cfg_file=cfg.txt 
weight_file=models/yolov4_person.om

[MOTSettings]
library_path=libowf_deepsort_multi_track.so
weight_file=resnet50.om

[GPUS]
gpu_id=0

[RegionDefine]
json=

[SystemSettings]
port=8214
device_id=0
taskId=
event_port=8215
stream_service_ip=192.168.1.220
#定位与图像目标融合
ais_fusion_switch=0
#基于图像的目标定位功能
video_target_pos=0


[Mqtt]
server=172.19.0.18
port=41883
user=
pwd=
topic=tds_det_status

[kafka]
server=192.168.101.1.196
port=9092
topic=UnionTargetTopic
groupid=arvideo-consumer-group
"""

class IniFileHelper:        

    @staticmethod
    def _new_parser() -> configparser.ConfigParser:
        cfg = configparser.ConfigParser(interpolation=None)
        cfg.optionxform = str
        return cfg

    @staticmethod
    def copy_file(src: Path, dst:Path, overwrite: bool=True) -> Path:
        src = Path(src)
        dst = Path(dst)
        if not src.exists():
            raise FileNotFoundError(f"源文件不存在: {src}")
        if dst.exists() and overwrite is False:
            raise FileExistsError(f"目标文件已存在，且不允许覆盖：{dst}")
        dst.parent.mkdir(parents=True,exist_ok=True)
        return Path(shutil.copy2(src,dst))
    
    @staticmethod
    def delete_file(dst: Path, ignore_mission = False) -> Path:               
        p = Path(dst)
        if p.exists() and p.is_dir():
            raise IsADirectoryError(f"目标是目录，不是文件：{p}")
        try:
            p.unlink()
        except FileNotFoundError:
            if not ignore_mission:
                raise
        return p
    
    @staticmethod
    def ensure_config(path: Path = CONFIG_PATH, template: Optional[str] = None):
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(template or _DEFAULT_TEMPLATE, encoding="utf-8")

    @classmethod
    def load_config(cls, path: Path = CONFIG_PATH) -> configparser.ConfigParser:
        cls.ensure_config(path)
        cfg = cls._new_parser()
        with path.open("r", encoding="utf-8") as f:
            cfg.read_file(f)
        return cfg

    @classmethod
    def save_config(cls, cfg: configparser.ConfigParser, path: Path = CONFIG_PATH):
        cls.ensure_config(path)
        with path.open("w", encoding="utf-8") as f:
            cfg.write(f)

    @classmethod
    def get_section(cls, section: str, path: Path = CONFIG_PATH) -> Dict[str, str]:
        cfg = cls.load_config(path)
        if section not in cfg:
            raise KeyError(f"缺少[{section}]")
        return dict(cfg[section].items())

    @classmethod
    def set_value(cls, section: str, key: str, value: Any, path: Path = CONFIG_PATH):
        cfg = cls.load_config(path)
        if section not in cfg:
            cfg.add_section(section)
        cfg.set(section, key, str(value))
        cls.save_config(cfg, path)

    @classmethod
    def batch_set(cls, section: str, data: Dict[str, Any], path: Path = CONFIG_PATH):
        cfg = cls.load_config(path)
        if section not in cfg:
            cfg.add_section(section)
        for k, v in data.items():
            cfg.set(section, k, str(v))
        cls.save_config(cfg, path)

    @staticmethod
    def to_number(v: str):
        try:
            if v.lower().startswith("0x"):
                return int(v, 16)
            if any(ch in v for ch in ('.', 'e', 'E')):
                return float(v)
            return int(v)
        except Exception:
            return v

    @classmethod
    def get_section_typed(cls, section: str, path: Path = CONFIG_PATH) -> Dict[str, Any]:
        return {k: cls.to_number(v) for k, v in cls.get_section(section, path).items()}

    @classmethod
    def ensure_camera_mapping(cls, logical: str, real_section: str, path: Path = CONFIG_PATH):
        cfg = cls.load_config(path)
        if "cam_list" not in cfg:
            cfg.add_section("cam_list")
        if logical not in cfg["cam_list"]:
            cfg.set("cam_list", logical, real_section)
            cls.save_config(cfg, path)

    @classmethod
    def list_cameras(cls, path: Path = CONFIG_PATH):
        cfg = cls.load_config(path)
        if "cam_list" not in cfg:
            return {}
        result = {}
        for logic, sec in cfg["cam_list"].items():
            if sec in cfg:
                result[logic] = dict(cfg[sec].items())
        return result
