from http_request_util.http_helper import HttpClient
from db import dbconn
from datetime import datetime  # 添加 datetime 模块
import json
from models.process_manager import ProcessManager
from models.task_return import TaskReturn
from models.process import TaskConfig, Point, Camera
from mq_controller.mq_controller import start_status_thread, pm
from ini_file_controller.ini_file_helper import IniFileHelper
from models.syn_data import ResponseEnvelope
from pathlib import Path
import time
import os
from task_controller.task_starter import start_task_process,get_port


def syn_task_data(cam_config): 
    try:          
        client = HttpClient(base_url='http://192.168.1.196:8089/icdcs')
        endpoint = "/tkCam/synArStreamUrlAndPort"        
        result = client.post(endpoint=endpoint,json_data=cam_config)
        # json_str=''
        
        response_entity = ResponseEnvelope.from_dict(result)
        print(str(result))
        if response_entity.code == 200:
            print('同步成功')
        else:
            print('同步报文错误,3秒后重试')
        time.sleep(3)
    except Exception as e:
        print(f'{e}')
    return
    # while True:
    #     try:          
    #         client = HttpClient(base_url='http://172.19.0.18:8083/omp/video')
    #         endpoint = "/videoCameraLinkageAction/queryList"
    #         result = client.get(endpoint=endpoint)
    #         # json_str=''
            
    #         response_entity = ResponseEnvelope.from_dict(result)
    #         print(str(result))
    #         if response_entity.code == 200:
    #             break
    #         else:
    #             print('同步报文错误,3秒后重试')
    #             time.sleep(3)
    #     except Exception as e:
    #         print(f'{e}')
    # task_list = response_entity.to_orm_tasks()    
    # for task in task_list:
    #     if not pm.any_running_by_name(task.id):            
    #         db = dbconn.DBConn()
    #         session = db.get_session()
            
           
    #         task = start_task_process(task,None)
    #         task.region=[]
    #         task.cameras=[]
    #         task.status=1           
    #         session.add(task)
    #         session.commit()
    #         time.sleep(5)
