from flask import Flask
from flask_cors import CORS
from sqlalchemy import delete
from models.process import TaskConfig
from ini_file_controller.ini_file_helper import IniFileHelper
from controllers.process_controller import process_bp
from controllers.manager_controller import manager_controller
from task_controller.task_starter import start_task_process, is_managed_temp_model_file
from task_controller.cleanup_daemon import start_cleanup_daemon
import time

from db import dbconn
import os
from pathlib import Path

DEBUG_MODE = False
HOST = '0.0.0.0'
PORT = 8212
DIRECT_RUN_THREADED = DEBUG_MODE


def create_app():
    app = Flask(__name__)
    CORS(app)
    app.register_blueprint(process_bp)
    app.register_blueprint(manager_controller)
    return app

#启动后自动恢复运行任务
def autostart_task():
    db = dbconn.DBConn()
    session = db.get_session()
    from http_request_util.data_syn_controller import syn_task_data
    from models.task_return import TaskReturn
    try:
        search_task = session.query(TaskConfig).all()
        for task in search_task:
            task.action = 1
            start_task_process(task, task.port)
            session.add(task)
            session.commit()
            session.refresh(task)
            task_return = TaskReturn()
            task_return.camId = task.cam1_id
            task_return.id = task.cam1_id
            task_return.pid = task.pid
            task_return.stream_url = task.url
            task_return.stream_port = task.port                
            task_return.event_port = task.event_port  
            syn_task_data(task_return.to_dict())
            time.sleep(1)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
def clean_tasktable():
    db = dbconn.DBConn()
    session = db.get_session()
    search_task = session.query(TaskConfig).all()
    for item in search_task:
        if item.ini_file:
            IniFileHelper.delete_file(Path(item.ini_file), ignore_mission=True)
        # IniFileHelper.delete_file(item.resnet_file,ignore_mission=True)
        if item.yolo_file and is_managed_temp_model_file(item.yolo_file):
            IniFileHelper.delete_file(Path(item.yolo_file), ignore_mission=True)
    session.execute(delete(TaskConfig))
    session.commit()
    # session.commit()
    
# def syn_task():
#     from http_request_util.data_syn_controller import syn_task_data
#     syn_task_data()


def start_background_services():
    try:
        start_cleanup_daemon(interval_seconds=60)
    except RuntimeError as exc:
        print(f'[bootstrap] cleanup daemon not started: {exc}')


app = create_app()


def bootstrap_services():
    """启动后端守护任务与任务恢复流程。"""
    autostart_task()
    # syn_task()
    start_background_services()


def should_bootstrap_services() -> bool:
    """开发模式下仅在 Werkzeug reloader 的子进程中执行一次初始化。"""
    run_main = os.environ.get('WERKZEUG_RUN_MAIN')
    if DEBUG_MODE:
        return run_main == 'true'
    return run_main in {None, 'true'}


if __name__ == '__main__':
    # 保留本地调试直启动能力，但生产环境推荐使用 gunicorn。
    print(f"[bootstrap] debug={DEBUG_MODE}, WERKZEUG_RUN_MAIN={os.environ.get('WERKZEUG_RUN_MAIN')}")
    if should_bootstrap_services():
        print('[bootstrap] executing bootstrap_services()')
        bootstrap_services()
    else:
        print('[bootstrap] skipping bootstrap_services() in reloader parent process')
    if not DIRECT_RUN_THREADED:
        print('[bootstrap] running with threaded=Falseto avoid unbounded request threads; use gunicornin production for concurrency')
    app.run(
        debug=DEBUG_MODE,
        host=HOST,
        port=PORT,
        threaded=DIRECT_RUN_THREADED,
        use_reloader=DEBUG_MODE,
    )
