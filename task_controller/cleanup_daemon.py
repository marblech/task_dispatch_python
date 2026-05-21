from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Iterable, Set

from db import dbconn
from ini_file_controller.ini_file_helper import IniFileHelper
from models.process import TaskConfig
from task_controller.task_starter import TASK_CONTAINER_IMAGE, is_managed_temp_model_file


EXCLUDED_CONTAINER_NAMES = {'task_condition_docker'}


def _get_active_task_container_ids() -> Set[str]:
    db = dbconn.DBConn()
    session = db.get_session()
    try:
        tasks = session.query(TaskConfig).all()
        return {str(task.pid).strip() for task in tasks if task.pid}
    finally:
        session.close()


def _is_target_task_container(container) -> bool:
    try:
        name = (getattr(container, 'name', '') or '').strip()
        if name in EXCLUDED_CONTAINER_NAMES:
            return False

        image = getattr(container, 'image', None)
        image_tags = getattr(image, 'tags', []) or []
        if TARGET_CONTAINER_IMAGE in image_tags:
            return True

        config = getattr(container, 'attrs', {}).get('Config', {})
        return config.get('Image') == TARGET_CONTAINER_IMAGE
    except Exception:
        return False


def _cleanup_orphan_containers_once() -> int:
    """Stop unmanaged task containers.

    Cleanup rules:
    - only process containers created from `TASK_CONTAINER_IMAGE`
    - skip reserved container names like `task_condition_docker`
    - stop/remove containers whose id is not present in `TaskConfig.pid`
    """
    try:
        from task_controller import docker_helper
    except Exception:
        return 0

    try:
        client = docker_helper.get_client()
        containers = client.containers.list(all=True)
    except Exception:
        return 0

    active_container_ids = _get_active_task_container_ids()
    stopped = 0

    for container in containers:
        try:
            container_id = (getattr(container, 'id', None) or '').strip()
            if not container_id:
                continue
            if not _is_target_task_container(container):
                continue
            if container_id in active_container_ids:
                continue

            docker_helper.stop_container(container_id, timeout=5, remove=True)
            stopped += 1
        except Exception:
            continue

    return stopped


DEFAULT_SCAN_DIRS = (
    Path('/data/video_ar_app'),
    Path('/data/video_ar_app/models'),
)

_cleanup_thread: threading.Thread | None = None
_cleanup_lock = threading.Lock()


def _normalize_path(value: str | None) -> Path | None:
    if not value:
        return None
    try:
        return Path(value).expanduser().resolve(strict=False)
    except Exception:
        return Path(value)


def _matches_task_file(file_path: Path, task: TaskConfig) -> bool:
    candidates = (
        task.ini_file,
        task.yolo_file,
        task.resnet_file,
    )
    normalized = file_path.resolve(strict=False)
    for raw in candidates:
        candidate = _normalize_path(raw)
        if candidate is not None and candidate == normalized:
            return True
    return False


def _collect_known_paths(tasks: Iterable[TaskConfig]) -> Set[Path]:
    known: Set[Path] = set()
    for task in tasks:
        for raw_path in (task.ini_file, task.yolo_file, task.resnet_file):
            p = _normalize_path(raw_path)
            if p is not None:
                known.add(p)
    return known


def _scan_and_cleanup_once(scan_dirs: Iterable[Path]) -> int:
    db = dbconn.DBConn()
    session = db.get_session()
    try:
        tasks = session.query(TaskConfig).all()
        known_paths = _collect_known_paths(tasks)
    finally:
        session.close()

    deleted = 0
    for base_dir in scan_dirs:
        if not base_dir.exists() or not base_dir.is_dir():
            continue
        for root, _, files in os.walk(base_dir):
            root_path = Path(root)
            for filename in files:
                file_path = (root_path / filename).resolve(strict=False)
                if file_path in known_paths:
                    continue
                suffix = file_path.suffix.lower()
                if suffix == '.ini':
                    pass
                elif suffix == '.om':
                    if not is_managed_temp_model_file(file_path):
                        continue
                elif suffix == '.onnx':
                    continue
                else:
                    continue
                try:
                    IniFileHelper.delete_file(file_path, ignore_mission=True)
                    deleted += 1
                except IsADirectoryError:
                    continue
                except Exception:
                    continue
    return deleted


def _cleanup_loop(interval_seconds: int, scan_dirs: tuple[Path, ...]):
    while True:
        try:
            _scan_and_cleanup_once(scan_dirs)
            try:
                _cleanup_orphan_containers_once()
            except Exception:
                pass
        except Exception:
            pass
        time.sleep(interval_seconds)


def start_cleanup_daemon(interval_seconds: int = 60, scan_dirs: Iterable[Path] = DEFAULT_SCAN_DIRS):
    global _cleanup_thread
    with _cleanup_lock:
        if _cleanup_thread and _cleanup_thread.is_alive():
            return _cleanup_thread
        scan_dirs_tuple = tuple(Path(p) for p in scan_dirs)
        _cleanup_thread = threading.Thread(
            target=_cleanup_loop,
            args=(interval_seconds, scan_dirs_tuple),
            daemon=True,
            name='task-cleanup-daemon',
        )
        _cleanup_thread.start()
        return _cleanup_thread
