from flask import Flask
from tornado.wsgi import WSGIContainer
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop

def create_app():
    app = Flask(__name__)
    # 在这里可以添加应用程序的配置
    return app

def run_tornado(app):
    container = WSGIContainer(app)
    http_server = HTTPServer(container)
    http_server.listen(5000)
    IOLoop.current().start()

app = create_app()

if __name__ == "__main__":
    run_tornado(app)