from flask import Blueprint, make_response, render_template
from flask import request, jsonify,Response
from models.process import TaskConfig
from db import dbconn
from datetime import datetime  # 添加 datetime 模块
import json
import os
from pathlib import Path
from flask import session, redirect

def response_json(code, msg, data=None):
    msg = {
        'status': code,
        'msg': msg,
        'data': data
    }
    return Response(json.dumps(msg,ensure_ascii=False),mimetype='application/json')

def login_required(f):
    """登录验证装饰器"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            if request.is_json or request.headers.get('Accept') == 'application/json':
                return jsonify({'success': False, 'message': '请先登录', 'redirect': '/login'}), 401
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

manager_controller = Blueprint('manager', __name__)
LOG_ROOT_DIR = Path('/data/webapi/logs').resolve()

@manager_controller.route('/favicon.ico')
def favicon():
    return make_response('', 204)  # 返回空响应，状态码 204 表示无内容

@manager_controller.route('/list',methods=['GET'])
@login_required
def task_list():
    return render_template('manager.html')

@manager_controller.route('/task_list',methods=['GET'])
@login_required
def get_task_list():
    db = dbconn.DBConn()
    session_db = db.get_session()
    try:
        task_list = session_db.query(TaskConfig).all()
        tasks = [{
            "id": task.id,
            "taskname": task.taskname,
            "udp_port": task.udp_port,
            "create_time": str(task.create_time),
            "port": task.port,
            "cam1_ip": task.cam1_ip,
            "cam1_username": task.cam1_username,
            "cam1_password": task.cam1_password,
            "cam1_source_url": task.cam1_source_url,
            "url": task.url,
            "event_port": task.event_port,
            "test_mode": task.test_mode,
            "log_file": task.log_file,
            # "cam2_ip": task.cam2_ip,
            # "cam2_username": task.cam2_username,
            # "cam2_password": task.cam2_password,
            # "cam2_type": task.cam2_type        
        }for task in task_list]
        return response_json(200,'查询成功',tasks)
    except Exception as e:
        return response_json(500,'查询失败',str(e))
    finally:
        session_db.close()


@manager_controller.route('/task/<string:task_id>', methods=['GET'])
@login_required
def get_task_detail(task_id):
    db = dbconn.DBConn()
    session_db = db.get_session()
    try:
        task = session_db.query(TaskConfig).filter_by(id=task_id).first()
        if not task:
            return response_json(404, '任务不存在')
        return response_json(200, '查询成功', {
            'id': task.id,
            'taskname': task.taskname,
            'pid': task.pid,
            'create_time': str(task.create_time),
            'port': task.port,
            'cam1_ip': task.cam1_ip,
            'cam1_username': task.cam1_username,
            'cam1_password': task.cam1_password,
            'cam1_source_url': task.cam1_source_url,
            'url': task.url,
            'event_port': task.event_port,
            'test_mode': task.test_mode,
            'log_file': task.log_file,
        })
    except Exception as e:
        return response_json(500, '查询失败', str(e))
    finally:
        session_db.close()


@manager_controller.route('/task/<string:task_id>/log', methods=['GET'])
@login_required
def get_task_log(task_id):
    db = dbconn.DBConn()
    session_db = db.get_session()
    try:
        task = session_db.query(TaskConfig).filter_by(id=task_id).first()
        if not task:
            return response_json(404, '任务不存在')

        if not task.log_file:
            return response_json(404, '任务未记录日志文件路径')

        log_path = Path(task.log_file).expanduser()
        if not log_path.is_absolute():
            log_path = LOG_ROOT_DIR / log_path

        try:
            resolved_log_path = log_path.resolve(strict=False)
        except Exception:
            return response_json(400, '日志文件路径无效')

        if LOG_ROOT_DIR not in resolved_log_path.parents and resolved_log_path != LOG_ROOT_DIR:
            return response_json(400, '日志文件路径不受支持')

        if not resolved_log_path.exists() or not resolved_log_path.is_file():
            return response_json(404, '日志文件不存在')

        with resolved_log_path.open('r', encoding='utf-8', errors='replace') as log_fp:
            content = log_fp.read()

        return response_json(200, '查询成功', {
            'task_id': task.id,
            'taskname': task.taskname,
            'log_file': str(resolved_log_path),
            'content': content,
        })
    except Exception as e:
        return response_json(500, '读取日志失败', str(e))
    finally:
        session_db.close()


@manager_controller.route('/task/<string:task_id>', methods=['PUT'])
@login_required
def update_task(task_id):
    db = dbconn.DBConn()
    session_db = db.get_session()
    try:
        from controllers.process_controller import restart_task_with_existing_record

        payload = request.get_json(silent=True) or {}
        task = session_db.query(TaskConfig).filter_by(id=task_id).first()
        if not task:
            return response_json(404, '任务不存在')

        def normalize_str(value):
            if value is None:
                return None
            return str(value).strip()

        def normalize_int(value, field_name='字段'):
            if value in (None, ''):
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                raise ValueError(f'{field_name}必须是整数')

        taskname = normalize_str(payload.get('taskname'))
        if not taskname:
            return response_json(400, '任务名称不能为空')

        test_mode = normalize_int(payload.get('test_mode'), '测试模式')
        if test_mode not in (0, 1):
            raise ValueError('测试模式只允许为0或1')

        task.taskname = taskname
        task.udp_port = normalize_int(payload.get('udp_port'), 'UDP端口')
        task.port = normalize_int(payload.get('port'), '视频端口')
        task.event_port = normalize_int(payload.get('event_port'), '事件端口')
        task.test_mode = test_mode
        task.cam1_ip = normalize_str(payload.get('cam1_ip'))
        task.cam1_username = normalize_str(payload.get('cam1_username'))
        task.cam1_password = normalize_str(payload.get('cam1_password'))
        task.cam1_source_url = normalize_str(payload.get('cam1_source_url'))
        task.url = normalize_str(payload.get('url'))
        task.update_time = datetime.now()

        new_task = restart_task_with_existing_record(session_db, task)
        return response_json(200, '修改成功，任务已重启', {
            'id': new_task.id,
            'taskname': new_task.taskname,
            'udp_port': new_task.udp_port,
            'port': new_task.port,
            'event_port': new_task.event_port,
            'cam1_ip': new_task.cam1_ip,
            'cam1_username': new_task.cam1_username,
            'cam1_password': new_task.cam1_password,
            'cam1_source_url': new_task.cam1_source_url,
            'url': new_task.url,
            'test_mode': new_task.test_mode,
            'pid': new_task.pid,
            'update_time': str(new_task.update_time) if new_task.update_time else None,
        })
    except ValueError as e:
        session_db.rollback()
        return response_json(400, str(e))
    except Exception as e:
        session_db.rollback()
        return response_json(500, '修改失败', str(e))
    finally:
        session_db.close()