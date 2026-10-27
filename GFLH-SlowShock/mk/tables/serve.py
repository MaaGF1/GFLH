#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tables/ 目录的极简静态服务器。

页面用 fetch 读取 data/*.json，file:// 下会被浏览器拦，所以需要起个本地服务：
    python serve.py            # http://127.0.0.1:8093/
    python serve.py --port 9000
"""

import argparse
import http.server
import os
import socketserver
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=HERE, **kwargs)

    def end_headers(self):
        # 改完页面按 F5 就能看到，不用清缓存
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(description="本地预览表格页面")
    parser.add_argument("--port", type=int, default=8093)
    args = parser.parse_args(argv)

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", args.port), Handler) as httpd:
        print("表格页面: http://127.0.0.1:{}/".format(args.port))
        print("按 Ctrl+C 停止")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n已停止")
    return 0


if __name__ == "__main__":
    sys.exit(main())
