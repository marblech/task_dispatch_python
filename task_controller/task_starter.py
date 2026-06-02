import os
import shlex
import time
from itertools import chain
from pathlib import Path
import json
from datetime import datetime  # 添加 datetime 模块
from models.process_manager import ProcessManager
from models.task_return import TaskReturn
from models.process import TaskConfig, Point, Camera
from models.ar_stream_config import ArStreamConfig
from ini_file_controller.ini_file_helper import IniFileHelper
from task_controller import docker_helper, port_helper

PROGRAM_PATH = '/data/video_ar_app'
SERVICE_IP = '192.168.1.221'
TEMP_MODEL_MARKER = '-tasktmp-'
PORT_RANGE_START = 30000
PORT_RANGE_END = 40000
#TASK_CONTAINER_IMAGE = 'feng_dian_ar_deploy'
# TASK_CONTAINER_IMAGE = 'ascend_dev_debug'
TASK_CONTAINER_IMAGE = 'task_condition_docker'
CONTAINER_MOUNT_DIR = f'/home/marblech'

def get_ini_filepath(name):
    ts = time.strftime("%Y%m%d-%H%M%S")
    safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(name))[:50]
    ini_file = os.path.join(PROGRAM_PATH, f"{safe_name}-{ts}.ini")
    return ini_file

def get_onnx_filepath(name):
    ts = time.strftime("%Y%m%d-%H%M%S")
    unique_suffix = str(time.time_ns())[-6:]
    safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(name))[:50]
    file_name = f"{safe_name}{TEMP_MODEL_MARKER}{ts}-{unique_suffix}.om"
    onnx_file = os.path.join(PROGRAM_PATH+'/models', file_name)    
    return file_name,onnx_file


def is_managed_temp_model_file(path) -> bool:
    p = Path(path)
    if p.suffix.lower() != '.om':
        return False
    return TEMP_MODEL_MARKER in p.name

# def get_ini_filepath(name):
#     ts = time.strftime("%Y%m%d-%H%M%S")
#     safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(name))[:50]
#     onnx_file = os.path.join(PROGRAM_PATH, f"{safe_name}-{ts}.ini")
#     return onnx_file

def get_port():
    return get_port_near()


def _iter_candidate_ports(preferred_port: int | None = None):
    if preferred_port is None:
        yield from range(PORT_RANGE_START, PORT_RANGE_END)
        return

    preferred_port = max(PORT_RANGE_START, min(int(preferred_port), PORT_RANGE_END - 1))
    forward = range(preferred_port, PORT_RANGE_END)
    backward = range(PORT_RANGE_START, preferred_port)
    yield from chain(forward, backward)


def get_port_near(preferred_port: int | None = None):
    docker_reserved_ports = port_helper.get_docker_published_host_ports()

    for port in _iter_candidate_ports(preferred_port):
        event_port = port + 1
        if event_port > PORT_RANGE_END:
            continue

        if not port_helper.is_host_port_available(port, docker_reserved_ports=docker_reserved_ports):
            continue

        if not port_helper.is_host_port_available(event_port, docker_reserved_ports=docker_reserved_ports):
            continue

        return port

    raise RuntimeError(
        f'no available consecutive ports found in range {PORT_RANGE_START}-{PORT_RANGE_END}'
    )


def _assign_available_ports(task: TaskConfig, preferred_port: int | None = None):
    desired_port = preferred_port if preferred_port is not None else task.port
    desired_event_port = task.event_port

    if desired_port is not None and desired_event_port is None:
        desired_event_port = desired_port + 1

    docker_reserved_ports = port_helper.get_docker_published_host_ports()

    if desired_port is not None and desired_event_port is not None:
        port_ok = port_helper.is_host_port_available(
            desired_port,
            docker_reserved_ports=docker_reserved_ports,
        )
        event_port_ok = port_helper.is_host_port_available(
            desired_event_port,
            docker_reserved_ports=docker_reserved_ports,
        )
        if port_ok and event_port_ok:
            task.port = desired_port
            task.event_port = desired_event_port
            return

        print(
            f'requested ports {desired_port}/{desired_event_port} unavailable, '
            'selecting a new available port pair'
        )

    new_port = get_port_near(desired_port)
    task.port = new_port
    task.event_port = new_port + 1


