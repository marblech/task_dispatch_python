#!/usr/bin/env python3
import argparse
import re
import shlex
import sys
import time

# Delay import of `docker` until we actually need to connect so that
# `-h` / argument parsing works even if the SDK isn't installed.

DOCKER_SOCKET = "unix://var/run/docker.sock"
DEFAULT_DOCKER_RUN_VOLUMES = {
    '/usr/local/Ascend/driver': {'bind': '/usr/local/Ascend/driver', 'mode': 'ro'},
    '/etc/ascend_install.info': {'bind': '/etc/ascend_install.info', 'mode': 'rw'},
    '/var/driver/version.info': {'bind': '/var/driver/version.info', 'mode': 'rw'},
}


def _normalize_volumes(volumes: list | dict | None) -> dict | None:
    if not volumes:
        return None

    if isinstance(volumes, dict):
        return dict(volumes)

    volume_map = {}
    for volume in volumes:
        if ":" not in volume:
            print(f"Ignoring invalid volume mapping: {volume}")
            continue
        host_path, container_path = volume.split(":", 1)
        volume_map[host_path] = {'bind': container_path, 'mode': 'rw'}

    return volume_map or None


def _merge_volume_map(volumes: list | dict | None) -> dict:
    merged = dict(DEFAULT_DOCKER_RUN_VOLUMES)
    extra_volumes = _normalize_volumes(volumes)
    if extra_volumes:
        merged.update(extra_volumes)
    return merged


def _cmd_to_tokens(cmd_value) -> list[str]:
    if cmd_value is None:
        return []
    if isinstance(cmd_value, (list, tuple)):
        return [str(item) for item in cmd_value if item is not None]
    try:
        return shlex.split(str(cmd_value))
    except Exception:
        return [str(cmd_value)]


def _extract_primary_executable(cmd_value) -> str:
    tokens = _cmd_to_tokens(cmd_value)
    if not tokens:
        return ''

    if len(tokens) >= 3 and tokens[0] in {'sh', '/bin/sh', 'bash', '/bin/bash'} and tokens[1] == '-c':
        shell_tokens = _cmd_to_tokens(tokens[2])
        if shell_tokens:
            tokens = shell_tokens

    for separator in ('&&', ';', '||'):
        if separator in tokens:
            tokens = tokens[tokens.index(separator) + 1:]

    while tokens and tokens[0] in {'exec'}:
        tokens = tokens[1:]

    for token in tokens:
        if token in {'>', '>>', '1>', '1>>', '2>', '2>>', '2>&1'}:
            break
        if token.startswith('-'):
            continue
        return token

    return ''


def _container_matches_request(container, image: str | None, cmd) -> bool:
    try:
        cfg = getattr(container, 'attrs', {}).get('Config', {})
    except Exception:
        cfg = {}

    existing_image = cfg.get('Image') or ''
    existing_tags = []
    try:
        existing_tags = getattr(getattr(container, 'image', None), 'tags', []) or []
    except Exception:
        existing_tags = []

    image_match = False
    if image:
        image_match = existing_image == image or image in existing_tags

    existing_cmd = cfg.get('Cmd') or cfg.get('Entrypoint')
    existing_cmd_tokens = _cmd_to_tokens(existing_cmd)
    requested_cmd_tokens = _cmd_to_tokens(cmd)

    if not requested_cmd_tokens:
        cmd_match = not existing_cmd_tokens
    elif existing_cmd_tokens == requested_cmd_tokens:
        cmd_match = True
    else:
        existing_exec = _extract_primary_executable(existing_cmd)
        requested_exec = _extract_primary_executable(cmd)
        cmd_match = bool(existing_exec) and existing_exec == requested_exec

    return image_match and cmd_match


def _stop_and_remove_if_matching(client, container_ref: str, image: str | None, cmd) -> bool:
    try:
        container = client.containers.get(container_ref)
    except Exception:
        return False

    if not _container_matches_request(container, image, cmd):
        return False

    print(f"Stopping and removing existing container: name={container.name}, id={container.id}")
    try:
        container.stop(timeout=5)
    except Exception:
        pass
    try:
        container.remove(force=True)
    except Exception:
        pass

    for _ in range(10):
        try:
            client.containers.get(container.id)
        except Exception:
            return True
        time.sleep(0.3)

    return False


def _tail_container_logs(container, tail: int = 80) -> str:
    try:
        logs = container.logs(tail=tail)
    except Exception:
        return ''

    if isinstance(logs, (bytes, bytearray)):
        return logs.decode('utf-8', errors='replace').strip()
    return str(logs).strip()


