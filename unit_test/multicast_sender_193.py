#!/usr/bin/env python3
"""海面光电监视设备组播报文模拟发送程序

根据通信协议文档 (v0.03) 模拟开发板发送组播报文，用于测试接收端程序。

支持报文类型：
  1. 负载状态上报 (地址位 0x00/0x01)
  2. 目标识别信息上报 (地址位 0x02)
  3. 跟踪状态上报 (地址位 0x03)
  4. 扫描方式状态上报 (地址位 0x06)

用法示例:
  # 发送负载状态上报报文（默认）
  python multicast_sender_193.py --type payload --count 10

  # 发送跟踪状态上报报文
  python multicast_sender_193.py --type track --count 10

  # 发送识别信息上报报文
  python multicast_sender_193.py --type identify --count 10

  # 发送扫描方式状态上报报文
  python multicast_sender_193.py --type scan --count 10

  # 自定义组播地址和端口
  python multicast_sender_193.py --multicast-group 239.255.43.21 --multicast-port 23232

  # 持续发送（每秒1个）
  python multicast_sender_193.py --type payload --count 0 --interval 1.0

  # 指定网络接口
  python multicast_sender_193.py --interface ppp0
"""

import socket
import sys
import time
import argparse
import logging
import signal
import fcntl
import struct
import random
from struct import pack, unpack

# 组播配置
MULTICAST_GROUP = '239.255.43.21'
MULTICAST_PORT = 23232
DEFAULT_INTERFACE = 'wlan0'

# 协议常量
FRAME_HEADER_PAYLOAD = 0xF11F  # 回送报文帧头（小端: 1F F1）
FRAME_TAIL_PAYLOAD = 0x1FF1     # 回送报文帧尾（小端: F1 1F）
FRAME_HEADER_COMMAND = 0x0FF0   # 命令报文帧头
FRAME_TAIL_COMMAND = 0xF00F     # 命令报文帧尾

# 地址位常量
ADDR_VISIBLE_LIGHT_TRACK = 0x00   # 可见光跟踪处理器
ADDR_IR_TRACK = 0x01              # 红外跟踪处理器
ADDR_VISIBLE_LIGHT_CAM = 0x02     # 可见光摄像机
ADDR_IR_CAM = 0x03                # 红外热像仪
ADDR_ENV_CTRL = 0x04              # 环控设备
ADDR_SERVO = 0x05                 # 光电转台伺服
ADDR_SCAN_GEN = 0x06              # 扫描生成器
ADDR_OSD_INFO = 0x07              # OSD实时信息

# 回送报文地址位
ADDR_PAYLOAD_STATUS = 0x00        # 负载状态（动态，00=白光通道，01=红外通道）
ADDR_IDENTIFY_INFO = 0x02         # 识别信息
ADDR_TRACK_INFO = 0x03            # 跟踪信息

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

running = True


def signal_handler(sig, frame):
    """处理中断信号。"""
    global running
    logger.info("收到中断信号，正在停止发送...")
    running = False


