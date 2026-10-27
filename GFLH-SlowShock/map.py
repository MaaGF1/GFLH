import sys
import time
import os
import json
import tempfile
import threading
import subprocess
import webbrowser
import http.server
import socketserver

from gflzirc import GFLProxy, set_windows_proxy, STATIC_KEY

# 打包成 exe 后，资源（gflmaps/、可选的 GFLData/）放在 exe 同目录；
# 开发时就是本文件所在目录。
FROZEN = bool(getattr(sys, "frozen", False))
BASE_DIR = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(os.path.abspath(__file__))

CONFIG = {
    "PROXY_PORT": 8080,
    "LOCAL_WEB_PORT": 8081,
    "OUTPUT_DIR": "traffic_dumps",
    # 默认打开 [活动]慢休克 - 自画像 - 厚涂（任务 11403）；换图改这里的 hash 即可
    "TARGET_URL": "http://127.0.0.1:8081/gflmaps/index.html#campaign=3058&mission=11403"
}

# WebView2 起不来时的兜底：用 Edge/Chrome 的应用窗口打开
BROWSER_CANDIDATES = [
    os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
    os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
    os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
]
PROFILE_DIR = os.path.join(tempfile.gettempdir(), "gflh-slowshock-edge")

proxy_instance = None
browser_process = None
window = None
page_hits = 0

# 抓包统计：给页面上的控制面板判断“到底有没有抓到东西”
packet_stats = {"s2c": 0, "map": 0, "spawn": 0, "death": 0}
packet_stats_lock = threading.Lock()
last_packet_ts = None


# ==============================================================
# 0. Logging (windowed exe has no console)
# ==============================================================
if FROZEN and sys.stdout is None:
    try:
        sys.stdout = open(os.path.join(BASE_DIR, "gflh-slowshock.log"), "a", encoding="utf-8", buffering=1)
        sys.stderr = sys.stdout
    except Exception:
        pass


def log(message):
    try:
        if sys.stdout is not None:
            sys.stdout.write(str(message) + "\n")
            sys.stdout.flush()
    except Exception:
        pass


# ==============================================================
# 1. Local HTTP server: static files + control API + SSE
# ==============================================================
sse_clients = set()
sse_lock = threading.Lock()


class RadarHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        global page_hits
        if self.path.startswith("/gflmaps/") or self.path == "/":
            page_hits += 1
        if self.path.startswith("/api/"):
            return self.handle_api()
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/"):
            return self.handle_api()
        self.send_error(404)

    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_api(self):
        action = self.path.split("?")[0].rstrip("/").split("/")[-1]
        try:
            if action == "status":
                with packet_stats_lock:
                    packets = dict(packet_stats)
                    last_at = last_packet_ts
                return self._send_json({
                    "ok": True,
                    "running": proxy_instance is not None,
                    "port": CONFIG["PROXY_PORT"],
                    "frozen": FROZEN,
                    "packets": packets,
                    "lastPacketAt": last_at,
                    "clients": len(sse_clients),
                })
            if action == "start":
                return self._send_json(start_monitor())
            if action == "stop":
                return self._send_json(stop_monitor())
            if action == "quit":
                threading.Timer(0.3, shutdown).start()
                return self._send_json({"ok": True, "message": "正在退出"})
            if action == "stream":
                return self.serve_event_stream()
            return self._send_json({"ok": False, "message": "unknown api"}, status=404)
        except Exception as exc:
            return self._send_json({"ok": False, "message": str(exc)}, status=500)

    def serve_event_stream(self):
        """SSE：页面订阅后，抓到的包会实时推过去。"""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        self.wfile.write(b": connected\n\n")
        self.wfile.flush()
        with sse_lock:
            sse_clients.add(self.wfile)
        log("[*] Page connected to live stream")
        try:
            while True:
                time.sleep(4)
                self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except Exception:
            pass
        finally:
            with sse_lock:
                sse_clients.discard(self.wfile)
            log("[*] Page disconnected from live stream")


class ThreadingServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def start_local_web_server():
    try:
        with ThreadingServer(("127.0.0.1", CONFIG["LOCAL_WEB_PORT"]), RadarHTTPRequestHandler) as httpd:
            log(f"[*] Web server: http://127.0.0.1:{CONFIG['LOCAL_WEB_PORT']} (root: {BASE_DIR})")
            httpd.serve_forever()
    except Exception as exc:
        log(f"[!] Web server failed: {exc}")


