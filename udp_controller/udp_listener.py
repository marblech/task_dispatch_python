"""UDP 监听服务程序。

功能：
- 系统启动时开始监听 UDP 报文
- 收到报文后获取来源 IP，查询数据库中 cam1_ip 字段
- 如果存在，则根据记录的 udp_port 字段值，将原文 UDP 报文转发到 localhost 的对应端口
"""

import socket
import threading
import logging
from typing import Optional

from sqlalchemy import text
from db.dbconn import DBConn

logger = logging.getLogger(__name__)

# 默认监听的 UDP 端口，可通过配置文件修改
DEFAULT_UDP_PORT = 9000


class UDPUdpListener:
    """UDP 监听与转发服务。"""

    def __init__(self, listen_port: int = DEFAULT_UDP_PORT):
        self.listen_port = listen_port
        self.server_socket: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """启动 UDP 监听服务（在新线程中运行）。"""
        if self._running:
            logger.warning('UDP listener already running')
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_server, daemon=True)
        self._thread.start()
        logger.info(f'UDP listener started on port {self.listen_port}')

    def stop(self) -> None:
        """停止 UDP 监听服务。"""
        self._running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=5)
        logger.info('UDP listener stopped')

    def _run_server(self) -> None:
        """实际运行 UDP 套接字监听的内部方法。"""
        self.server_socket = socket.socket(
            socket.AF_INET, socket.SOCK_DGRAM
        )
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(('0.0.0.0', self.listen_port))
        self.server_socket.settimeout(1.0)  # 1秒超时，便于检查 _running 状态

        logger.info(f'UDP server listening on 0.0.0.0:{self.listen_port}')

        while self._running:
            try:
                data, client_addr = self.server_socket.recvfrom(65535)
                # 在新线程中处理接收到的数据，避免阻塞监听
                threading.Thread(
                    target=self._handle_packet,
                    args=(data, client_addr),
                    daemon=True,
                ).start()
            except socket.timeout:
                continue
            except OSError:
                if self._running:
                    raise
                break
            except Exception:
                if self._running:
                    logger.exception('Error in UDP recvfrom loop')
                break

    def _handle_packet(self, data: bytes, client_addr: tuple) -> None:
        """处理单个 UDP 报文：查询 cam1_ip，转发到对应端口。"""
        source_ip = client_addr[0]
        source_port = client_addr[1]

        logger.debug(f'Received UDP packet from {source_ip}:{source_port}, size={len(data)} bytes')

        # 查询数据库中 cam1_ip 匹配的记录，获取 udp_port
        udp_port = self._lookup_udp_port(source_ip)

        if udp_port is None:
            logger.debug(f'No record found for cam1_ip={source_ip}, skipping forward')
            return

        # 转发原始数据到 localhost 的 udp_port
        self._forward_packet(data, source_ip, udp_port)

    def _lookup_udp_port(self, cam_ip: str) -> Optional[int]:
        """根据 cam_ip 查询数据库中 cam1_ip 匹配记录的 udp_port 字段。"""
        db = DBConn()
        session = db.get_session()
        try:
            # 使用原始 SQL 查询 udp_port 字段
            result = session.execute(
                text("SELECT udp_port FROM tasktable WHERE cam1_ip = :cam_ip LIMIT 1"),
                {"cam_ip": cam_ip},
            )
            row = result.fetchone()
            if row and row[0] is not None:
                port = int(row[0])
                logger.info(f'Found udp_port={port} for cam1_ip={cam_ip}')
                return port
            logger.debug(f'cam1_ip={cam_ip} not found in tasktable')
            return None
        except Exception:
            logger.exception(f'Error looking up udp_port for cam_ip={cam_ip}')
            return None
        finally:
            session.close()

    def _forward_packet(self, data: bytes, target_ip: str, target_port: int) -> None:
        """将原始 UDP 数据转发到 localhost 的指定端口。"""
        try:
            forward_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            forward_socket.sendto(data, (target_ip, target_port))
            forward_socket.close()
            logger.info(f'Forwarded {len(data)} bytes to {target_ip}:{target_port}')
        except Exception:
            logger.exception(f'Error forwarding packet to {target_ip}:{target_port}')


# 全局单例
_udp_listener: Optional[UDPUdpListener] = None


def get_udp_listener() -> UDPUdpListener:
    """获取全局 UDP 监听器单例。"""
    global _udp_listener
    if _udp_listener is None:
        _udp_listener = UDPUdpListener()
    return _udp_listener


def start_udp_listener(listen_port: int = DEFAULT_UDP_PORT) -> UDPUdpListener:
    """启动 UDP 监听服务。"""
    listener = get_udp_listener()
    if listen_port != DEFAULT_UDP_PORT:
        listener.listen_port = listen_port
    listener.start()
    return listener


def stop_udp_listener() -> None:
    """停止 UDP 监听服务。"""
    global _udp_listener
    if _udp_listener:
        _udp_listener.stop()
        _udp_listener = None