import subprocess
import threading
import time
import shlex
import os
import shutil
from typing import Optional

try:
    import psutil
except ModuleNotFoundError:
    raise ModuleNotFoundError(
        "缺少依赖包 psutil。请运行：\n"
        "  python3 -m pip install psutil -i https://pypi.tuna.tsinghua.edu.cn/simple\n"
        "或在 Debian/Ubuntu 上：\n"
        "  sudo apt-get install -y python3-psutil"
    )
class ProcessManager:
    def __init__(self):
        # pid -> {'name': str, 'popen': Popen, 'cmd': str, 'start_time': float}
        self._procs = {}
        self._lock = threading.Lock()
        self._log_dir = "./logs"
        os.makedirs(self._log_dir, exist_ok=True)

    def start_process(self, name, cmd, *, log_to_file: bool = False,
                      log_file: Optional[str] = None,
                      log_dir: Optional[str] = None,
                      merge_stderr: bool = True,
                      force_line_buffer: bool = True):
        """
        启动外部进程。

        参数:
        - name: 业务名称，用于分组/检索
        - cmd: 启动命令，str 或 list
        - log_to_file: 是否将 stdout/stderr 写入日志文件
        - log_file: 指定日志文件路径；未指定则自动生成到 log_dir
        - log_dir: 日志目录，未指定使用初始化时的默认目录
        - merge_stderr: 是否将 stderr 合并到同一文件
        - force_line_buffer: 当重定向到文件时，使用 stdbuf 将 stdout/stderr 设为行缓冲，
                              以解决 C/C++ 程序在非 TTY 下全缓冲导致日志长时间不落盘的问题。
        """
        if isinstance(cmd, str):
            args = shlex.split(cmd)
        else:
            args = cmd

        # 在 Linux 下，很多 C/C++ 程序（std::cout/printf）在非 TTY（文件/管道）时会启用全缓冲，
        # 导致日志长时间不写入文件。使用 coreutils 的 stdbuf 包装为行缓冲，提升“实时性”。
        if force_line_buffer and args and os.name == 'posix':
            stdbuf_path = shutil.which("stdbuf")
            if stdbuf_path and os.path.basename(args[0]) != 'stdbuf':
                # 使用不带缓冲（-o0 -e0），即使没有换行也能尽快写入文件
                args = [stdbuf_path, '-o0', '-e0', *args]
            elif shutil.which("script") and os.path.basename(args[0]) != 'script':
                # 备用方案：使用 script 分配伪终端，强制程序认为连接的是 TTY，从而关闭全缓冲
                # 注意：script 需要把命令作为字符串传入 -c
                try:
                    cmd_str = shlex.join(args)
                except Exception:
                    cmd_str = " ".join(shlex.quote(a) for a in args)
                args = ["script", "-q", "-c", cmd_str, "/dev/null"]

        stdout_fp = None
        stderr_fp = None
        popen_kwargs = {}

        if log_to_file or log_file or log_dir:
            base_dir = log_dir or self._log_dir
            os.makedirs(base_dir, exist_ok=True)
            if not log_file:
                ts = time.strftime("%Y%m%d-%H%M%S")
                safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(name))[:50]
                log_file = os.path.join(base_dir, f"{safe_name}-{ts}.log")
            stdout_fp = open(log_file, "ab")
            popen_kwargs["stdout"] = stdout_fp
            if merge_stderr:
                popen_kwargs["stderr"] = stdout_fp
            else:
                err_file = os.path.splitext(log_file)[0] + ".err.log"
                stderr_fp = open(err_file, "ab")
                popen_kwargs["stderr"] = stderr_fp

        try:
            popen = subprocess.Popen(args, **popen_kwargs)  # shell=False 默认
        except Exception:
            # 启动失败时关闭已打开的文件句柄
            try:
                if stdout_fp: stdout_fp.close()
                if stderr_fp: stderr_fp.close()
            finally:
                raise

        with self._lock:
            info = {
                'name': name,
                'popen': popen,
                'cmd': cmd,
                'start_time': time.time()
            }
            if stdout_fp:
                info['log_file'] = log_file
                info['log_fp'] = stdout_fp
            if stderr_fp:
                # log_file may be annotated Optional[str]; guard for static checkers
                info['err_log_file'] = os.path.splitext(log_file or "")[0] + ".err.log"
                info['err_fp'] = stderr_fp
            self._procs[popen.pid] = info
        return popen.pid

    def stop_process_by_pid(self, pid: int):
        with self._lock:
            info = self._procs.get(pid)
            if not info:
                raise Exception(f'未找到 pid={pid}')
            popen = info['popen']
        self._terminate(popen)
        # 关闭日志文件句柄
        try:
            for key in ('log_fp', 'err_fp'):
                fp = info.get(key)
                if fp:
                    try: fp.flush()
                    except Exception: pass
                    try: fp.close()
                    except Exception: pass
        except Exception:
            pass
        with self._lock:
            self._procs.pop(pid, None)
        return True

    def stop_processes_by_name(self, name: str):
        with self._lock:
            target = [pid for pid, info in self._procs.items() if info['name'] == name]
            if not target:
                raise Exception(f'没有 name={name} 的进程')
        for pid in target:
            try:
                self.stop_process_by_pid(pid)
            except Exception:
                pass
        return target

    def list_processes(self):
        with self._lock:
            result = []
            for pid, info in self._procs.items():
                popen = info['popen']
                result.append({
                    'pid': pid,
                    'name': info['name'],
                    'cmd': info['cmd'],
                    'running': popen.poll() is None,
                    'start_time': info['start_time'],
                    'log_file': info.get('log_file'),
                    'err_log_file': info.get('err_log_file'),
                })
            return result

    def is_running_pid(self, pid: int) -> bool:
        """优先检查系统进程是否存活，兼容服务重启后内存进程表丢失的场景。"""
        try:
            proc = psutil.Process(int(pid))
            return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
        except (TypeError, ValueError, psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
        with self._lock:
            info = self._procs.get(pid)
            if not info:
                return False
            popen = info['popen']
        return popen.poll() is None

    def any_running_by_name(self, name: str) -> bool:
        """是否存在指定 name 的运行中进程（由本管理器启动）"""
        with self._lock:
            for info in self._procs.values():
                if info['name'] == name and info['popen'].poll() is None:
                    return True
        return False

    def _terminate(self, popen):
        if popen.poll() is None:
            popen.terminate()
            try:
                popen.wait(timeout=5)
            except subprocess.TimeoutExpired:
                popen.kill()