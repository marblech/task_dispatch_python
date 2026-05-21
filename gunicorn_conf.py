bind = "0.0.0.0:8212"
workers = 1
# worker_class = "sync"
threads = 4
timeout = 120
accesslog = "-"
errorlog = "-"
loglevel = "info"


def post_worker_init(worker):
    # gunicorn worker 启动后初始化后台任务，避免主进程重复启动。
    from main import bootstrap_services

    bootstrap_services()
