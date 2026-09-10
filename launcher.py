"""Desktop launcher for Datasheet2Symbol.

The UI runs in Microsoft Edge's app mode: it has no tab strip or address bar,
but uses the production Edge renderer instead of an embedded WebView bridge.
This avoids the interaction lockups observed with pywebview on this machine.
"""
import ctypes
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import uvicorn

from backend.main import app


def find_free_port() -> int:
    """Choose an ephemeral loopback port rather than competing for 8000."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(('127.0.0.1', 0))
        return int(probe.getsockname()[1])


def wait_for_server(port: int, timeout_seconds: float = 10) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.3):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError('本地服务启动超时')


def backend_command(port: int) -> list[str]:
    args = ['--backend', '--port', str(port)]
    if getattr(sys, 'frozen', False):
        return [sys.executable, *args]
    return [sys.executable, str(Path(__file__).resolve()), *args]


def edge_executable() -> str:
    candidates = [
        shutil.which('msedge'),
        str(Path(os.environ.get('ProgramFiles(x86)', r'C:\\Program Files (x86)')) / 'Microsoft' / 'Edge' / 'Application' / 'msedge.exe'),
        str(Path(os.environ.get('ProgramFiles', r'C:\\Program Files')) / 'Microsoft' / 'Edge' / 'Application' / 'msedge.exe'),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise RuntimeError('未找到 Microsoft Edge；请安装或修复 Edge 后重试。')


def notify_error(message: str) -> None:
    ctypes.windll.user32.MessageBoxW(None, message, 'Datasheet2Symbol', 0x10)


def launcher_log_path() -> Path:
    root = Path(sys.executable).parent if getattr(sys, '_MEIPASS', None) else Path.cwd()
    return root / 'datasheet2symbol-launcher.log'


def run_backend(port: int) -> None:
    uvicorn.run(app, host='127.0.0.1', port=port, log_level='warning', access_log=False)


def main() -> None:
    if len(sys.argv) >= 2 and sys.argv[1] == '--backend':
        try:
            port = int(sys.argv[sys.argv.index('--port') + 1])
        except (ValueError, IndexError):
            raise SystemExit('后台服务缺少有效端口')
        run_backend(port)
        return

    port = find_free_port()
    log_file = launcher_log_path().open('a', encoding='utf-8')
    log_file.write(f'\n[{time.strftime("%Y-%m-%d %H:%M:%S")}] starting desktop app on {port}\n')
    log_file.flush()
    backend: subprocess.Popen | None = None
    profile_dir: str | None = None
    try:
        backend = subprocess.Popen(backend_command(port), stdout=log_file, stderr=subprocess.STDOUT)
        wait_for_server(port)
        profile_dir = tempfile.mkdtemp(prefix='datasheet2symbol-edge-')
        browser = subprocess.Popen([
            edge_executable(),
            f'--app=http://127.0.0.1:{port}',
            f'--user-data-dir={profile_dir}',
            '--window-size=1440,940',
            '--no-first-run',
            '--no-default-browser-check',
        ])
        browser.wait()
    except Exception as exc:
        log_file.write(f'{type(exc).__name__}: {exc}\n')
        log_file.flush()
        notify_error(str(exc))
    finally:
        if backend and backend.poll() is None:
            backend.terminate()
            try:
                backend.wait(timeout=5)
            except subprocess.TimeoutExpired:
                backend.kill()
        if profile_dir:
            shutil.rmtree(profile_dir, ignore_errors=True)
        log_file.close()


if __name__ == '__main__':
    main()
