"""UDP 监听服务程序。

功能：
- 系统启动时开始监听 UDP 报文
- 支持单播和组播模式
- 收到报文后获取来源 IP，查询数据库中 cam1_ip 字段
- 如果存在，则根据记录的 udp_port 字段值，将原文 UDP 报文转发到 localhost 的对应端口
- 支持组播加入，监听组播地址
"""

import socket
import threading
import logging
import struct
import fcntl
from typing import Optional, Dict, List, Tuple

from sqlalchemy import text
from db.dbconn import DBConn

logger = logging.getLogger(__name__)

# 默认监听的 UDP 端口，可通过配置文件修改
DEFAULT_UDP_PORT = 9000

# 组播配置默认值
DEFAULT_MULTICAST_GROUP = '239.255.43.21'
DEFAULT_MULTICAST_PORT = 23232
DEFAULT_TTL = 1
DEFAULT_INTERFACE = '0.0.0.0'
DEFAULT_INTERFACE_NAME = 'wlan0'  # 默认网络接口名称（可根据实际环境修改）

# 组播地址范围定义 (224.0.0.0 - 239.255.255.255)
# 224 = 0xE0, 240 = 0xF0
MULTICAST_IP_START = 224
MULTICAST_IP_END = 239


def is_multicast_ip(ip: str) -> bool:
    """判断IP地址是否为组播地址。
    
    组播地址范围: 224.0.0.0 - 239.255.255.255
    """
    try:
        ip_bytes = socket.inet_aton(ip)
        first_octet = ip_bytes[0]
        return 224 <= first_octet <= 239
    except (socket.error, ValueError):
        return False




class MulticastGroup:
    """组播组配置。"""
    
    def __init__(self, group_address: str, group_port: int, interface: str = DEFAULT_INTERFACE, 
                 ttl: int = DEFAULT_TTL, interface_name: str = DEFAULT_INTERFACE_NAME):
        self.group_address = group_address  # 组播IP地址
        self.group_port = group_port        # 组播端口
        self.interface = interface          # 网络接口IP（用于加入组播组）
        self.interface_name = interface_name  # 网络接口名称（如eth0）
        self.ttl = ttl                      # 生存时间
        self.socket: Optional[socket.socket] = None
        self.iface_ip: str = '0.0.0.0'      # 接口IP地址
        self.iface_index: int = 0           # 接口索引


