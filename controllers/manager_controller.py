from flask import Blueprint, make_response, render_template, send_from_directory
from flask import request, jsonify,Response
from models.process import TaskConfig
from db import dbconn
from datetime import datetime  # 添加 datetime 模块
import json
import os

def response_json(code, msg, data=None):
    msg = {
        'status': code,
        'msg': msg,
        'data': data
    }
    return Response(json.dumps(msg,ensure_ascii=False),mimetype='application/json')

manager_controller = Blueprint('manager', __name__)

@manager_controller.route('/favicon.ico')
def favicon():
    return make_response('', 204)  # 返回空响应，状态码 204 表示无内容

@manager_controller.route('/list',methods=['GET'])
def task_list():
    return render_template('manager.html')

@manager_controller.route('/task_list',methods=['GET'])
def get_task_list():
    db = dbconn.DBConn()
    session = db.get_session()
    try:
        task_list = session.query(TaskConfig).all()
        tasks = [{
            "id": task.id,
            "taskname": task.taskname,
            "pid": task.pid,
            "create_time": str(task.create_time),
            "port": task.port,
            "cam1_ip": task.cam1_ip,
            "cam1_username": task.cam1_username,
            "cam1_password": task.cam1_password,
            "url": task.url,
            "event_port": task.event_port
            # "cam2_ip": task.cam2_ip,
            # "cam2_username": task.cam2_username,
            # "cam2_password": task.cam2_password,
            # "cam2_type": task.cam2_type        
        }for task in task_list]
        return response_json(200,'查询成功',tasks)
    except Exception as e:
        return response_json(500,'查询失败',str(e))


@manager_controller.route('/task/<string:task_id>', methods=['GET'])
def get_task_detail(task_id):
    db = dbconn.DBConn()
    session = db.get_session()
    try:
        task = session.query(TaskConfig).filter_by(id=task_id).first()
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
            'url': task.url,
            'event_port': task.event_port,
        })
    except Exception as e:
        return response_json(500, '查询失败', str(e))