def _assign_available_udp_port(task: TaskConfig, preferred_udp_port: int | None = None):
    """
    动态分配一个可用的UDP端口并保存到 task.udp_port
    """
    docker_reserved_ports = port_helper.get_docker_published_host_ports()

    if preferred_udp_port is not None:
        # 优先使用指定的UDP端口
        if port_helper.is_host_udp_port_available(
            preferred_udp_port,
            docker_reserved_ports=docker_reserved_ports,
        ):
            task.udp_port = preferred_udp_port
            return
        else:
            print(f'requested UDP port {preferred_udp_port} unavailable, selecting a new available UDP port')

    # 从PORT_RANGE_START开始寻找可用的UDP端口
    for udp_port in range(PORT_RANGE_START, PORT_RANGE_END):
        if port_helper.is_host_udp_port_available(
            udp_port,
            docker_reserved_ports=docker_reserved_ports,
        ):
            task.udp_port = udp_port
            return

    raise RuntimeError(
        f'no available UDP port found in range {PORT_RANGE_START}-{PORT_RANGE_END}'
    )

def start_task_process(task:TaskConfig,port=None):
    try:
        _assign_available_ports(task, preferred_port=port)
        port = task.port
        
        # 动态分配UDP端口并保存到 task.udp_port
        _assign_available_udp_port(task, preferred_udp_port=task.udp_port)
        udp_port = task.udp_port
        print(f'Assigned UDP port: {udp_port} for task {task.taskname}')
        
        # cmd = '/app/qiang_qiu_lian_dong_deploy/hello_test'
        
        ini_fullpath = Path(get_ini_filepath('config'))
        IniFileHelper.ensure_config(ini_fullpath)
        # IniFileHelper.set_value("SystemSettings","port",str(port),ini_fullpath)              
        if task.test_mode==0:
            org_det_onnx = Path(PROGRAM_PATH+'/models/'+'yolov4_ship.om')
            onnx_file,onnx_fullpath=get_onnx_filepath('yolov4_ship')
            dst_det_onnx = Path(onnx_fullpath)
            IniFileHelper.copy_file(org_det_onnx,dst_det_onnx)
            IniFileHelper.set_value("ModelSettings","weight_file",'models/'+str(onnx_file),ini_fullpath)
            IniFileHelper.set_value("ModelSettings","model_path","libs/libowf_detect_ship_alg.so",ini_fullpath)
            IniFileHelper.set_value("ModelSettings","name_file","labels/label_ship.txt",ini_fullpath)
            IniFileHelper.set_value("ModelSettings","cfg_file","cfg.txt",ini_fullpath)
            IniFileHelper.set_value("GPUS","gpu_id","0",ini_fullpath)
            IniFileHelper.set_value("MOTSettings","library_path","libowf_deepsort_multi_track.so",ini_fullpath)
            IniFileHelper.set_value("MOTSettings","weight_file","/data/video_ar_app/models/resnet50.om",ini_fullpath)
        else:
            org_det_onnx = Path(PROGRAM_PATH+'/models/'+'yolov4_person.om')
            onnx_file,onnx_fullpath=get_onnx_filepath('yolov4_person')
            dst_det_onnx = Path(onnx_fullpath)
            IniFileHelper.copy_file(org_det_onnx,dst_det_onnx)
            IniFileHelper.set_value("ModelSettings","weight_file",'models/'+str(onnx_file),ini_fullpath)
        
        # org_trk_onnx = Path(PROGRAM_PATH+'/'+'resnet50.onnx')
        # onnx_file,onnx_fullpath=get_onnx_filepath('resnet50')
        # dst_trk_onnx = Path(onnx_fullpath)
        # IniFileHelper.copy_file(org_trk_onnx,dst_trk_onnx)
        # IniFileHelper.set_value("MOTSettings","weight_file",str(dst_trk_onnx),ini_fullpath)
        
        IniFileHelper.set_value("SystemSettings","taskId",str(task.cam1_id),ini_fullpath)
        IniFileHelper.set_value("p2p","listen_port",str(task.udp_port),ini_fullpath)
        # IniFileHelper.set_value("SystemSettings","device_id",str(task.cameras[0].id),ini_fullpath)
        
        # task.cam1_username = task.cameras[0].user
        # task.cam1_password = task.cameras[0].password
        # task.cam1_ip = task.cameras[0].ip        
        # task.cam1_id = task.cameras[0].id
        
        # task.cam2_username = task.cameras[1].user
        # task.cam2_password = task.cameras[1].password
        # task.cam2_ip = task.cameras[1].ip        
        # task.cam2_type = task.cameras[1].cameratype
        # task.cam2_id = task.cameras[1].id
        
        # if task.cam1_type in {1,2,3,4}:
        if task.cam1_source_url not in (None, ""):
            cam1_stream_str = task.cam1_source_url
        else:
            if task.test_mode==1:
                cam1_stream_str = str(f"rtsp://{task.cam1_ip}/live/stream")
            else:
                cam1_stream_str = str(f"rtsp://{task.cam1_username}:{task.cam1_password}@{task.cam1_ip}/h264/ch1/sub/av_stream")
        IniFileHelper.set_value("ScanCam","rtsp_url",str(cam1_stream_str),ini_fullpath)
        IniFileHelper.set_value("ScanCam","ip",str(task.cam1_ip),ini_fullpath)
        IniFileHelper.set_value("ScanCam","username",str(task.cam1_username),ini_fullpath)
        IniFileHelper.set_value("ScanCam","password",str(task.cam1_password),ini_fullpath)
        IniFileHelper.set_value("ScanCam","realip",str(task.cam1_ip),ini_fullpath)
        IniFileHelper.set_value("ScanCam","realusername",str(task.cam1_username),ini_fullpath)
        IniFileHelper.set_value("ScanCam","realpwd",str(task.cam1_password),ini_fullpath)
        IniFileHelper.set_value("ScanCam","id",str(task.cam1_id),ini_fullpath)
        IniFileHelper.set_value("SystemSettings","event_port",str(task.event_port),ini_fullpath)
        IniFileHelper.set_value("SystemSettings","port",str(task.port),ini_fullpath)
        IniFileHelper.set_value("kafka","groupid","ar_"+str(task.cam1_id),ini_fullpath)
        task.url= str(f"ws://{SERVICE_IP}:{task.port}/{task.cam1_id}/ar.live.flv")
        # IniFileHelper.set_value("ScanCam","min_focal",str(task.cameras[0].minfocus),ini_fullpath)
        # IniFileHelper.set_value("ScanCam","cmos_len",str(task.cameras[0].cmos),ini_fullpath)
            
        # elif task.cam1_type in {5,6}:
        #     cam1_stream_str = str(f"rtsp://{task.cam1_username}:{task.cam1_password}@{task.cam1_ip}/h264/ch1/main/av_stream")  
        #     IniFileHelper.set_value("TrackCam","rtsp_url",str(cam1_stream_str),ini_fullpath)
        #     IniFileHelper.set_value("TrackCam","ip",str(task.cam1_ip),ini_fullpath)
        #     IniFileHelper.set_value("TrackCam","username",str(task.cam1_username),ini_fullpath)
        #     IniFileHelper.set_value("TrackCam","password",str(task.cam1_password),ini_fullpath)
        #     IniFileHelper.set_value("TrackCam","realip",str(task.cam1_ip),ini_fullpath)
        #     IniFileHelper.set_value("TrackCam","realusername",str(task.cam1_username),ini_fullpath)
        #     IniFileHelper.set_value("TrackCam","realpwd",str(task.cam1_password),ini_fullpath)  
        #     IniFileHelper.set_value("TrackCam","pan",str(task.cameras[0].pan),ini_fullpath)
        #     IniFileHelper.set_value("TrackCam","tilt",str(task.cameras[0].tilt),ini_fullpath)
        #     IniFileHelper.set_value("TrackCam","zoom",str(task.cameras[0].zoom),ini_fullpath)
        #     IniFileHelper.set_value("SystemSettings","device_id",str(task.cameras[0].deviceid),ini_fullpath)
        
        # if task.cam2_type in {1,2,3,4}:
        #     cam2_stream_str = str(f"rtsp://{task.cam2_username}:{task.cam2_password}@{task.cam2_ip}/h264/ch1/main/av_stream")
        #     IniFileHelper.set_value("ScanCam","rtsp_url",str(cam2_stream_str),ini_fullpath)
        #     IniFileHelper.set_value("ScanCam","ip",str(task.cam2_ip),ini_fullpath)
        #     IniFileHelper.set_value("ScanCam","username",str(task.cam2_username),ini_fullpath)
        #     IniFileHelper.set_value("ScanCam","password",str(task.cam2_password),ini_fullpath)
        #     IniFileHelper.set_value("ScanCam","realip",str(task.cam2_ip),ini_fullpath)
        #     IniFileHelper.set_value("ScanCam","realusername",str(task.cam2_username),ini_fullpath)
        #     IniFileHelper.set_value("ScanCam","realpwd",str(task.cam2_password),ini_fullpath)
        #     IniFileHelper.set_value("ScanCam","min_focal",str(task.cameras[1].minfocus),ini_fullpath)
        #     IniFileHelper.set_value("ScanCam","cmos_len",str(task.cameras[1].cmos),ini_fullpath)
            
        # elif task.cam2_type in {5,6}:
        #     cam2_stream_str = str(f"rtsp://{task.cam2_username}:{task.cam2_password}@{task.cam2_ip}/h264/ch1/main/av_stream")
        #     IniFileHelper.set_value("TrackCam","rtsp_url",str(cam2_stream_str),ini_fullpath)
        #     IniFileHelper.set_value("TrackCam","ip",str(task.cam2_ip),ini_fullpath)
        #     IniFileHelper.set_value("TrackCam","username",str(task.cam2_username),ini_fullpath)
        #     IniFileHelper.set_value("TrackCam","password",str(task.cam2_password),ini_fullpath)
        #     IniFileHelper.set_value("TrackCam","realip",str(task.cam2_ip),ini_fullpath)
        #     IniFileHelper.set_value("TrackCam","realusername",str(task.cam2_username),ini_fullpath)
        #     IniFileHelper.set_value("TrackCam","realpwd",str(task.cam2_password),ini_fullpath)  
        #     IniFileHelper.set_value("TrackCam","pan",str(task.cameras[1].pan),ini_fullpath)
        #     IniFileHelper.set_value("TrackCam","tilt",str(task.cameras[1].tilt),ini_fullpath)
        #     IniFileHelper.set_value("TrackCam","zoom",str(task.cameras[1].zoom),ini_fullpath)  
        #     IniFileHelper.set_value("SystemSettings","device_id",str(task.cameras[1].deviceid),ini_fullpath)   
        
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        host_log_dir = Path('/data/webapi/logs')
        host_log_dir.mkdir(parents=True, exist_ok=True)
        container_log_file = f'/data/webapi/logs/{task.taskname}_{ts}.log'

        if task.cam1_password=="testtesttest":
            binary_path = '/data/video_ar_app/cam_controller_example'
        else:
            binary_path = '/data/video_ar_app/cam_controller_example'

        cmd = [
            'sh',
            '-c',
            (
               'export LD_LIBRARY_PATH=/data/boost_182/lib:/data/ffmpeg_517_install/lib:/data/hksdk_arm/lib:/data/video_ar_app/libs:/data/video_ar_app:$LD_LIBRARY_PATH && '           
                                # 'mkdir -p /data/webapi/logs && '
               f'exec {shlex.quote(binary_path)} '
               f'-c {shlex.quote(str(ini_fullpath))} '
               f'>> {shlex.quote(container_log_file)} 2>&1'
            ),
        ]

        # Run the command inside a docker container using docker_helper.docker_run
        # Use the deployment image and keep runtime-specific ports explicit here.
        try:
            if task.port is None or task.event_port is None:
                raise ValueError('task port or event_port is not set')

            # 构建 TCP 端口映射列表
            port_mappings = [
                f'{task.port}:{task.port}',
                f'{task.event_port}:{task.event_port}',
            ]
            
            # 构建 UDP 端口映射列表
            udp_port_mappings = [
                f'{task.udp_port}:{task.udp_port}',
            ]

            container = docker_helper.docker_run(
                image=TASK_CONTAINER_IMAGE,
                cmd=cmd,
                detach=True,
                remove=False,
                verify_running=True,
                startup_timeout=5,
                name=task.taskname,
                ports=port_mappings,
                udp_ports=udp_port_mappings,
                volumes={CONTAINER_MOUNT_DIR : {'bind': '/data', 'mode': 'rw'}},
            )
            # When detached, docker_helper returns a container object; use its id as pid
            pid = getattr(container, 'id', None)
            if pid is None:
                # Fallback: try to use returned value directly
                pid = container
            if isinstance(pid, (bytes, bytearray)):
                pid = pid.decode()
            elif pid is not None and not isinstance(pid, str):
                pid = str(pid)
        except Exception as e:
            raise Exception(
                'failed to start docker container: '
                f'{e}; host_log_file={container_log_file}; '
                f'tcp_ports={task.port}/{task.event_port}; udp_port={task.udp_port}'
            )
        task.pid = pid
        # task.resnet_file = str(dst_trk_onnx)
        task.yolo_file = str(dst_det_onnx)
        task.ini_file = str(ini_fullpath)
        task.log_file = str(container_log_file)
        task.port = port
        # udp_port 已在之前分配到 task.udp_port
        return task
    except Exception as e:
        raise Exception(f'create task fail reason: {e}')