class UDPUdpListener:
    """UDP 监听与转发服务。"""

    def __init__(self, listen_port: int = DEFAULT_UDP_PORT, multicast_groups: Optional[List[Dict]] = None):
        """初始化UDP监听器。
        
        Args:
            listen_port: 单播监听端口
            multicast_groups: 组播组配置列表，格式为:
                [
                    {"group_address": "224.0.0.1", "group_port": 9001, "interface": "0.0.0.0", "ttl": 1},
                    ...
                ]
        """
        self.listen_port = listen_port
        self.server_socket: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None       
        self._multicast_sockets: List[MulticastGroup] = []  # 组播套接字列表
        self._multicast_threads: List[threading.Thread] = []  # 组播监听线程
        
        # 解析组播组配置
        if multicast_groups:
            for group_config in multicast_groups:
                mc = MulticastGroup(
                    group_address=group_config.get('group_address', DEFAULT_MULTICAST_GROUP),
                    group_port=group_config.get('group_port', DEFAULT_MULTICAST_PORT),
                    interface=group_config.get('interface', DEFAULT_INTERFACE),
                    ttl=group_config.get('ttl', DEFAULT_TTL)
                )
                self._multicast_sockets.append(mc)

    def start(self) -> None:
        """启动 UDP 监听服务（在新线程中运行）。"""
        if self._running:
            logger.warning('UDP listener already running')
            return

        self._running = True        
        
        # 启动组播监听（在单播监听之前，确保组播组提前加入）
        if self._multicast_sockets:
            for mc_group in self._multicast_sockets:
                # 解析接口IP和索引
                self._resolve_interface(mc_group)
                mc_thread = threading.Thread(
                    target=self._run_multicast_server,
                    args=(mc_group,),
                    daemon=True,
                    name=f"Multicast-{mc_group.group_address}:{mc_group.group_port}"
                )
                mc_thread.start()
                self._multicast_threads.append(mc_thread)
                logger.info(f'Multicast listener started for group {mc_group.group_address}:{mc_group.group_port}')
            logger.info(f'UDP listener started with {len(self._multicast_sockets)} multicast group(s)')
        
        # 启动单播监听
        self._thread = threading.Thread(target=self._run_server, daemon=True)
        self._thread.start()
        logger.info(f'UDP listener started on port {self.listen_port}')
        
        logger.info('UDP listener started')

    def stop(self) -> None:
        """停止 UDP 监听服务。"""
        self._running = False
        
        # 关闭单播套接字
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
        
        # 关闭组播套接字并离开组播组
        for mc_group in self._multicast_sockets:
            if mc_group.socket:
                try:
                    # 离开组播组
                    group = socket.inet_aton(mc_group.group_address)
                    if mc_group.iface_ip != '0.0.0.0':
                        mc_group.socket.setsockopt(
                            socket.IPPROTO_IP,
                            socket.IP_DROP_MEMBERSHIP,
                            group + socket.inet_aton(mc_group.iface_ip)
                        )
                    else:
                        mc_group.socket.setsockopt(
                            socket.IPPROTO_IP,
                            socket.IP_DROP_MEMBERSHIP,
                            group + socket.inet_aton('0.0.0.0')
                        )
                except Exception:
                    pass
                try:
                    mc_group.socket.close()
                except Exception:
                    pass
        
        # 等待线程结束
        if self._thread:
            self._thread.join(timeout=5)
        
        for mc_thread in self._multicast_threads:
            mc_thread.join(timeout=5)
      
        logger.info('UDP listener stopped')
    
    def _run_server(self) -> None:
        """实际运行 UDP 套接字监听的内部方法（单播）。"""
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
                # self._handle_packet(data, client_addr)
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

    def _resolve_interface(self, mc_group: MulticastGroup) -> None:
        """解析网络接口的IP地址和索引。
        
        Args:
            mc_group: 组播组配置对象
        """
        iface_name = mc_group.interface_name
        try:
            mc_group.iface_ip = self._get_interface_ip(iface_name)
            mc_group.iface_index = self._get_interface_index(iface_name)
            logger.info(f"Resolved interface {iface_name}: IP={mc_group.iface_ip}, index={mc_group.iface_index}")
        except Exception as e:
            logger.warning(f"Failed to resolve interface {iface_name}: {e}, using 0.0.0.0")
            mc_group.iface_ip = '0.0.0.0'
            mc_group.iface_index = 0

    def _get_interface_ip(self, iface_name: str) -> str:
        """获取指定网络接口的 IP 地址。"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            req = struct.pack('16sH20s', iface_name.encode(), socket.AF_INET, b'\x00' * 12)
            result = fcntl.ioctl(s.fileno(), 0x8915, req)  # SIOCGIFADDR
            ip = socket.inet_ntoa(result[20:24])
            s.close()
            return ip
        except Exception as e:
            logger.warning(f"获取接口 {iface_name} 的 IP 失败: {e}")
            return '0.0.0.0'

    def _get_interface_index(self, iface_name: str) -> int:
        """获取指定网络接口的索引。"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            result = fcntl.ioctl(s.fileno(), 0x8933, struct.pack('256s', iface_name.encode()))  # SIOCGIFINDEX
            s.close()
            index = struct.unpack('<I', result[16:20])[0]
            return index
        except Exception as e:
            logger.warning(f"获取接口 {iface_name} 的索引失败: {e}")
            return 0

    def _run_multicast_server(self, mc_group: MulticastGroup) -> None:
        """运行组播监听的内部方法。
        
        Args:
            mc_group: 组播组配置对象
        """
        try:
            # 创建组播套接字
            mc_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            mc_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # 绑定到所有接口，监听组播端口（关键：绑定 0.0.0.0 而非组播地址）
            mc_socket.bind(('0.0.0.0', mc_group.group_port))
            mc_socket.settimeout(1.0)  # 1秒超时
            
            logger.info(f"Multicast socket bound to 0.0.0.0:{mc_group.group_port}")
            
            # 设置组播TTL
            mc_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, mc_group.ttl)
            
            # 加入组播组，使用接口IP指定接口
            group = socket.inet_aton(mc_group.group_address)
            
            if mc_group.iface_index > 0 and mc_group.iface_ip != '0.0.0.0':
                # 使用接口IP加入组播组（推荐方式）
                mc_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(mc_group.iface_ip))
                mc_socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, group + socket.inet_aton(mc_group.iface_ip))
                logger.info(f"Joined multicast group {mc_group.group_address} on interface {mc_group.interface_name} ({mc_group.iface_ip})")
            else:
                # 回退到 0.0.0.0
                interface_addr = socket.inet_aton('0.0.0.0')
                mc_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, interface_addr)
                mc_socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, group + interface_addr)
                logger.info(f"Joined multicast group {mc_group.group_address} (fallback to 0.0.0.0)")
            
            # 保存套接字引用
            mc_group.socket = mc_socket

            while self._running:
                try:
                    data, client_addr = mc_socket.recvfrom(65535)
                    # 在新线程中处理接收到的数据，避免阻塞监听
                    threading.Thread(
                        target=self._handle_packet,
                        args=(data, client_addr),
                        daemon=True,
                    ).start()
                    # self._handle_packet(data, client_addr)
                except socket.timeout:
                    continue
                except OSError:
                    if self._running:
                        raise
                    break
                except Exception:
                    if self._running:
                        logger.exception(f'Error in multicast recvfrom loop for {mc_group.group_address}:{mc_group.group_port}')
                    break

        except Exception:
            logger.exception(f'Failed to start multicast server for {mc_group.group_address}:{mc_group.group_port}')
            # 清理套接字
            if mc_group.socket:
                try:
                    mc_group.socket.close()
                except Exception:
                    pass
                mc_group.socket = None

    def _handle_packet(self, data: bytes, client_addr: tuple) -> None:
        """处理单个 UDP 报文：查询 cam1_ip，转发到对应端口。"""
        source_ip = client_addr[0]
        source_port = client_addr[1]
        packet_hex = data.hex(' ')

        logger.info(
            'Received UDP packet from %s:%s, size=%s bytes, raw=%r, hex=%s',
            source_ip,
            source_port,
            len(data),
            data,
            packet_hex,
        )

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


