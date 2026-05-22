from flask import Flask
from flask_cors import CORS
from sqlalchemy import delete
from models.process import TaskConfig
from ini_file_controller.ini_file_helper import IniFileHelper
from controllers.process_controller import process_bp
from controllers.manager_controller import manager_controller
from controllers.auth_controller import auth_bp, init_default_user
from task_controller.task_starter import start_task_process, is_managed_temp_model_file
from task_controller.cleanup_daemon import start_cleanup_daemon
from udp_controller.udp_listener import DEFAULT_UDP_PORT, start_udp_listener
import time
import logging

from db import dbconn
import os
from pathlib import Path

DEBUG_MODE = False
HOST = os.environ.get('WEBAPI_HOST', '0.0.0.0')
PORT = int(os.environ.get('WEBAPI_PORT', '8212'))
UDP_LISTEN_PORT = int(os.environ.get('UDP_LISTEN_PORT', str(DEFAULT_UDP_PORT)))
DIRECT_RUN_THREADED = DEBUG_MODE


# 设置session密钥
import secrets
SESSION_SECRET = os.environ.get('SESSION_SECRET', secrets.token_hex(32))


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
    )

def create_app():
    app = Flask(__name__)
    app.secret_key = SESSION_SECRET
    CORS(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(process_bp)
    app.register_blueprint(manager_controller)
    return app

#启动后自动恢复运行任务
def autostart_task():
    db = dbconn.DBConn()
    session = db.get_session()
    from http_request_util.data_syn_controller import syn_task_data
    from models.task_return import TaskReturn
    failed_tasks = []
    try:
        search_task = session.query(TaskConfig).all()
        for task in search_task:
            try:
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

                try:
                    syn_task_data(task_return.to_dict())
                except Exception as exc:
                    print(f'[bootstrap] sync task data failed: task={task.taskname}, error={exc}')

                time.sleep(1)
            except Exception as exc:
                session.rollback()
                failed_tasks.append((task.taskname, str(exc)))
                print(f'[bootstrap] autostart task failed: task={task.taskname}, error={exc}')
    finally:
        session.close()

    if failed_tasks:
        print(f'[bootstrap] autostart finished with {len(failed_tasks)} failed task(s)')

    return failed_tasks
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

    try:
        start_udp_listener(listen_port=UDP_LISTEN_PORT)
        print(f'[bootstrap] UDP listener started successfully on port {UDP_LISTEN_PORT}')
    except Exception as exc:
        print(f'[bootstrap] UDP listener not started: {exc}')


app = create_app()


def bootstrap_services():
    """启动后端守护任务与任务恢复流程。"""
    # 初始化默认管理员账号
    init_default_user()
    
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
    configure_logging()
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