# ==============================================================
# 2. Packet capture
# ==============================================================
def parse_payload(payload):
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except Exception:
            return {"raw_string": payload}
    if isinstance(payload, bytes):
        try:
            return json.loads(payload.decode("utf-8"))
        except Exception:
            return {"raw_hex": payload.hex()}
    return {"raw_type": str(type(payload))}


def push_to_page(handler, payload):
    message = "event: gfl\ndata: " + json.dumps({"handler": handler, "payload": payload}) + "\n\n"
    with sse_lock:
        for stream in list(sse_clients):
            try:
                stream.write(message.encode("utf-8"))
                stream.flush()
            except Exception:
                sse_clients.discard(stream)


def record_packet(has_map, has_spawn, has_death):
    global last_packet_ts
    with packet_stats_lock:
        packet_stats["s2c"] += 1
        if has_map:
            packet_stats["map"] += 1
        if has_spawn:
            packet_stats["spawn"] += 1
        if has_death:
            packet_stats["death"] += 1
        last_packet_ts = time.time()


def reset_packet_stats():
    global last_packet_ts
    with packet_stats_lock:
        for key in packet_stats:
            packet_stats[key] = 0
        last_packet_ts = None


def on_traffic(event_type: str, url: str, data):
    event_upper = str(event_type).upper()

    if event_upper == "SYS_KEY_UPGRADE":
        log("\n[!] SYSTEM UPGRADE: sniffed dynamic user keys.")
        if isinstance(data, dict):
            log(f"    New UID  : {data.get('uid')}")
            log(f"    New SIGN : {data.get('sign')}")
        log("[*] Proxy crypto key has been updated automatically.\n")

    elif event_upper == "C2S":
        log(f"\n[--> C2S] Captured Request: {url}")

    elif event_upper == "S2C":
        json_obj = parse_payload(data)
        handlers = []
        # died_enemy / died_ally 只带阵亡信息，也要触发一次重绘
        has_map = "spot_act_info" in json_obj
        has_spawn = "enemy_instance_info" in json_obj or "ally_instance_info" in json_obj
        has_death = "died_enemy" in json_obj or "died_ally" in json_obj
        if has_map or has_death:
            handlers.append("updateLiveMap")
        if has_spawn:
            handlers.append("updateSpawnLive")
        for handler in handlers:
            push_to_page(handler, json_obj)
        record_packet(has_map, has_spawn, has_death)

    else:
        log(f"\n[?] UNKNOWN event ({event_type}): {url}")


# ==============================================================
# 3. Monitor control
# ==============================================================
def start_monitor():
    global proxy_instance
    if proxy_instance is not None:
        return {"ok": True, "running": True, "message": "监控已经在运行"}
    try:
        proxy_instance = GFLProxy(CONFIG["PROXY_PORT"], STATIC_KEY, on_traffic)
        proxy_instance.start()
        set_windows_proxy(True, f"127.0.0.1:{CONFIG['PROXY_PORT']}")
        reset_packet_stats()
        log(f"[*] Monitor started on {CONFIG['PROXY_PORT']}; system proxy set.")
        return {"ok": True, "running": True, "message": "监控已启动，系统代理已设置"}
    except Exception as exc:
        proxy_instance = None
        log(f"[!] Monitor start failed: {exc}")
        return {"ok": False, "running": False, "message": f"启动失败：{exc}"}


def stop_monitor():
    global proxy_instance
    if proxy_instance is None:
        try:
            set_windows_proxy(False)
        except Exception:
            pass
        return {"ok": True, "running": False, "message": "监控未在运行"}
    try:
        proxy_instance.stop()
    except Exception as exc:
        log(f"[!] Monitor stop failed: {exc}")
    finally:
        proxy_instance = None
        try:
            set_windows_proxy(False)
        except Exception as exc:
            log(f"[!] Restore proxy failed: {exc}")
    log("[*] Monitor stopped.")
    return {"ok": True, "running": False, "message": "监控已停止，系统代理已还原"}


def shutdown(exit_code=0):
    stop_monitor()
    if browser_process is not None:
        try:
            browser_process.terminate()
        except Exception:
            pass
    try:
        if window is not None:
            window.destroy()
    except Exception:
        pass
    os._exit(exit_code)


