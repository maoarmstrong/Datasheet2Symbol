"""Datasheet2Symbol native launcher via pywebview (WebView2).

The FastAPI backend runs in a daemon thread; webview.start() owns the main
thread. Closing the window returns from webview.start(), ending the process
(and the daemon backend) cleanly. This avoids the interaction lockups caused
by running uvicorn on the main thread.
"""
import socket
import sys
import threading
import time
from pathlib import Path

import uvicorn
import webview

from backend.main import app


def icon_path() -> str:
    candidates = [
        Path(__file__).resolve().parent / 'assets' / 'icon.ico',
        Path(sys.executable).parent / 'assets' / 'icon.ico',
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return ''


def find_free_port() -> int:
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


def run_backend(port: int) -> None:
    uvicorn.run(app, host='127.0.0.1', port=port, log_level='warning', access_log=False)


def main() -> None:
    port = find_free_port()
    backend = threading.Thread(target=run_backend, args=(port,), daemon=True)
    backend.start()
    wait_for_server(port)
    webview.create_window(
        'Datasheet2Symbol',
        f'http://127.0.0.1:{port}',
        width=1440,
        height=940,
        min_size=(900, 600),
        confirm_close=True,
    )
    webview.start(icon=icon_path())


if __name__ == '__main__':
    main()
