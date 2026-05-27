from flask import Blueprint, request, jsonify
from flask import Blueprint, make_response, render_template
from flask import request, jsonify,Response
from db import dbconn
from datetime import datetime  # 添加 datetime 模块
import json
from models.process_manager import ProcessManager
from models.task_return import TaskReturn
from models.process import TaskConfig, Point, Camera
from models.ar_stream_config import ArStreamConfig
from mq_controller.mq_controller import start_status_thread, pm
from ini_file_controller.ini_file_helper import IniFileHelper
from pathlib import Path
from task_controller import docker_helper
import uuid
import time
import os
from task_controller.task_starter import start_task_process, get_port, is_managed_temp_model_file

# PROGRAM_PATH = '/app/video_app/build'

# def get_ini_filepath(name):
#     ts = time.strftime("%Y%m%d-%H%M%S")
#     safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(name))[:50]
#     ini_file = os.path.join(PROGRAM_PATH, f"{safe_name}-{ts}.ini")
#     return ini_file

# def get_onnx_filepath(name):
#     ts = time.strftime("%Y%m%d-%H%M%S")
#     safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(name))[:50]
#     onnx_file = os.path.join(PROGRAM_PATH, f"{safe_name}-{ts}.onnx")
#     return onnx_file

# def get_ini_filepath(name):
#     ts = time.strftime("%Y%m%d-%H%M%S")
#     safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(name))[:50]
#     onnx_file = os.path.join(PROGRAM_PATH, f"{safe_name}-{ts}.ini")
#     return onnx_file

# def get_port():
#     db = dbconn.DBConn()
#     session = db.get_session()
    
#     for i in range(51000,51050):
#         search_task = session.query(TaskConfig).filter_by(status=1,port=i).first()
#         if not search_task:
#             return i
def response_json_feng_dian(code,msg,data=None):
    msg = {
        'code': code,
        'result': msg,
        'data': data
    }
    return Response(json.dumps(msg,ensure_ascii=False),mimetype='application/json')

#定义一个返回信息的固定格式
def response_json(code, msg, data=None):
    msg = {
        'status': code,
        'msg': msg,
        'data': data
    }
    return Response(json.dumps(msg,ensure_ascii=False),mimetype='application/json')


def _safe_delete_file(file_path, *, only_managed_model: bool = False):
    if not file_path:
        return
    if only_managed_model and not is_managed_temp_model_file(file_path):
        return
    IniFileHelper.delete_file(Path(file_path), ignore_mission=True)


def _delete_task_files(task: TaskConfig):
    _safe_delete_file(task.ini_file)
    _safe_delete_file(task.resnet_file)
    _safe_delete_file(task.yolo_file, only_managed_model=True)


def _restart_task_from_record(session, task: TaskConfig):
    new_task = TaskConfig()
    new_task.id = task.id
    new_task.taskname = task.taskname
    new_task.create_by = task.create_by
    new_task.create_time = task.create_time
    new_task.update_by = task.update_by
    new_task.update_time = datetime.now()
    new_task.cam1_id = task.cam1_id
    new_task.cam1_ip = task.cam1_ip
    new_task.cam1_username = task.cam1_username
    new_task.cam1_password = task.cam1_password
    new_task.cam1_source_url = task.cam1_source_url
    new_task.cam2_id = task.cam2_id
    new_task.cam2_ip = task.cam2_ip
    new_task.cam2_username = task.cam2_username
    new_task.cam2_password = task.cam2_password
    new_task.cam1_type = task.cam1_type
    new_task.cam2_type = task.cam2_type
    new_task.region_str = task.region_str
    new_task.cameras_str = task.cameras_str
    new_task.udp_port = task.udp_port
    new_task.port = task.port
    new_task.event_port = task.event_port
    new_task.test_mode = task.test_mode
    new_task.status = 1
    new_task.action = 1
    new_task = start_task_process(new_task, new_task.port)
    new_task.region = []
    new_task.cameras = []
    session.add(new_task)
    session.commit()
    return new_task


def _build_task_return_from_task(task: TaskConfig):
    task_return = TaskReturn()
    task_return.camId = task.cam1_id
    task_return.id = task.cam1_id
    task_return.pid = task.pid
    task_return.stream_url = task.url
    task_return.stream_port = task.port
    task_return.event_port = task.event_port
    return task_return


