#!/usr/bin/env python3
"""Start a loopback-only iOS controller; close sessions on normal window exit."""
import os
import socket
import threading
import time
import uvicorn
from backend.security import TOKEN


def main():
    # Bind first: never navigate to an unrelated service occupying our port.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('127.0.0.1', int(os.environ.get('FAKEGPS_PORT', '8765'))))
    sock.listen(128)
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config('backend.app:app', host='127.0.0.1', port=port, log_level='info'))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=False)
    thread.start()
    url = f'http://127.0.0.1:{port}/#token={TOKEN}'
    try:
        deadline = time.monotonic() + 15
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError('服务启动失败')
            time.sleep(0.05)
        print(f'本机控制地址（含访问凭据，请勿分享）：{url}', flush=True)
        try:
            import webview
            webview.create_window('iPhone 定位 · iOS 17+', url, width=1180, height=800)
            webview.start()
        except Exception as exc:
            print(f'桌面窗口不可用：{exc}\n请在浏览器打开上面的完整地址，按 Ctrl+C 退出。', flush=True)
            while thread.is_alive():
                time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.should_exit = True
        thread.join(timeout=60)
        sock.close()
        if thread.is_alive():
            print('设备清理仍在等待响应，请检查手机实际定位。', flush=True)


if __name__ == '__main__':
    main()