def start_udp_listener(listen_port: int = DEFAULT_UDP_PORT, multicast_groups: Optional[List[Dict]] = None) -> UDPUdpListener:
    """启动 UDP 监听服务。
    
    Args:
        listen_port: 单播监听端口
        multicast_groups: 组播组配置列表，格式为:
            [
                {
                    "group_address": "224.0.0.1",     # 组播IP地址
                    "group_port": 9001,                # 组播端口
                    "interface": "0.0.0.0",            # 网络接口IP（可选，默认0.0.0.0）
                    "interface_name": "eth0",          # 网络接口名称（可选，默认eth0）
                    "ttl": 1                           # TTL（可选，默认1）
                },
                ...
            ]
    
    Returns:
        UDPUdpListener: UDP监听器实例
    """
    listener = get_udp_listener()
    if listen_port != DEFAULT_UDP_PORT:
        listener.listen_port = listen_port
    
    # 如果没有配置组播组，使用默认配置（来自 multicast_receiver_193 的组播组）
    if not listener._multicast_sockets:
        if multicast_groups:
            for group_config in multicast_groups:
                mc = MulticastGroup(
                    group_address=group_config.get('group_address', DEFAULT_MULTICAST_GROUP),
                    group_port=group_config.get('group_port', DEFAULT_MULTICAST_PORT),
                    interface=group_config.get('interface', DEFAULT_INTERFACE),
                    interface_name=group_config.get('interface_name', DEFAULT_INTERFACE_NAME),
                    ttl=group_config.get('ttl', DEFAULT_TTL)
                )
                listener._multicast_sockets.append(mc)
        else:
            # 默认启动 multicast_receiver_193 的组播监听
            mc = MulticastGroup(
                group_address=DEFAULT_MULTICAST_GROUP,
                group_port=DEFAULT_MULTICAST_PORT,
                interface=DEFAULT_INTERFACE,
                interface_name=DEFAULT_INTERFACE_NAME,
                ttl=DEFAULT_TTL
            )
            listener._multicast_sockets.append(mc)
            logger.info(f"Using default multicast group {DEFAULT_MULTICAST_GROUP}:{DEFAULT_MULTICAST_PORT} (from multicast_receiver_193)")
    
    listener.start()
    return listener


def stop_udp_listener() -> None:
    """停止 UDP 监听服务。"""
    global _udp_listener
    if _udp_listener:
        _udp_listener.stop()
        _udp_listener = None