def _verify_detached_container(container, startup_timeout: float):
    deadline = time.time() + max(float(startup_timeout or 0), 0)

    while True:
        try:
            container.reload()
        except Exception as exc:
            raise RuntimeError(f'container disappeared before startup verification completed: {exc}') from exc

        state = getattr(container, 'attrs', {}).get('State', {}) or {}
        status = state.get('Status') or getattr(container, 'status', None)

        if state.get('Running'):
            return container

        if status in {'exited', 'dead'}:
            exit_code = state.get('ExitCode')
            logs = _tail_container_logs(container)
            message = f'container exited immediately (status={status}, exit_code={exit_code})'
            if logs:
                message = f'{message}\ncontainer logs:\n{logs}'
            raise RuntimeError(message)

        if time.time() >= deadline:
            return container

        time.sleep(0.5)

def get_client():
    try:
        import docker
    except Exception:
        print("Missing dependency: docker SDK is required. Run: pip install docker", file=sys.stderr)
        raise

    try:
        return docker.DockerClient(base_url=DOCKER_SOCKET)
    except Exception as e:
        print(f"Failed to connect to Docker socket ({DOCKER_SOCKET}): {e}")
        raise


def pull_image_with_progress(client, image: str):
    """Pull an image and stream progress to stdout so the user sees what's happening."""
    try:
        api = client.api
        # If image exists locally, skip pulling to avoid unnecessary network IO.
        try:
            local = client.images.list(name=image)
            if local:
                print(f"Image '{image}' found locally; skipping pull.")
                return
        except Exception:
            # If checking fails, fall back to attempting to pull and surface errors.
            pass

        print(f"Pulling image '{image}' (streaming progress) ...")
        for line in api.pull(image, stream=True, decode=True):
            # each line is a dict with possible keys: status, progress, id, error
            if not isinstance(line, dict):
                print(line)
                continue
            if 'error' in line:
                print(f"ERROR: {line.get('error')}")
                continue
            status = line.get('status')
            prog = line.get('progress') or line.get('progressDetail')
            ident = line.get('id')
            if ident:
                print(f"{ident}: {status} {prog if prog else ''}")
            else:
                print(f"{status} {prog if prog else ''}")
    except Exception as e:
        print(f"Image pull error: {e}")
        raise

def create_container(image: str, name: str | None, cmd: str, detach: bool = True):
    client = get_client()
    pull_image_with_progress(client, image)
    print("Creating container...")
    container = client.containers.create(image=image, command=cmd, name=name, detach=detach)
    container.start()
    print(f"Started container: id={container.id}, name={container.name}")
    return container

def docker_run(image: str, cmd: str | list[str] | None = None, name: str | None = None,
                             detach: bool = False, remove: bool = False,
                             ports: list | None = None, volumes: list | dict | None = None,
                             envs: list | None = None, tty: bool = True, interactive: bool = True,
                             privileged: bool = True, verify_running: bool = False,
                             startup_timeout: float = 0):
    """Run a container similar to `docker run` using docker SDK.

        Compose-style defaults applied here:
        - default bind mounts for Ascend runtime related host paths
        - `privileged=True`
        - `tty=True`
        - `stdin_open=True`

        Explicitly not applied as defaults here:
        - restart policy (`unless-stopped`)
        - port mappings
        - working directory
        - command

        - `ports` is a list of strings like '8000:80' (host:container)
        - `volumes` is either a list of strings like '/host/path:/container/path' or
            a dict mapping host paths to bind options like `{'/host/path': {'bind': '/container/path', 'mode': 'rw'}}`.
    - `envs` is a list of strings like 'KEY=VALUE'
    """
    client = get_client()
    pull_image_with_progress(client, image)

    port_map = None
    if ports:
        port_map = {}
        for p in ports:
            if ":" not in p:
                print(f"Ignoring invalid port mapping: {p}")
                continue
            host, container = p.split(":", 1)
            # normalize container port with tcp
            key = f"{container}/tcp"
            try:
                port_map[key] = int(host)
            except ValueError:
                port_map[key] = host

    volume_map = _merge_volume_map(volumes)

    env_map = None
    if envs:
        env_map = {}
        for e in envs:
            if "=" not in e:
                print(f"Ignoring invalid env var: {e}")
                continue
            k, val = e.split("=", 1)
            env_map[k] = val

    # If a name is provided and a container with that name already exists,
    # check if it matches the requested image and command. If it does, stop
    # and remove it so we can reuse the name. This avoids the 409 Conflict
    # when reusing container names for identical tasks.
    if name:
        _stop_and_remove_if_matching(client, name, image, cmd)

    try:
        print("Creating and starting container...")
        container = client.containers.run(
            image,
            command=cmd,
            name=name,
            detach=detach,
            remove=remove,
            ports=port_map,
            volumes=volume_map,
            environment=env_map,
            tty=tty,
            stdin_open=interactive,
            privileged=privileged,
        )
        if detach:
            if verify_running:
                _verify_detached_container(container, startup_timeout=startup_timeout)
            print(f"Started container (detached): id={getattr(container, 'id', None)}, name={getattr(container, 'name', None)}")
            return container
        else:
            # when not detached, `container` is a bytes stream; print it
            print(container.decode() if isinstance(container, (bytes, bytearray)) else container)
            return None
    except Exception as e:
        conflict_id = None
        try:
            match = re.search(r'already in use by container "([0-9a-f]{12,64})"', str(e))
            if match:
                conflict_id = match.group(1)
        except Exception:
            conflict_id = None

        if conflict_id and _stop_and_remove_if_matching(client, conflict_id, image, cmd):
            print("Retrying container creation after removing conflicting container...")
            container = client.containers.run(
                image,
                command=cmd,
                name=name,
                detach=detach,
                remove=remove,
                ports=port_map,
                volumes=volume_map,
                environment=env_map,
                tty=tty,
                stdin_open=interactive,
                privileged=privileged,
            )
            if detach:
                if verify_running:
                    _verify_detached_container(container, startup_timeout=startup_timeout)
                print(f"Started container (detached): id={getattr(container, 'id', None)}, name={getattr(container, 'name', None)}")
                return container
            print(container.decode() if isinstance(container, (bytes, bytearray)) else container)
            return None

        print(f"Failed to run container: {e}")
        raise