def restart_task_with_existing_record(session, task: TaskConfig):
    if task.pid:
        try:
            _stop_pid_flexible(task.pid)
        except Exception:
            pass

    _delete_task_files(task)
    session.delete(task)
    session.commit()

    new_task = _restart_task_from_record(session, task)
    from http_request_util.data_syn_controller import syn_task_data
    syn_task_data(_build_task_return_from_task(new_task).to_dict())
    return new_task


def _stop_pid_flexible(pid_value):
    """Stop either a host process (numeric pid) via ProcessManager or a Docker container by id/name."""
    if pid_value is None:
        return
    # If numeric, use ProcessManager
    try:
        pid_int = int(pid_value)
    except Exception:
        # treat as container id/name
        try:
            docker_helper.stop_container(str(pid_value), remove=True)
            return
        except Exception as e:
            # raise so caller can handle/report
            raise
    else:
        return pm.stop_process_by_pid(pid_int)

process_bp = Blueprint('process', __name__)

# def start_task_process(task):
#     try:
#         cmd = '/app/qiang_qiu_lian_dong_deploy/hello_test'
#         ini_fullpath = Path(get_ini_filepath('config'))
#         IniFileHelper.ensure_config(ini_fullpath)
        
#         org_det_onnx = Path(PROGRAM_PATH+'/'+'yolov8n.onnx')
#         dst_det_onnx = Path(get_onnx_filepath('yolov8n'))
#         IniFileHelper.copy_file(org_det_onnx,dst_det_onnx)
        
#         org_trk_onnx = Path(PROGRAM_PATH+'/'+'resnet50.onnx')
#         dst_trk_onnx = Path(get_onnx_filepath('resnet50'))
#         IniFileHelper.copy_file(org_trk_onnx,dst_trk_onnx)
        
#         pid = pm.start_process(task.id, cmd, log_to_file=True, merge_stderr=True)
#         start_status_thread(json.dumps({'id': task.id, 'status': 1, 'pid': pid},ensure_ascii=False))
#         task.pid = pid
#         task.resnet_file = str(dst_trk_onnx)
#         task.yolo_file = str(dst_det_onnx)
#         task.ini_file = str(ini_fullpath)
#         return task
#     except Exception as e:
#         raise Exception(f'create task fail reason: {e}')

@process_bp.route('/cam-ar-task',methods=['POST'])
def start_task():
    db = dbconn.DBConn()
    session = db.get_session()
    print(request.get_data(as_text=True))
    data = request.get_json()
    arStreamConfig = ArStreamConfig.from_dict(data)
    task = TaskConfig()
    task.taskname=arStreamConfig.camId;    
    task.cam1_id = arStreamConfig.camId
    task.cam1_ip = arStreamConfig.camIp
    task.cam1_password = arStreamConfig.camPassword
    task.cam1_username = arStreamConfig.camAccount
    task.url = arStreamConfig.arStreamUrl   
    task.id = str(uuid.uuid4())
    print(arStreamConfig.camId)
    try:        
        search_member = session.query(TaskConfig).filter_by(cam1_id=task.cam1_id).first()
        if search_member:
            # if task.action ==3:
            #     pm.stop_process_by_pid(int(search_member.pid))
            #     IniFileHelper.delete_file(search_member.ini_file)
            #     IniFileHelper.delete_file(search_member.resnet_file)
            #     IniFileHelper.delete_file(search_member.yolo_file)
            #     session.delete(search_member)
            #     session.commit()
                
            
            # if task.action == 2:
            #     task.port = get_port()
            #     task.event_port=(task.port+1)        
            #     pm.stop_process_by_pid(int(search_member.pid))
            #     IniFileHelper.delete_file(search_member.ini_file)
            #     IniFileHelper.delete_file(search_member.resnet_file)
            #     IniFileHelper.delete_file(search_member.yolo_file)
            #     session.delete(search_member)
            #     session.commit()
            #     task = start_task_process(arStreamConfig,task.port)
            #     task.region=[]
            #     task.cameras=[]
            #     task.status=1                
            #     session.add(task)
            #     session.commit()
            task.action=2
            task.cam1_id = search_member.cam1_id
            task.pid = search_member.pid
            task.url = search_member.url
            task.port = search_member.port
            task.event_port = search_member.event_port
        else:             
                task.action =1
                task.port = get_port() 
                task.event_port=(task.port+1)
                task = start_task_process(task,task.port)
                task.region=[]
                task.cameras=[]
                task.status=1            
                session.add(task)
                session.commit()
        # ini_fullpath = Path('/app/qiang_qiu_lian_dong_deploy/config.ini')
        # IniFileHelper.ensure_config(ini_fullpath)
        
        # org_det_onnx = Path(PROGRAM_PATH+'/'+'yolov8n.onnx')
        # dst_det_onnx = Path(get_onnx_filepath('yolov8n'))
        # IniFileHelper.copy_file(org_det_onnx,dst_det_onnx)
        
        # org_trk_onnx = Path(PROGRAM_PATH+'/'+'resnet50.onnx')
        # dst_trk_onnx = Path(get_onnx_filepath('resnet50'))
        # IniFileHelper.copy_file(org_trk_onnx,dst_trk_onnx)
        
        # pid = pm.start_process(name, cmd, log_to_file=True, merge_stderr=True)
        # start_status_thread(json.dumps({'id': task.id, 'status': 1, 'pid': pid},ensure_ascii=False))
        
        task_return = TaskReturn()
        task_return.id = task.cam1_id
        task_return.pid = task.pid
        task_return.stream_url = task.url
        task_return.stream_port = task.port                
        task_return.event_port = task.event_port
                   
        if task.action==1:
            return response_json_feng_dian(200, True ,task_return.to_dict())
        if task.action==2:
            return response_json_feng_dian(200, True ,task_return.to_dict())
        if task.action==3:
            return response_json_feng_dian(200, True ,task_return.to_dict())
        # return jsonify({'message': '启动成功', 'pid': pid, 'name': name}), 200
    except Exception as e:
        return response_json(400, str(e))    

