# Web API 启动说明

## 使用 gunicorn 启动

```bash
pip install -r requirements.txt
gunicorn -c gunicorn_conf.py main:app
```

## 说明

- `main:app` 是 WSGI 入口。
- 启动后会自动执行任务恢复、同步数据和守护清理线程初始化。
- 默认监听 `0.0.0.0:8231`。
- 本地调试仍可执行 `python main.py`，但生产环境建议统一使用 `gunicorn`。