def get_interface_ipv4(iface_name: str) -> str:
    """获取指定网络接口的 IPv4 地址。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        request = struct.pack('256s', iface_name[:15].encode('utf-8'))
        response = fcntl.ioctl(sock.fileno(), 0x8915, request)
        return socket.inet_ntoa(response[20:24])
    finally:
        sock.close()


def create_multicast_socket(iface_name: str = DEFAULT_INTERFACE) -> socket.socket:
    """创建用于发送组播数据的 UDP 套接字。"""
    try:
        interface_ip = get_interface_ipv4(iface_name)
    except Exception as e:
        logger.warning(f"无法获取接口 {iface_name} 的 IPv4 地址: {e}")
        interface_ip = None

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

    try:
        so_bind = getattr(socket, 'SO_BINDTODEVICE', 25)
        sock.setsockopt(socket.SOL_SOCKET, so_bind, iface_name.encode() + b'\0')
        logger.info(f"已绑定设备: {iface_name}")
    except PermissionError:
        logger.warning("绑定设备需要 root 权限，跳过 SO_BINDTODEVICE 设置")
    except OSError as e:
        logger.warning(f"绑定设备失败: {e}")
    except Exception:
        pass

    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 32)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)

    if interface_ip:
        try:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(interface_ip))
            logger.info(f"发送网卡:   {iface_name} ({interface_ip})")
        except OSError as e:
            logger.warning(f"设置 IP_MULTICAST_IF 失败: {e}")
    else:
        logger.info(f"发送网卡:   {iface_name} (IP 未知)")

    return sock


# ============================================================================
# 协议构建函数
# ============================================================================

def calc_checksum_low_byte(data: bytes) -> int:
    """计算校验位：地址位到数据位所有字节的和，取低位1字节。"""
    return sum(data) & 0xFF


def calc_xor_checksum(data: bytes) -> int:
    """计算异或校验位。"""
    result = 0
    for b in data:
        result ^= b
    return result


def build_payload_status_packet(channel: int = 0, frame_seq: int = 0,
                                 ir_focal_length: float = 50.0,
                                 visible_focal_length: float = 100.0,
                                 az_err: float = 1.5,
                                 el_err: float = -2.3,
                                 env_ctrl: int = 0x010002FF,
                                 servo_az: float = 120.5,
                                 servo_el: float = 45.2,
                                 self_check_status: int = 0x0F,
                                 cam_image_status: int = 0x00,
                                 cam_comm_status: int = 0x00,
                                 tracker_temp: int = 35,
                                 cam_temp: int = 32,
                                 elec_zoom: int = 0x00,
                                 electronic_mist: int = 0x00,
                                 exposure_time: int = 33,
                                 detect_threshold: int = 50,
                                 track_threshold: int = 60,
                                 memory_track_time: int = 2000) -> bytes:
    """构建负载状态上报报文 (地址位 0x00/0x01)。
    
    协议格式 (Table 3-11, 3-12):
    帧头(2) + 地址位(1) + 帧序号(2) + 数据区(41) + 校验(1) + 帧尾(2) = 48字节
    但实际原始数据为49字节，数据区为42字节（含帧头重复）
    
    根据原始数据分析:
    1f f1 | 00 | f7 7f | [41字节数据] | 76 | f1 1f
    """
    # 帧头 (小端)
    frame_header = pack('<H', FRAME_HEADER_PAYLOAD)  # 1F F1
    
    # 地址位 (0=白光通道, 1=红外通道)
    addr_byte = pack('B', channel)
    
    # 帧序号 (小端)
    seq_bytes = pack('<H', frame_seq & 0xFFFF)
    
    # 数据区 (41字节)
    data = bytearray()
    
    # Byte 5: 保留
    data.append(0x00)
    
    # Byte 6-9: 红外焦距 (float)
    data.extend(pack('<f', ir_focal_length))
    
    # Byte 10-13: 白光焦距 (float)
    data.extend(pack('<f', visible_focal_length))
    
    # Byte 14-17: 方位脱靶量 (float)
    data.extend(pack('<f', az_err))
    
    # Byte 18-21: 俯仰脱靶量 (float)
    data.extend(pack('<f', el_err))
    
    # Byte 22-25: 环控设备
    # 格式: 01**02** (**: 00关闭/FF打开)
    # 按小端字节顺序逐字节写入，严格对应 C++ 实现中 env_ctrl_byte1..4 的写入顺序
    env = env_ctrl & 0xFFFFFFFF
    data.append(env & 0xFF)
    data.append((env >> 8) & 0xFF)
    data.append((env >> 16) & 0xFF)
    data.append((env >> 24) & 0xFF)
    
    # Byte 26-29: 伺服方位角 (float)
    data.extend(pack('<f', servo_az))
    
    # Byte 30-33: 伺服俯仰角 (float)
    data.extend(pack('<f', servo_el))
    
    # Byte 34: 自检状态
    # Bit0: 分系统正常/异常, Bit1: 相机正常/异常, Bit2: 跟踪处理器正常/异常
    # Bit3: 0=自检结束, 1=自检中
    data.append(self_check_status & 0xFF)
    
    # Byte 35: 可见光摄像机图像状态 (00=有图像, 01=无图像)
    data.append(cam_image_status & 0xFF)
    
    # Byte 36: 可见光摄像机通信状态 (00=有通信, 01=无通信)
    data.append(cam_comm_status & 0xFF)
    
    # Byte 37: 跟踪处理器温度 (摄氏度)
    data.append(tracker_temp & 0xFF)
    
    # Byte 38: 可见光摄像机温度 (摄氏度)
    data.append(cam_temp & 0xFF)
    
    # Byte 39: 电子放大状态 (00=无变倍, 01=2X, 02=4X)
    data.append(elec_zoom & 0xFF)
    
    # Byte 40: 电子透雾状态 (00=无效, 01=有效)
    data.append(electronic_mist & 0xFF)
    
    # Byte 41: 当前曝光时间 (单位: 0.1毫秒)
    data.append(exposure_time & 0xFF)
    
    # Byte 42: 当前检测/识别阈值 (0-100)
    data.append(detect_threshold & 0xFF)
    
    # Byte 43: 当前跟踪阈值 (0-100)
    data.append(track_threshold & 0xFF)
    
    # Byte 44-45: 当前记忆跟踪时间 (毫秒)
    data.extend(pack('<H', memory_track_time & 0xFFFF))
    
    # 补齐到41字节
    while len(data) < 41:
        data.append(0x00)
    
    data = bytes(data)
    
    # 校验位: 地址位到数据位的和，取低位1字节
    checksum_data = addr_byte + seq_bytes + data
    checksum = calc_checksum_low_byte(checksum_data)
    
    # 帧尾 (小端)
    frame_tail = pack('<H', FRAME_TAIL_PAYLOAD)  # F1 1F
    
    # 组装完整报文
    packet = frame_header + checksum_data + pack('B', checksum) + frame_tail
    
    return packet


def build_identify_packet(channel: int = 0x01, frame_seq: int = 0,
                           year: int = 2026, month: int = 6, day: int = 1,
                           hour: int = 10, minute: int = 30, second: int = 0, ms: int = 0,
                           target_type: int = 0x01, target_confidence: int = 85,
                           x_missile: int = 100, y_missile: int = 200) -> bytes:
    """构建目标识别信息上报报文 (地址位 0x02)。
    
    协议格式 (Table 3-13):
    帧头(2) + 地址位(1) + 通道(1) + 时间(8) + 识别数据组(6*N) + 校验(1) + 帧尾(2)
    """
    # 帧头 (小端)
    frame_header = pack('<H', FRAME_HEADER_PAYLOAD)  # 1F F1
    
    # 地址位
    addr_byte = pack('B', ADDR_IDENTIFY_INFO)
    
    # 通道 (0x01=可见光, 0x02=红外)
    ch_byte = pack('B', channel)
    
    # 时间 (8字节)
    time_bytes = pack('<HBBBHHH', year, month, day, hour, minute, second, ms)
    
    # 识别数据组 (6字节/组)
    # 目标类型(1) + 置信度(1) + x脱靶量(2) + y脱靶量(2)
    # 可见光: Bit0=无人机, Bit1=鸟类
    identify_data = pack('<BBHH', target_type, target_confidence, x_missile, y_missile)
    
    # 补齐到最多5组目标
    while len(identify_data) < 6:
        identify_data += pack('<BBHH', 0, 0, 0, 0)
    
    data = ch_byte + time_bytes + identify_data
    
    # 补齐到合适长度
    while len(data) < 18:
        data += b'\x00'
    
    # 校验位
    checksum_data = addr_byte + data
    checksum = calc_checksum_low_byte(checksum_data)
    
    # 帧尾
    frame_tail = pack('<H', FRAME_TAIL_PAYLOAD)
    
    packet = frame_header + checksum_data + pack('B', checksum) + frame_tail
    
    return packet


def build_track_packet(channel: int = 0x01, frame_seq: int = 0,
                        year: int = 2026, month: int = 6, day: int = 1,
                        hour: int = 10, minute: int = 30, second: int = 0, ms: int = 0,
                        track_status: int = 0x01, detect_status: int = 0x00,
                        exposure_time: int = 33, detect_threshold: int = 50,
                        track_threshold: int = 60, memory_track_time: int = 2000) -> bytes:
    """构建跟踪状态上报报文 (地址位 0x03)。
    
    协议格式:
    帧头(2) + 地址位(1) + 通道(1) + 时间(8) + 跟踪状态(1) + 检测状态(1) + 
    曝光时间(1) + 检测阈值(1) + 跟踪阈值(1) + 记忆时间(2) + 校验(1) + 帧尾(2)
    """
    # 帧头
    frame_header = pack('<H', FRAME_HEADER_PAYLOAD)
    
    # 地址位
    addr_byte = pack('B', ADDR_TRACK_INFO)
    
    # 通道
    ch_byte = pack('B', channel)
    
    # 时间
    time_bytes = pack('<HBBBHHH', year, month, day, hour, minute, second, ms)
    
    # 数据区
    data = bytearray()
    
    # Byte 12: 跟踪状态 (0x00=未跟踪, 0x01=正常跟踪, 0x10=记忆跟踪, 0x11=丢失)
    data.append(track_status & 0xFF)
    
    # Byte 13: 检测/识别状态 (0x00=关, 0x01=检测有效, 0x02=识别有效)
    data.append(detect_status & 0xFF)
    
    # Byte 14: 当前曝光时间
    data.append(exposure_time & 0xFF)
    
    # Byte 15: 当前检测/识别阈值
    data.append(detect_threshold & 0xFF)
    
    # Byte 16: 当前跟踪阈值
    data.append(track_threshold & 0xFF)
    
    # Byte 17-18: 记忆跟踪时间
    data.extend(pack('<H', memory_track_time & 0xFFFF))
    
    data = bytes(data)
    
    # 校验位
    checksum_data = addr_byte + ch_byte + time_bytes + data
    checksum = calc_checksum_low_byte(checksum_data)
    
    # 帧尾
    frame_tail = pack('<H', FRAME_TAIL_PAYLOAD)
    
    packet = frame_header + checksum_data + pack('B', checksum) + frame_tail
    
    return packet


def build_scan_status_packet(scan_type: int = 0x01, frame_seq: int = 0,
                               scan_speed: float = 10.5, stay_time: int = 500,
                               az_start: int = -30, az_end: int = 30,
                               az_step: int = 1, py_start: int = -10, py_end: int = 10) -> bytes:
    """构建扫描方式状态上报报文 (地址位 0x06)。
    
    协议格式:
    帧头(2) + 地址位(1) + 功能位(1) + 数据区(13) + 校验(1) + 帧尾(2)
    """
    # 帧头
    frame_header = pack('<H', FRAME_HEADER_PAYLOAD)
    
    # 地址位
    addr_byte = pack('B', ADDR_SCAN_GEN)
    
    # 功能位
    func_byte = pack('B', 0x01)  # 设定扫描方式
    
    # 数据区 (15字节固定，未使用部分补0)
    data = bytearray()
    
    if scan_type == 0x01:  # 路径巡航
        data.extend(pack('<f', scan_speed))
        data.append(stay_time & 0xFF)
        while len(data) < 15:
            data.append(0x00)
    
    elif scan_type == 0x02:  # 线扫
        data.extend(pack('<i', az_start))
        data.extend(pack('<i', az_end))
        data.extend(pack('<f', scan_speed))
        while len(data) < 15:
            data.append(0x00)
    
    elif scan_type == 0x03:  # 帧扫描
        data.extend(pack('<i', az_start))
        data.extend(pack('<i', az_end))
        data.extend(pack('<i', az_step))
        data.append(stay_time & 0xFF)
        while len(data) < 15:
            data.append(0x00)
    
    elif scan_type == 0x04:  # 苹果皮扫描
        data.extend(pack('<i', py_start))
        data.extend(pack('<i', py_end))
        data.extend(pack('<f', scan_speed))
        while len(data) < 15:
            data.append(0x00)
    
    else:
        data.extend(pack('<f', scan_speed))
        data.append(stay_time & 0xFF)
        while len(data) < 15:
            data.append(0x00)
    
    data = bytes(data[:15])
    
    # 校验位
    checksum_data = addr_byte + func_byte + data
    checksum = calc_checksum_low_byte(checksum_data)
    
    # 帧尾
    frame_tail = pack('<H', FRAME_TAIL_PAYLOAD)
    
    packet = frame_header + pack('B', frame_seq & 0xFF) + checksum_data + pack('B', checksum) + frame_tail
    
    return packet


# ============================================================================
# 报文解析显示
# ============================================================================

def parse_payload_status(packet: bytes) -> dict:
    """解析负载状态上报报文。"""
    result = {}
    if len(packet) < 48:
        return {'error': '报文长度不足'}
    
    result['帧头'] = hex(unpack('<H', packet[0:2])[0])
    result['地址位'] = hex(packet[2])
    result['帧序号'] = unpack('<H', packet[3:5])[0]
    
    # 红外焦距
    result['红外焦距'] = unpack('<f', packet[6:10])[0]
    # 白光焦距
    result['白光焦距'] = unpack('<f', packet[10:14])[0]
    # 方位脱靶量
    result['方位脱靶量'] = unpack('<f', packet[14:18])[0]
    # 俯仰脱靶量
    result['俯仰脱靶量'] = unpack('<f', packet[18:22])[0]
    # 环控设备
    result['环控设备'] = hex(unpack('<I', packet[22:26])[0])
    # 伺服方位角
    result['伺服方位角'] = unpack('<f', packet[26:30])[0]
    # 伺服俯仰角
    result['伺服俯仰角'] = unpack('<f', packet[30:34])[0]
    # 自检状态
    result['自检状态'] = bin(packet[34])
    # 图像状态
    result['图像状态'] = '有图像' if packet[35] == 0 else '无图像'
    # 通信状态
    result['通信状态'] = '有通信' if packet[36] == 0 else '无通信'
    # 温度
    result['跟踪处理器温度'] = packet[37]
    result['可见光摄像机温度'] = packet[38]
    # 电子放大
    zoom_map = {0: '无变倍', 1: '2X', 2: '4X'}
    result['电子放大状态'] = zoom_map.get(packet[39], f'未知({packet[39]})')
    # 透雾
    result['电子透雾状态'] = '有效' if packet[40] == 1 else '无效'
    # 曝光时间
    result['当前曝光时间'] = f"{packet[41] * 0.1}ms"
    # 阈值
    result['检测/识别阈值'] = packet[42]
    result['跟踪阈值'] = packet[43]
    # 记忆跟踪时间
    result['记忆跟踪时间'] = unpack('<H', packet[44:46])[0]
    
    return result


def format_hex(data: bytes) -> str:
    """格式化字节数据为十六进制字符串。"""
    return ' '.join(f'{b:02x}' for b in data)


def run_sender(count: int = 10, interval: float = 1.0, packet_type: str = 'payload',
                interface: str = DEFAULT_INTERFACE, multicast_group: str = MULTICAST_GROUP,
                multicast_port: int = MULTICAST_PORT, channel: int = 0,
                ir_focal: float = 50.0, visible_focal: float = 100.0,
                servo_az: float = 120.5, servo_el: float = 45.2,
                track_status: int = 0x01, scan_type: int = 0x01):
    """运行组播发送器。"""
    global running
    
    sock = create_multicast_socket(interface)
    
    logger.info("=" * 70)
    logger.info("海面光电监视设备组播报文模拟发送器")
    logger.info("=" * 70)
    logger.info(f"组播地址:     {multicast_group}")
    logger.info(f"组播端口:     {multicast_port}")
    logger.info(f"发送次数:     {count if count > 0 else '无限'}")
    logger.info(f"发送间隔:     {interval} 秒")
    logger.info(f"报文类型:     {packet_type}")
    logger.info(f"网络接口:     {interface}")
    logger.info("=" * 70)
    
    sent_count = 0
    start_time = time.time()
    frame_seq = 0
    # 确保以下值为 Python 的 float 类型，pack('<f', ...) 会把它们打为 4 字节单精度浮点
    ir_focal = float(ir_focal)
    visible_focal = float(visible_focal)
    servo_az = float(servo_az)
    servo_el = float(servo_el)
    
    try:
        while running:
            if count > 0 and sent_count >= count:
                break
            
            # 根据类型构建报文
            if packet_type == 'payload':
                # 负载状态上报
                frame_seq = (frame_seq + 1) & 0xFFFF
                # 切换通道: 0=白光, 1=红外
                ch = sent_count % 2
                packet = build_payload_status_packet(
                    channel=ch,
                    frame_seq=frame_seq,
                    ir_focal_length=float(ir_focal),
                    visible_focal_length=float(visible_focal),
                    az_err=float(1.5 + random.uniform(-0.5, 0.5)),
                    el_err=float(-2.3 + random.uniform(-0.5, 0.5)),
                    servo_az=float(servo_az + random.uniform(-1, 1)),
                    servo_el=float(servo_el + random.uniform(-0.5, 0.5)),
                    self_check_status=0x0F,
                    tracker_temp=35 + random.randint(-2, 2),
                    cam_temp=32 + random.randint(-2, 2),
                )
            elif packet_type == 'identify':
                frame_seq = (frame_seq + 1) & 0xFFFF
                packet = build_identify_packet(
                    channel=0x01,
                    frame_seq=frame_seq,
                    target_type=0x01,  # 无人机
                    target_confidence=85,
                    x_missile=100 + random.randint(-10, 10),
                    y_missile=200 + random.randint(-10, 10),
                )
            elif packet_type == 'track':
                frame_seq = (frame_seq + 1) & 0xFFFF
                # 切换通道
                ch = sent_count % 2
                ch_byte = 0x01 if ch == 0 else 0x02
                packet = build_track_packet(
                    channel=ch_byte,
                    frame_seq=frame_seq,
                    track_status=track_status,
                    detect_status=0x01,
                )
            elif packet_type == 'scan':
                frame_seq = (frame_seq + 1) & 0xFFFF
                packet = build_scan_status_packet(
                    scan_type=scan_type,
                    frame_seq=frame_seq,
                    scan_speed=float(10.5 + random.uniform(-1, 1)),
                )
            else:
                logger.error(f"未知报文类型: {packet_type}")
                break
            
            # 发送报文
            sock.sendto(packet, (multicast_group, multicast_port))
            sent_count += 1
            
            # 显示报文信息
            logger.info(f"[#{sent_count}] 类型={packet_type}, 长度={len(packet)}字节, HEX={format_hex(packet[:10])}...{format_hex(packet[-3:])}")
            
            if packet_type == 'payload':
                parsed = parse_payload_status(packet)
                for key, value in parsed.items():
                    logger.info(f"  {key}: {value}")
            
            # 等待间隔
            time.sleep(interval)
            
    finally:
        sock.close()
    
    elapsed = time.time() - start_time
    logger.info("=" * 70)
    logger.info("发送统计")
    logger.info("=" * 70)
    logger.info(f"运行时长:   {elapsed:.1f} 秒")
    logger.info(f"发送报文:   {sent_count} 个")
    if elapsed > 0:
        logger.info(f"发送速率:   {sent_count / elapsed:.2f} 个/秒")
    logger.info("=" * 70)


def main():
    """主函数。"""
    parser = argparse.ArgumentParser(
        description='海面光电监视设备组播报文模拟发送程序',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 发送负载状态上报报文
  python multicast_sender_193.py --type payload --count 10
  
  # 发送跟踪状态上报报文
  python multicast_sender_193.py --type track --count 10 --interval 0.02
  
  # 发送识别信息上报报文
  python multicast_sender_193.py --type identify --count 5
  
  # 发送扫描方式状态上报报文
  python multicast_sender_193.py --type scan --scan-type 2 --count 5
        """
    )
    
    parser.add_argument('--count', '-n', type=int, default=10000000,
                        help='发送次数 (默认: 10000000, 0表示持续发送)')
    parser.add_argument('--interval', '-i', type=float, default=1.0,
                        help='发送间隔秒数 (默认: 1.0)')
    parser.add_argument('--type', '-t', type=str, default='payload',
                        choices=['payload', 'identify', 'track', 'scan'],
                        help='报文类型 (默认: payload)')
    parser.add_argument('--interface', '-f', type=str, default=DEFAULT_INTERFACE,
                        help=f'网络接口名称 (默认: {DEFAULT_INTERFACE})')
    parser.add_argument('--multicast-group', '-g', type=str, default=MULTICAST_GROUP,
                        help=f'组播组地址 (默认: {MULTICAST_GROUP})')
    parser.add_argument('--multicast-port', '-p', type=int, default=MULTICAST_PORT,
                        help=f'组播端口 (默认: {MULTICAST_PORT})')
    parser.add_argument('--channel', '-c', type=int, default=0,
                        choices=[0, 1],
                        help='通道选择 (默认: 0=白光通道)')
    
    # 负载状态相关参数
    parser.add_argument('--ir-focal', type=float, default=50.0,
                        help='红外焦距 (默认: 50.0)')
    parser.add_argument('--visible-focal', type=float, default=100.0,
                        help='白光焦距 (默认: 100.0)')
    parser.add_argument('--servo-az', type=float, default=120.5,
                        help='伺服方位角 (默认: 120.5)')
    parser.add_argument('--servo-el', type=float, default=45.2,
                        help='伺服俯仰角 (默认: 45.2)')
    
    # 跟踪状态相关参数
    parser.add_argument('--track-status', type=int, default=0x01,
                        choices=[0x00, 0x01, 0x10, 0x11],
                        help='跟踪状态 (默认: 0x01=正常跟踪)')
    
    # 扫描方式相关参数
    parser.add_argument('--scan-type', type=int, default=0x01,
                        choices=[0x01, 0x02, 0x03, 0x04],
                        help='扫描类型 (默认: 0x01=路径巡航)')
    
    args = parser.parse_args()
    
    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    run_sender(
        count=args.count,
        interval=args.interval,
        packet_type=args.type,
        interface=args.interface,
        multicast_group=args.multicast_group,
        multicast_port=args.multicast_port,
        channel=args.channel,
        ir_focal=args.ir_focal,
        visible_focal=args.visible_focal,
        servo_az=args.servo_az,
        servo_el=args.servo_el,
        track_status=args.track_status,
        scan_type=args.scan_type,
    )


if __name__ == '__main__':
    main()