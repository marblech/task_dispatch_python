import ctypes
import os
import queue
import sqlite3
import socket
import subprocess
import sys
import threading
import time
import unittest
import uuid
from pathlib import Path

from udp_controller.udp_listener import UDPUdpListener


REPO_ROOT = Path(__file__).resolve().parents[1]
CAMMON_LIB_PATH = REPO_ROOT / 'cam_wind' / 'cam_mon_cpp' / 'build' / 'libcammon.so'
TASK_DB_PATH = REPO_ROOT / 'db' / 'task.db'
USE_RUNNING_MAIN = os.environ.get('TEST_USE_RUNNING_MAIN') == '1'
SPAWN_MAIN = os.environ.get('TEST_SPAWN_MAIN') == '1'
MAIN_UDP_PORT = int(os.environ.get('TEST_MAIN_UDP_PORT', '9000'))
MAIN_HTTP_PORT = int(os.environ.get('TEST_MAIN_HTTP_PORT', '8212'))
MAIN_LOG_PATH = REPO_ROOT / 'unit_test' / '.main_udp_integration.log'


def _find_free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


def _find_free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


def _wait_for_tcp_port(host: str, port: int, timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.settimeout(1)
                sock.connect((host, port))
                return
            except OSError:
                time.sleep(0.1)
    raise AssertionError(f'TCP service {host}:{port} was not ready in time')


def _assert_forwarded_camera_packet(
    test_case: unittest.TestCase,
    forwarded_data: bytes,
    forwarded_addr: tuple[str, int],
) -> None:
    test_case.assertEqual(forwarded_addr[0], '127.0.0.1')
    test_case.assertGreaterEqual(len(forwarded_data), 23)
    test_case.assertEqual(forwarded_data[0], 0x0F)
    test_case.assertEqual(forwarded_data[1], 0xF0)
    test_case.assertEqual(forwarded_data[2], 0x02)
    test_case.assertEqual(forwarded_data[3], 0x01)
    test_case.assertEqual(forwarded_data[4], 0x01)
    test_case.assertEqual(forwarded_data[5], 5)
    test_case.assertEqual(forwarded_data[-2], 0xF0)
    test_case.assertEqual(forwarded_data[-1], 0x0F)


def _wait_for_log_contains(expected_text: str, timeout: float = 5.0) -> str:
    deadline = time.time() + timeout
    last_log_text = ''
    while time.time() < deadline:
        if MAIN_LOG_PATH.exists():
            last_log_text = MAIN_LOG_PATH.read_text(encoding='utf-8')
            if expected_text in last_log_text:
                return last_log_text
        time.sleep(0.1)
    raise AssertionError(
        f'Expected log text not found within {timeout} seconds: {expected_text}\n'
        f'Current log tail:\n{last_log_text[-2000:]}'
    )


class _CammonMixin:
    @classmethod
    def setUpClass(cls) -> None:
        cls.cammon = ctypes.CDLL(str(CAMMON_LIB_PATH))
        cls.cammon.cammon_send_camera_command.argtypes = [
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_int,
            ctypes.c_int,
        ]
        cls.cammon.cammon_send_camera_command.restype = ctypes.c_int

    def _send_camera_command(self, host: bytes, port: int) -> int:
        payload = (ctypes.c_uint8 * 1)(5)
        response_buffer = (ctypes.c_uint8 * 1024)()
        return self.cammon.cammon_send_camera_command(
            host,
            port,
            0x01,
            0x01,
            payload,
            1,
            response_buffer,
            len(response_buffer),
            200,
        )

@unittest.skipUnless(CAMMON_LIB_PATH.exists(), f'cammon library not found: {CAMMON_LIB_PATH}')
@unittest.skipIf(USE_RUNNING_MAIN, 'standalone listener test disabled when targeting running main.py')
class CamWindUdpListenerTest(_CammonMixin, unittest.TestCase):

    def setUp(self) -> None:
        self.listen_port = _find_free_udp_port()
        self.forward_port = _find_free_udp_port()
        self.received_packets: queue.Queue[tuple[bytes, tuple[str, int]]] = queue.Queue()
        self.stop_event = threading.Event()

        self.receiver_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.receiver_socket.settimeout(0.2)
        self.receiver_socket.bind(('127.0.0.1', self.forward_port))

        self.receiver_thread = threading.Thread(target=self._recv_forwarded_packet, daemon=True)
        self.receiver_thread.start()

        self.listener = UDPUdpListener(listen_port=self.listen_port)
        self.listener._lookup_udp_port = lambda cam_ip: self.forward_port
        self.listener.start()
        self._wait_for_listener_ready()

    def tearDown(self) -> None:
        self.listener.stop()
        self.stop_event.set()
        self.receiver_socket.close()
        self.receiver_thread.join(timeout=1)

    def _wait_for_listener_ready(self) -> None:
        deadline = time.time() + 2
        while time.time() < deadline:
            if self.listener.server_socket is not None:
                return
            time.sleep(0.05)
        self.fail('UDP listener did not start in time')

    def _recv_forwarded_packet(self) -> None:
        while not self.stop_event.is_set():
            try:
                data, addr = self.receiver_socket.recvfrom(4096)
                self.received_packets.put((data, addr))
                return
            except socket.timeout:
                continue
            except OSError:
                return

    def test_cam_wind_library_can_send_datagram_to_udp_listener(self) -> None:
        self._send_camera_command(b'127.0.0.1', self.listen_port)

        forwarded_data, forwarded_addr = self.received_packets.get(timeout=2)
        _assert_forwarded_camera_packet(self, forwarded_data, forwarded_addr)


@unittest.skipUnless(CAMMON_LIB_PATH.exists(), f'cammon library not found: {CAMMON_LIB_PATH}')
@unittest.skipUnless(
    USE_RUNNING_MAIN or SPAWN_MAIN,
    'set TEST_USE_RUNNING_MAIN=1 or TEST_SPAWN_MAIN=1 to target main.py service',
)
class MainServiceUdpListenerIntegrationTest(_CammonMixin, unittest.TestCase):
    main_process: subprocess.Popen[str] | None = None
    main_log_handle = None
    active_main_udp_port = MAIN_UDP_PORT
    active_main_http_port = MAIN_HTTP_PORT

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        if SPAWN_MAIN:
            cls.active_main_http_port = _find_free_tcp_port()
            cls.active_main_udp_port = _find_free_udp_port()
            cls.main_log_handle = open(MAIN_LOG_PATH, 'w', encoding='utf-8', buffering=1)
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            env['WEBAPI_PORT'] = str(cls.active_main_http_port)
            env['UDP_LISTEN_PORT'] = str(cls.active_main_udp_port)
            cls.main_process = subprocess.Popen(
                [sys.executable, 'main.py'],
                cwd=str(REPO_ROOT),
                stdout=cls.main_log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
            )
        else:
            cls.active_main_http_port = MAIN_HTTP_PORT
            cls.active_main_udp_port = MAIN_UDP_PORT
        try:
            _wait_for_tcp_port('127.0.0.1', cls.active_main_http_port)
        except AssertionError as exc:
            process = cls.main_process
            if process is not None and process.poll() is not None:
                if cls.main_log_handle is not None:
                    cls.main_log_handle.flush()
                log_excerpt = ''
                if MAIN_LOG_PATH.exists():
                    log_excerpt = MAIN_LOG_PATH.read_text(encoding='utf-8')[-2000:]
                raise AssertionError(
                    f'{exc}; main.py exited with code {process.returncode}. Log tail:\n{log_excerpt}'
                ) from exc
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        process = cls.main_process
        try:
            if process is not None:
                process.terminate()
                process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            if process is not None:
                process.kill()
                process.wait(timeout=5)
        finally:
            cls.main_process = None
            if cls.main_log_handle is not None:
                cls.main_log_handle.close()
                cls.main_log_handle = None

    def setUp(self) -> None:
        self.forward_port = _find_free_udp_port()
        self.received_packets: queue.Queue[tuple[bytes, tuple[str, int]]] = queue.Queue()
        self.stop_event = threading.Event()
        self.task_id = f'udp-test-{uuid.uuid4()}'

        self.receiver_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.receiver_socket.settimeout(0.2)
        self.receiver_socket.bind(('127.0.0.1', self.forward_port))

        self.receiver_thread = threading.Thread(target=self._recv_forwarded_packet, daemon=True)
        self.receiver_thread.start()

        self._insert_udp_mapping()
        _wait_for_tcp_port('127.0.0.1', self.active_main_http_port)

    def tearDown(self) -> None:
        self._delete_udp_mapping()
        self.stop_event.set()
        self.receiver_socket.close()
        self.receiver_thread.join(timeout=1)

    def _recv_forwarded_packet(self) -> None:
        while not self.stop_event.is_set():
            try:
                data, addr = self.receiver_socket.recvfrom(4096)
                if data:
                    self.received_packets.put((data, addr))
                    return
            except socket.timeout:
                continue
            except OSError:
                return

    def _insert_udp_mapping(self) -> None:
        connection = sqlite3.connect(TASK_DB_PATH)
        try:
            connection.execute(
                'INSERT INTO tasktable (id, taskname, cam1_ip, udp_port, cam1_id, cam2_id) VALUES (?, ?, ?, ?, ?, ?)',
                (self.task_id, self.task_id, '127.0.0.1', self.forward_port, self.task_id, self.task_id),
            )
            connection.commit()
        finally:
            connection.close()

    def _delete_udp_mapping(self) -> None:
        connection = sqlite3.connect(TASK_DB_PATH)
        try:
            connection.execute('DELETE FROM tasktable WHERE id = ?', (self.task_id,))
            connection.commit()
        finally:
            connection.close()

    def test_running_main_service_receives_and_forwards_udp_datagram(self) -> None:
        self._send_camera_command(b'127.0.0.1', self.active_main_udp_port)

        forwarded_data, forwarded_addr = self.received_packets.get(timeout=3)
        _assert_forwarded_camera_packet(self, forwarded_data, forwarded_addr)

        if SPAWN_MAIN:
            expected_raw = f'raw={forwarded_data!r}'
            expected_hex = f'hex={forwarded_data.hex(" ")}'
            log_text = _wait_for_log_contains('Received UDP packet from 127.0.0.1:')
            self.assertIn(expected_raw, log_text)
            self.assertIn(expected_hex, log_text)


if __name__ == '__main__':
    unittest.main()