@process_bp.route('/start_process', methods=['POST'])
def start_process():
    db = dbconn.DBConn()
    session = db.get_session()
    print(request.get_data(as_text=True))
    data = request.get_json()
    task = TaskConfig.from_dict(data)    
    name = task.id
    # cmd = '/app/video_app/build/video_app --conf /app/qiang_qiu_service/webapi/config.ini'
    # cmd = '/app/qiang_qiu_lian_dong_deploy/hello_test'
    # if not cmd:
    #     return jsonify({'error': '缺少 cmd'}), 400
    try:        
        search_member = session.query(TaskConfig).filter_by(id=task.id).first()
        if search_member:
            if task.action ==3:
                _stop_pid_flexible(search_member.pid)
                IniFileHelper.delete_file(search_member.ini_file)
                IniFileHelper.delete_file(search_member.resnet_file)
                IniFileHelper.delete_file(search_member.yolo_file)
                session.delete(search_member)
                session.commit()
                
            
            if task.action == 2:
                task.port = get_port()        
                _stop_pid_flexible(search_member.pid)
                IniFileHelper.delete_file(search_member.ini_file)
                IniFileHelper.delete_file(search_member.resnet_file)
                IniFileHelper.delete_file(search_member.yolo_file)
                session.delete(search_member)
                session.commit()
                task = start_task_process(task,task.port)
                task.region=[]
                task.cameras=[]
                task.status=1                
                session.add(task)
                session.commit()
                
        if task.action == 1: 
            task.port = get_port()   
            task = start_task_process(task,task.port)
            task.region=[]
            task.cameras=[]
            task.status=1            
            session.add(task)
            session.commit()
        # ini_fullpath = Path('/app/qiang_qiu_lian_dong_deploy/config.ini')
        # IniFileHelper.ensure_config(ini_fullpath)
        
        # org_det_onnx = Path(PROGRAM_PATH+'/'+'yolov8n.onnx')
        # dst_det_onnx = Path(get_onnx_filepath('yolov8n'))
        # IniFileHelper.copy_file(org_det_onnx,dst_det_onnx)
        
        # org_trk_onnx = Path(PROGRAM_PATH+'/'+'resnet50.onnx')
        # dst_trk_onnx = Path(get_onnx_filepath('resnet50'))
        # IniFileHelper.copy_file(org_trk_onnx,dst_trk_onnx)
        
        # pid = pm.start_process(name, cmd, log_to_file=True, merge_stderr=True)
        # start_status_thread(json.dumps({'id': task.id, 'status': 1, 'pid': pid},ensure_ascii=False))
        
        task_return = TaskReturn()
        task_return.id = task.id
        task_return.pid = task.pid
        # task_return.stream_url = "ws://172.19.0.51:5201"
        task_return.stream_port = task.port                
           
        if task.action==1:
            return response_json(200, '启动成功' ,task_return.to_dict())
        if task.action==2:
            return response_json(200, '修改成功' ,task_return.to_dict())
        if task.action==3:
            return response_json(200, '删除成功' ,task_return.to_dict())
        # return jsonify({'message': '启动成功', 'pid': pid, 'name': name}), 200
    except Exception as e:
        return response_json(400, str(e))
        # return jsonify({'error': str(e)}), 400

