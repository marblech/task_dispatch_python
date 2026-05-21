from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
import os
from pathlib import Path

class DBConn:
    """数据库连接操作类"""
    _instance = None  # 单例模式，确保只有一个数据库连接实例

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(DBConn, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        # 获取数据库路径
        db_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'db')
        self.db_path = os.path.join(db_dir, 'task.db')
        
        # 确保数据库目录存在
        Path(db_dir).mkdir(parents=True, exist_ok=True)
        
        # 创建数据库引擎
        self.engine = create_engine(
            f'sqlite:///{self.db_path}',
            connect_args={'check_same_thread': False},  # 允许跨线程使用连接
            pool_size=20,  # 连接池大小
            max_overflow=0  # 超出池大小的连接数
        )
        
        # 创建线程安全的会话工厂
        self.session_factory = sessionmaker(bind=self.engine)
        self.Session = scoped_session(self.session_factory)

    def get_session(self):
        """获取数据库会话"""
        return self.Session

    def close_session(self):
        """关闭数据库会话"""
        self.Session.remove()