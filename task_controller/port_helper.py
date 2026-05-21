import os
import socket
import struct
from functools import lru_cache
from typing import Optional


def get_docker_published_host_ports() -> set[int]:
    """
    Return host ports currently published by running Docker containers.

    This catches ports reserved by Docker port mappings even when a plain TCP
    connect probe would still report the port as unavailable/closed.
    """
    try:
        from task_controller import docker_helper

        client = docker_helper.get_client()
        used_ports: set[int] = set()
        for container in client.containers.list():
            try:
                ports = container.attrs.get('NetworkSettings', {}).get('Ports', {}) or {}
            except Exception:
                ports = {}

            for bindings in ports.values():
                if not bindings:
                    continue
                for binding in bindings:
                    host_port = binding.get('HostPort')
                    if not host_port:
                        continue
                    try:
                        used_ports.add(int(host_port))
                    except (TypeError, ValueError):
                        continue

        return used_ports
    except Exception:
        return set()


def _can_bind_local_port(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(('0.0.0.0', int(port)))
        except OSError:
            return False
    return True


@lru_cache(maxsize=1)
def _running_in_container() -> bool:
    if os.path.exists('/.dockerenv'):
        return True

    try:
        with open('/proc/1/cgroup', 'r', encoding='utf-8', errors='ignore') as handle:
            content = handle.read()
    except Exception:
        return False

    markers = ('docker', 'containerd', 'kubepods', 'cri-containerd')
    return any(marker in content for marker in markers)


@lru_cache(maxsize=1)
def _get_host_gateway() -> str:
    """
    Try to get the host gateway IP in a container.
    Priority:
      1) HOST_GATEWAY env
      2) host.docker.internal (if resolvable)
      3) default Linux gateway 172.17.0.1
    """
    env = os.getenv("HOST_GATEWAY")
    if env:
        return env

    try:
        socket.gethostbyname("host.docker.internal")
        return "host.docker.internal"
    except socket.gaierror:
        # Try to parse the container's default gateway from /proc/net/route
        try:
            with open('/proc/net/route', 'r') as f:
                for line in f.readlines()[1:]:
                    parts = line.strip().split()
                    if len(parts) >= 3:
                        iface, dest, gateway = parts[0], parts[1], parts[2]
                        if dest == '00000000':
                            # gateway is in hex little-endian
                            try:
                                gw = struct.pack("<L", int(gateway, 16))
                                gw_ip = socket.inet_ntoa(gw)
                                return gw_ip
                            except Exception:
                                continue
        except Exception:
            pass

        # Fallback to common default docker bridge address
        return "172.17.0.1"


def is_host_port_available(
    port: int,
    timeout: float = 0.15,
    host: Optional[str] = None,
    docker_reserved_ports: Optional[set[int]] = None,
) -> bool:
    """
    Check if a host port is available from within a container.

    Returns True if the port is NOT in use on the host (connection refused/timeout),
    False if the port is open (connection succeeds).

    :param port: Port number on the host to check.
    :param timeout: Socket connection timeout in seconds.
    :param host: Optional host/IP to check; defaults to inferred host gateway.
    :param docker_reserved_ports: Optional pre-fetched set of Docker published
        host ports to avoid re-querying Docker for every probe.
    """
    reserved_ports = docker_reserved_ports
    if reserved_ports is None:
        reserved_ports = get_docker_published_host_ports()

    if int(port) in reserved_ports:
        return False

    if not _running_in_container():
        return _can_bind_local_port(port)

    target = host or _get_host_gateway()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        result = sock.connect_ex((target, int(port)))
        # connect_ex returns 0 when connection succeeds (port in use)
        return result != 0