@process_bp.route('/stop_process', methods=['POST'])
def stop_process():
    db = dbconn.DBConn()   
    session = db.get_session()
    print(request.get_data(as_text=True))
    data = request.get_json()
    arStreamConfig = ArStreamConfig.from_dict(data)
    task = TaskConfig()
    task.taskname=arStreamConfig.camId;    
    task.cam1_id = arStreamConfig.camId
    task.cam1_ip = arStreamConfig.camIp
    task.cam1_password = arStreamConfig.camPassword
    task.cam1_username = arStreamConfig.camAccount
    task.url = arStreamConfig.arStreamUrl   
    task.id = str(uuid.uuid4())
    print(arStreamConfig.camId)
    # data = request.get_json()
    # pid = data.get('pid')
    # name = data.get('name')
    if task.cam1_id is None:
        return jsonify({'error': '需要提供 pid 或 name'}), 400
    try:
        running = session.query(TaskConfig).filter_by(taskname=task.cam1_id).first()
        if running:
            stop_task_and_delete(running.id)
            task_return = TaskReturn()
            task_return.id = task.cam1_id
            task_return.pid = task.pid
            task_return.stream_url = task.url
            task_return.stream_port = task.port                
            task_return.event_port = task.event_port    
            return  response_json_feng_dian(200, True ,task_return.to_dict())
            # if pid is not None:
        #     try:
        #         _stop_pid_flexible(pid)
        #     except Exception as e:
        #         return jsonify({'error': str(e)}), 400

        #     return jsonify({'message': f'pid {pid} 已停止'}), 200
        # else:
        #     pids = pm.stop_processes_by_name(name)
        #     return jsonify({'message': f'name={name} 已停止', 'pids': pids}), 200
    except Exception as e:
        task_return = TaskReturn()
        task_return.id = task.cam1_id
        task_return.pid = task.pid
        task_return.stream_url = task.url
        task_return.stream_port = task.port                
        task_return.event_port = task.event_port
        return  response_json_feng_dian(400, False ,task_return.to_dict())

@process_bp.route('/list_processes', methods=['GET'])
def list_processes():
    return jsonify({'processes': pm.list_processes()}), 200


@process_bp.route('/task/<string:task_id>/stop', methods=['POST'])
def stop_task_and_delete(task_id):
    db = dbconn.DBConn()
    session = db.get_session()
    try:
        task = session.query(TaskConfig).filter_by(id=task_id).first()
        if not task:
            return response_json(404, '任务不存在')

        if task.pid:
            try:
                _stop_pid_flexible(task.pid)
            except Exception:
                pass

        _delete_task_files(task)
        session.delete(task)
        session.commit()
        return response_json(200, '结束并删除成功')
    except Exception as e:
        session.rollback()
        return response_json(400, str(e))


@process_bp.route('/task/<string:task_id>/restart', methods=['POST'])
def restart_task_from_record(task_id):
    db = dbconn.DBConn()
    session = db.get_session()
    try:
        task = session.query(TaskConfig).filter_by(id=task_id).first()
        if not task:
            return response_json(404, '任务不存在')

        new_task = restart_task_with_existing_record(session, task)
        return response_json(200, '重启成功', {
            'id': new_task.id,
            'pid': new_task.pid,
            'port': new_task.port,
            'event_port': new_task.event_port,
            'url': new_task.url,
        })
    except Exception as e:
        session.rollback()
        return response_json(400, str(e))
