#!/usr/bin/env python3
"""点对点 UDP 发送器（用于 unit_test）

参考 `multicast_sender_193.py` 的报文构建函数，向 localhost:12345 发送 UDP 报文，方便本地接收端测试。

用法示例:
  python udp_sender_local.py --type payload --count 10
  python udp_sender_local.py --type track --count 0 --interval 0.1
"""

import socket
import time
import argparse
import logging
import signal
import random

from multicast_sender_193 import (
    build_payload_status_packet,
    build_identify_packet,
    build_track_packet,
    build_scan_status_packet,
    format_hex,
    parse_payload_status,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

running = True


def signal_handler(sig, frame):
    global running
    logger.info("收到中断信号，停止发送...")
    running = False


def run_sender(host: str = '127.0.0.1', port: int = 12345,
               count: int = 10, interval: float = 1.0,
               packet_type: str = 'payload', channel: int = 0,
               ir_focal: float = 50.0, visible_focal: float = 100.0,
               servo_az: float = 120.5, servo_el: float = 45.2,
               track_status: int = 0x01, scan_type: int = 0x01):
    global running

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    logger.info("=" * 60)
    logger.info("点对点 UDP 发送器（本地）")
    logger.info("=" * 60)
    logger.info(f"目标地址:     {host}:{port}")
    logger.info(f"发送次数:     {count if count > 0 else '无限'}")
    logger.info(f"发送间隔:     {interval} 秒")
    logger.info(f"报文类型:     {packet_type}")
    logger.info("=" * 60)

    sent = 0
    start = time.time()
    frame_seq = 0

    # 确保以下值为 Python 的 float 类型，pack('<f', ...) 会把它们打为 4 字节单精度浮点
    ir_focal = float(ir_focal)
    visible_focal = float(visible_focal)
    servo_az = float(servo_az)
    servo_el = float(servo_el)

    try:
        while running:
            if count > 0 and sent >= count:
                break

            if packet_type == 'payload':
                frame_seq = (frame_seq + 1) & 0xFFFF
                ch = sent % 2
                packet = build_payload_status_packet(
                    channel=ch,
                    frame_seq=frame_seq,
                    ir_focal_length=float(ir_focal),
                    visible_focal_length=float(visible_focal),
                    az_err=float(1.5 + random.uniform(-0.5, 0.5)),
                    el_err=float(-2.3 + random.uniform(-0.5, 0.5)),
                    servo_az=float(servo_az + random.uniform(-1, 1)),
                    servo_el=float(servo_el + random.uniform(-0.5, 0.5)),
                )

            elif packet_type == 'identify':
                frame_seq = (frame_seq + 1) & 0xFFFF
                packet = build_identify_packet(
                    channel=0x01,
                    frame_seq=frame_seq,
                    target_type=0x01,
                    target_confidence=85,
                    x_missile=100 + random.randint(-10, 10),
                    y_missile=200 + random.randint(-10, 10),
                )

            elif packet_type == 'track':
                frame_seq = (frame_seq + 1) & 0xFFFF
                ch = sent % 2
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

            sock.sendto(packet, (host, port))
            sent += 1

            logger.info(f"[#{sent}] 类型={packet_type}, 长度={len(packet)}字节, HEX={format_hex(packet[:10])}...{format_hex(packet[-3:])}")

            if packet_type == 'payload':
                parsed = parse_payload_status(packet)
                for k, v in parsed.items():
                    logger.info(f"  {k}: {v}")

            time.sleep(interval)

    finally:
        sock.close()

    elapsed = time.time() - start
    logger.info("=" * 60)
    logger.info("发送统计")
    logger.info("=" * 60)
    logger.info(f"运行时长:   {elapsed:.1f} 秒")
    logger.info(f"发送报文:   {sent} 个")
    if elapsed > 0:
        logger.info(f"发送速率:   {sent / elapsed:.2f} 个/秒")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='本地点对点 UDP 发送器')
    parser.add_argument('--host', '-H', type=str, default='127.0.0.1', help='目标主机 (默认: localhost)')
    parser.add_argument('--port', '-P', type=int, default=12345, help='目标端口 (默认: 12345)')
    parser.add_argument('--count', '-n', type=int, default=10, help='发送次数 (0 表示无限)')
    parser.add_argument('--interval', '-i', type=float, default=1.0, help='发送间隔秒数')
    parser.add_argument('--type', '-t', type=str, default='payload', choices=['payload', 'identify', 'track', 'scan'], help='报文类型')
    parser.add_argument('--channel', '-c', type=int, default=0, choices=[0, 1], help='通道 (payload 用)')
    parser.add_argument('--ir-focal', type=float, default=50.0)
    parser.add_argument('--visible-focal', type=float, default=100.0)
    parser.add_argument('--servo-az', type=float, default=120.5)
    parser.add_argument('--servo-el', type=float, default=45.2)
    parser.add_argument('--track-status', type=int, default=0x01, choices=[0x00, 0x01, 0x10, 0x11])
    parser.add_argument('--scan-type', type=int, default=0x01, choices=[0x01, 0x02, 0x03, 0x04])

    args = parser.parse_args()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    run_sender(
        host=args.host,
        port=args.port,
        count=args.count,
        interval=args.interval,
        packet_type=args.type,
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