# ==============================================================
# 4. Window: WebView2 (pywebview) first, browser fallback
# ==============================================================
def on_window_closed():
    log("[*] Window closed. Cleaning up.")
    shutdown()


def run_webview():
    """用 pywebview 的 WebView2 窗口打开页面。失败返回 False。"""
    global window
    try:
        import webview as webview_module
    except Exception as exc:
        log(f"[!] pywebview unavailable: {exc}")
        return False

    try:
        window = webview_module.create_window(
            title="GFL Live Radar - 慢休克",
            url=CONFIG["TARGET_URL"],
            width=1380,
            height=900,
        )
        window.events.closed += on_window_closed
        log("[*] WebView2 window created")
        webview_module.start(gui="edgechromium")
        return True
    except Exception as exc:
        log(f"[!] WebView2 window failed: {exc}")
        window = None
        return False


def child_env():
    env = dict(os.environ)
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        target = os.path.normcase(os.path.abspath(meipass))
        parts = [p for p in env.get("PATH", "").split(os.pathsep) if p and os.path.normcase(os.path.abspath(p)) != target]
        env["PATH"] = os.pathsep.join(parts)
    return env


def wait_for_page(timeout=20.0):
    started = time.time()
    while time.time() - started < timeout:
        if page_hits > 0:
            return True
        time.sleep(0.4)
    return False


def open_app_window():
    """兜底：用 Edge/Chrome 的应用窗口打开地图。"""
    global browser_process
    url = CONFIG["TARGET_URL"]
    try:
        import shutil
        shutil.rmtree(PROFILE_DIR, ignore_errors=True)
    except Exception:
        pass

    for path in BROWSER_CANDIDATES:
        if path and os.path.exists(path):
            try:
                browser_process = subprocess.Popen([
                    path,
                    "--app=" + url,
                    "--window-size=1380,900",
                    "--user-data-dir=" + PROFILE_DIR,
                    "--no-first-run",
                ], env=child_env())
            except Exception as exc:
                log(f"[!] Launch {path} failed: {exc}")
                browser_process = None
                continue

            time.sleep(3)
            if browser_process.poll() is None:
                log(f"[*] Window opened with {os.path.basename(path)}")
                return True
            log(f"[!] {os.path.basename(path)} exited early rc={browser_process.returncode}")
            browser_process = None

    try:
        os.startfile(url)
        log("[*] Opened with default browser (os.startfile)")
    except Exception as exc:
        webbrowser.open(url)
        log(f"[*] Opened with webbrowser.open ({exc})")
    return False


# ==============================================================
# 5. CLI (development only)
# ==============================================================
def print_menu():
    print("\n================= MENU =================")
    print(" -c : Start Network Monitor (MITM)")
    print(" -q : Stop Network Monitor")
    print(" -E : Exit program")
    print("========================================\n")


def cli_loop():
    print_menu()
    time.sleep(0.5)
    while True:
        try:
            cmd = input("GFL-MONITOR> ").strip()
            if not cmd:
                continue
            cmd_prefix = cmd.split()[0]
            if cmd_prefix == "-c":
                print("[*] " + start_monitor()["message"])
            elif cmd_prefix == "-q":
                print("[*] " + stop_monitor()["message"])
            elif cmd_prefix == "-E":
                print("[*] Exiting cleanly...")
                shutdown()
            else:
                print(f"[!] Unknown command: {cmd_prefix}")
                print_menu()
        except KeyboardInterrupt:
            print("\n[!] Use '-E' to exit safely!")


def main():
    # 1. web server
    threading.Thread(target=start_local_web_server, daemon=True).start()
    time.sleep(0.6)

    # 2. dev console
    if not FROZEN:
        threading.Thread(target=cli_loop, daemon=True).start()

    # 3. WebView2 window（打包版和源码都优先用它）
    if run_webview():
        log("[*] Window closed, exiting.")
        shutdown()

    # 4. 兜底：WebView2 起不来时用浏览器窗口，服务保持可用
    log("[!] Falling back to browser window mode")
    open_app_window()
    if not wait_for_page(timeout=8.0):
        log("[!] No page request yet; keep serving, open the URL manually if needed.")
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
