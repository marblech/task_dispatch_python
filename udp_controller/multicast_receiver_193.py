#!/usr/bin/env python3
"""专门用于接收来自开发板(193.0.1.94)发送到 239.255.43.21:23232 的组播报文。

网络环境:
- 主机 eth0 连接到开发板 (193.0.1.94)
- 开发板发送组播报文到 239.255.43.21:23232
- 主机需要加入该组播组并接收报文

用法:
    python multicast_receiver_193.py              # 默认配置运行
    python multicast_receiver_193.py --interface eth0   # 指定网络接口
    python multicast_receiver_193.py --output output.txt  # 保存到文件
"""

import socket
import sys
import signal
import time
import argparse
import logging
import os
import struct
import fcntl

# 组播配置
MULTICAST_GROUP = '239.255.43.21'
MULTICAST_PORT = 23232

# 默认网络接口
DEFAULT_INTERFACE = 'eth0'

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
    logger.info("收到中断信号，正在停止...")
    running = False


def get_interface_ip(iface_name: str) -> str:
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


def get_interface_index(iface_name: str) -> int:
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


def receive_multicast(interface: str = DEFAULT_INTERFACE, output_file: str | None = None):
    """接收组播报文。
    
    Args:
        interface: 网络接口名称 (如 eth0, wlan0)
        output_file: 可选的输出文件路径
    """
    global running
    
    iface_ip = get_interface_ip(interface)
    iface_index = get_interface_index(interface)
    
    logger.info("=" * 60)
    logger.info("组播报文接收器启动")
    logger.info("=" * 60)
    logger.info(f"组播地址:   {MULTICAST_GROUP}")
    logger.info(f"组播端口:   {MULTICAST_PORT}")
    logger.info(f"网络接口:   {interface}")
    logger.info(f"接口IP:     {iface_ip}")
    logger.info(f"接口索引:   {iface_index}")
    logger.info("=" * 60)
    
    # 创建 UDP 套接字
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    # 绑定到所有接口，监听组播端口
    sock.bind(('', MULTICAST_PORT))
    logger.info(f"套接字绑定到 0.0.0.0:{MULTICAST_PORT}")
    
    # 设置 IP_ADD_MEMBERSHIP，指定网络接口
    group = socket.inet_aton(MULTICAST_GROUP)
    
    if iface_index > 0:
        # 使用接口索引指定组播接口 (IP_MULTICAST_IF 使用网络字节序的接口索引)
        iface_bytes = socket.inet_aton(iface_ip)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, iface_bytes)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, group + iface_bytes)
    else:
        # 回退到 0.0.0.0
        interface_addr = socket.inet_aton('0.0.0.0')
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, group + interface_addr)
    
    logger.info(f"已加入组播组 {MULTICAST_GROUP} (接口: {interface})")
    
    # 设置接收超时
    sock.settimeout(1.0)
    
    packet_count = 0
    total_bytes = 0
    start_time = time.time()
    
    logger.info("开始接收组播报文... (按 Ctrl+C 停止)")
    logger.info("-" * 60)
    
    try:
        # 打开输出文件（如果指定）
        outfile = None
        if output_file:
            outfile = open(output_file, 'a')
            logger.info(f"输出文件: {output_file}")
        
        while running:
            try:
                data, addr = sock.recvfrom(65535)
                packet_count += 1
                total_bytes += len(data)
                elapsed = time.time() - start_time
                
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
                
                # 控制台输出
                logger.info(f"[{timestamp}] 收到报文 #{packet_count}")
                logger.info(f"  来源: {addr[0]}:{addr[1]}")
                logger.info(f"  长度: {len(data)} 字节")
                logger.info(f"  数据: {data}")
                logger.info(f"  十六进制: {' '.join(f'{b:02x}' for b in data[:128])}" + 
                           (f" ... (总计 {len(data)} 字节)" if len(data) > 128 else ""))
                logger.info("-" * 60)
                
                # 写入文件
                if outfile:
                    hex_data = ' '.join(f'{b:02x}' for b in data)
                    text_data = data.decode('utf-8', errors='replace')
                    outfile.write(f"{timestamp} | src={addr[0]}:{addr[1]} | len={len(data)} | data={text_data}\n")
                    outfile.flush()
                    
            except socket.timeout:
                continue
        
        # 清理
        if outfile:
            outfile.close()
            
    finally:
        # 离开组播组
        try:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, group + socket.inet_aton(iface_ip))
        except Exception:
            pass
        sock.close()
    
    # 打印统计信息
    logger.info("=" * 60)
    logger.info("接收统计")
    logger.info("=" * 60)
    logger.info(f"运行时长:   {elapsed:.1f} 秒")
    logger.info(f"收到报文:   {packet_count} 个")
    logger.info(f"总字节数:   {total_bytes} 字节 ({total_bytes / 1024:.1f} KB)")
    if elapsed > 0:
        logger.info(f"平均速率:   {total_bytes / elapsed / 1024:.1f} KB/s")
    logger.info("=" * 60)


def main():
    """主函数。"""
    parser = argparse.ArgumentParser(description='接收来自开发板的组播报文 (239.255.43.21:23232)')
    parser.add_argument('--interface', '-i', type=str, default=DEFAULT_INTERFACE,
                       help=f'网络接口名称 (默认: {DEFAULT_INTERFACE})')
    parser.add_argument('--output', '-o', type=str, default=None,
                       help='输出文件路径（可选）')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='详细输出（默认已开启详细日志）')
    
    args = parser.parse_args()
    
    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 验证接口是否存在
    if not os.path.exists(f'/sys/class/net/{args.interface}'):
        logger.error(f"网络接口 {args.interface} 不存在")
        logger.info("可用接口: " + ", ".join(os.listdir('/sys/class/net')))
        sys.exit(1)
    
    receive_multicast(interface=args.interface, output_file=args.output)


if __name__ == '__main__':
    main()