def list_containers(all_containers: bool = False):
    client = get_client()
    containers = client.containers.list(all=all_containers)
    if not containers:
        print("(no containers)")
        return
    for c in containers:
        print(f"{c.id[:12]}  {c.name}  status={c.status}  image={c.image.tags}")

def stop_container(name_or_id: str, timeout: int = 10, remove: bool = False):
    client = get_client()
    try:
        c = client.containers.get(name_or_id)
    except Exception:
        print(f"Container '{name_or_id}' not found")
        return
    container_id = getattr(c, 'id', '') or ''
    print(f"Stopping container {c.name} ({container_id[:12]}) ...")
    c.stop(timeout=timeout)
    print("Stopped")
    if remove:
        print("Removing container...")
        c.remove()
        print("Removed")

def parse_args():
    p = argparse.ArgumentParser(description="Demo: control Docker from inside a container via Docker socket")
    sub = p.add_subparsers(dest="subcmd")

    p_list = sub.add_parser("list", help="List containers")
    p_list.add_argument("--all", action="store_true", help="List all containers")

    p_create = sub.add_parser("create", help="Create and start a container")
    p_create.add_argument("--image", default="alpine", help="Image to use (default: alpine)")
    p_create.add_argument("--name", default=None, help="Optional container name")
    p_create.add_argument("--cmd", default="sleep 3600", help="Command to run inside the container")

    p_stop = sub.add_parser("stop", help="Stop a container")
    p_stop.add_argument("name_or_id", help="Container name or id")
    p_stop.add_argument("--timeout", type=int, default=10)
    p_stop.add_argument("--rm", action="store_true", help="Remove after stopping")

    p_run = sub.add_parser("run", help="Run a container (docker run-like)")
    p_run.add_argument("--image", default="alpine", help="Image to use (default: alpine)")
    p_run.add_argument("--name", default=None, help="Optional container name")
    p_run.add_argument("--cmd", default=None, help="Command to run inside the container")
    p_run.add_argument("-d", "--detach", action="store_true", help="Run container in background (detached)")
    p_run.add_argument("--rm", dest="rm", action="store_true", help="Remove container after exit")
    p_run.add_argument("-p", "--publish", action="append", help="Publish a container's port(s) to the host (format: hostPort:containerPort). Can be repeated.")
    p_run.add_argument("-v", "--volume", action="append", help="Bind mount a volume (format: host_path:container_path). Can be repeated.")
    p_run.add_argument("-e", "--env", action="append", help="Set environment variables (format: KEY=VALUE). Can be repeated.")
    p_run.add_argument("-t", "--tty", action="store_true", help="Allocate a pseudo-TTY")
    p_run.add_argument("-i", "--interactive", action="store_true", help="Keep STDIN open even if not attached")

    return p.parse_args()

def main():
    args = parse_args()
    if args.subcmd == "list":
        list_containers(all_containers=args.all)
    elif args.subcmd == "create":
        create_container(image=args.image, name=args.name, cmd=args.cmd)
    elif args.subcmd == "stop":
        stop_container(args.name_or_id, timeout=args.timeout, remove=args.rm)
    elif args.subcmd == "run":
        docker_run(image=args.image, cmd=args.cmd, name=args.name,
                   detach=args.detach, remove=getattr(args, 'rm', False),
                   ports=getattr(args, 'publish', None), volumes=getattr(args, 'volume', None),
                   envs=getattr(args, 'env', None), tty=args.tty, interactive=args.interactive)
    else:
        print("No command specified. Run with -h for help.")

