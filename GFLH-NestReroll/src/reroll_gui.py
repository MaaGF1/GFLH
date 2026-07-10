# reroll_gui.py
import sys
import os
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from gflzirc import (
    GFLClient, GFLProxy, set_windows_proxy,
    SERVERS, STATIC_KEY, DEFAULT_SIGN,
    API_MISSION_COMBINFO, API_MISSION_START, API_MISSION_ABORT,
)

# ========== 配置常量 ==========
MISSION_ID = 10508
START_SPOT = 91501
# 1box 目标点位
TARGET_1BOX_SPOTS = [91508, 91517]
TARGET_2BOX_PAIRS = [
    (91508, 91517),
    (91526, 91514),
    (91526, 91509),
    (91542, 91523),
    (91542, 91519),
]
RETRY_DELAY = 0.1  

SERVER_ITEMS = [f"{name} | {url}" for name, url in SERVERS.items()]

# ========== GUI 主类 ==========
class RerollApp:
    def __init__(self, root):
        self.root = root
        self.root.title("GFLH - Hornet's Nest Reroll")
        self.root.geometry("620x550")
        try:
            self.root.iconbitmap("mk/icon.ico")
        except:
            pass

        # 全局状态
        self.proxy_capture = None      # 捕获代理实例
        self.active_proxy = False      # 系统代理是否被本工具开启
        self.stop_flag = False
        self.reroll_thread = None

        self.setup_top_bar()
        self.setup_control_panel()
        self.setup_log_area()

    # ---------- UI 构建 ----------
    def setup_top_bar(self):
        self.frame_top = ttk.LabelFrame(self.root, text="1. 用户配置", padding=10)
        self.frame_top.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(self.frame_top, text=" UID:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.var_uid = tk.StringVar()
        ttk.Entry(self.frame_top, textvariable=self.var_uid, width=30).grid(row=0, column=1, padx=5, pady=2)

        ttk.Label(self.frame_top, text="Sign Key:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.var_sign = tk.StringVar()
        ttk.Entry(self.frame_top, textvariable=self.var_sign, width=30).grid(row=1, column=1, padx=5, pady=2)

        ttk.Label(self.frame_top, text="服务器URL:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.var_server = tk.StringVar()
        cb = ttk.Combobox(self.frame_top, textvariable=self.var_server, values=SERVER_ITEMS, width=45)
        cb.grid(row=2, column=1, padx=5, pady=2)
        cb.current(0)

        self.btn_cap = ttk.Button(self.frame_top, text="自动捕获密钥", command=self.start_capture)
        self.btn_cap.grid(row=0, column=2, padx=5)
        self.btn_stop_cap = ttk.Button(self.frame_top, text="停止捕获", command=self.stop_capture, state=tk.DISABLED)
        self.btn_stop_cap.grid(row=1, column=2, padx=5)

    def setup_control_panel(self):
        self.frame_ctrl = ttk.LabelFrame(self.root, text="2. 重掷设定", padding=10)
        self.frame_ctrl.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(self.frame_ctrl, text="开局模式:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.var_mode = tk.StringVar(value="1box")
        mode_combo = ttk.Combobox(self.frame_ctrl, textvariable=self.var_mode, values=["1box", "2box"], width=10)
        mode_combo.grid(row=0, column=1, sticky=tk.W, padx=5)

        ttk.Label(self.frame_ctrl, text="梯队ID:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.var_team_id = tk.IntVar(value=1)
        team_combo = ttk.Combobox(self.frame_ctrl, textvariable=self.var_team_id, values=list(range(1, 11)), width=5)
        team_combo.grid(row=1, column=1, sticky=tk.W, padx=5)

        btn_frame = ttk.Frame(self.frame_ctrl)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=10)
        self.btn_start = ttk.Button(btn_frame, text="开始重掷", command=self.start_reroll)
        self.btn_start.pack(side=tk.LEFT, padx=5)
        self.btn_stop = ttk.Button(btn_frame, text="停止", command=self.stop_reroll, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=5)

    def setup_log_area(self):
        self.frame_log = ttk.LabelFrame(self.root, text="日志", padding=5)
        self.frame_log.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.txt_log = tk.Text(self.frame_log, height=12, state=tk.DISABLED)
        self.txt_log.pack(fill=tk.BOTH, expand=True)

    def log(self, msg):
        self.root.after(0, self._append_log, msg)

    def _append_log(self, msg):
        self.txt_log.config(state=tk.NORMAL)
        self.txt_log.insert(tk.END, msg + "\n")
        self.txt_log.see(tk.END)
        self.txt_log.config(state=tk.DISABLED)

    # ---------- 代理捕获 ----------
    def on_keys_captured(self, uid, sign):
        self.root.after(0, self.var_uid.set, uid)
        self.root.after(0, self.var_sign.set, sign)
        self.log(f"[CAPTURE] UID: {uid}")

    def start_capture(self):
        if self.proxy_capture:
            self.log("[CAPTURE] Proxy already running.")
            return
        try:
            self.proxy_capture = GFLProxy(8080, STATIC_KEY, self._capture_callback)
            self.proxy_capture.start()
            set_windows_proxy(True, "127.0.0.1:8080")
            self.active_proxy = True
            self.log("[CAPTURE] Proxy started on port 8080, Windows proxy SET.")
            self.btn_cap.config(state=tk.DISABLED)
            self.btn_stop_cap.config(state=tk.NORMAL)
        except Exception as e:
            self.log(f"[CAPTURE] Error: {e}")
            self.proxy_capture = None

    def _capture_callback(self, event_type, url, data):
        if event_type == "SYS_KEY_UPGRADE":
            uid = data.get("uid")
            sign = data.get("sign")
            if uid and sign:
                self.on_keys_captured(uid, sign)

    def stop_capture(self):
        if self.proxy_capture:
            self.proxy_capture.stop()
            self.proxy_capture = None
        if self.active_proxy:
            set_windows_proxy(False)
            self.active_proxy = False
        self.log("[CAPTURE] Proxy stopped, Windows proxy restored.")
        self.btn_cap.config(state=tk.NORMAL)
        self.btn_stop_cap.config(state=tk.DISABLED)

    def get_spawned_boxes(self, start_resp):
        boxes = []
        for sid, info in start_resp.get("new_spot_change", {}).items():
            if info.get("type") == 5:
                boxes.append(int(sid))
        return boxes

    def abort_mission(self, client):
        resp = client.send_request(API_MISSION_ABORT, {"mission_id": MISSION_ID})
        if "error" in resp or "error_local" in resp:
            self.log(f"[ABORT] Failed: {resp}")
            return False
        self.log("[ABORT] Mission aborted.")
        return True

    def reroll_worker(self):
        # 清除代理环境变量
        os.environ['HTTP_PROXY'] = ''
        os.environ['HTTPS_PROXY'] = ''
        os.environ['http_proxy'] = ''
        os.environ['https_proxy'] = ''

        uid = self.var_uid.get().strip()
        sign = self.var_sign.get().strip()
        server_str = self.var_server.get().strip()

        # 解析纯 URL（支持 "名称 | URL" 或 "名称|URL" 格式）
        if '|' in server_str:
            base_url = server_str.split('|', 1)[1].strip()
        else:
            base_url = server_str

        if not uid or not sign or not base_url:
            self.log("[ERROR] UID/SIGN/Server missing. Please capture or input manually.")
            self.root.after(0, self._reset_ui_after_stop)
            return

        team_id = self.var_team_id.get()
        mode = self.var_mode.get()

        self.log("=== Rerolling (Checking Boxes) ===")
        if mode == "2box":
            self.log(f"Mode: 2box, Target pairs: {TARGET_2BOX_PAIRS}")
        else:
            self.log(f"Mode: 1box, Target spots: {TARGET_1BOX_SPOTS}")

        client = GFLClient(uid, sign, base_url)
        attempt = 0

        while not self.stop_flag:
            attempt += 1
            self.log(f"\n[Attempt {attempt}]")

            # combinationInfo
            comb_resp = client.send_request(API_MISSION_COMBINFO, {"mission_id": MISSION_ID})
            if "error" in comb_resp or "error_local" in comb_resp:
                self.log(f"[COMBINFO] Failed: {comb_resp}, retrying...")
                time.sleep(RETRY_DELAY)
                continue

            # startMission
            payload = {
                "mission_id": MISSION_ID,
                "spots": [{"spot_id": START_SPOT, "team_id": team_id}],
                "squad_spots": [], "sangvis_spots": [], "vehicle_spots": [],
                "ally_spots": [], "mission_ally_spots": [],
                "ally_id": int(time.time())
            }
            start_resp = client.send_request(API_MISSION_START, payload)
            if "error" in start_resp or "error_local" in start_resp:
                self.log(f"[START] Failed: {start_resp}, retrying...")
                time.sleep(RETRY_DELAY)
                continue

            boxes = self.get_spawned_boxes(start_resp)
            self.log(f"    Boxes: {boxes}")

            satisfied = False
            if mode == "2box":
                # 检查是否有任意一组预设完全匹配
                for pair in TARGET_2BOX_PAIRS:
                    if all(spot in boxes for spot in pair):
                        satisfied = True
                        self.log(f"    Matched pair: {pair}")
                        break
            else:  # 1box
                if any(spot in boxes for spot in TARGET_1BOX_SPOTS):
                    satisfied = True

            if satisfied:
                self.log("\n[SUCCESS] Desired boxes found! Enjoy the game!")
                self.log(f"    Final boxes: {boxes}")
                break
            else:
                if mode == "2box":
                    self.log(f"   No target pair fully matched, aborting mission...")
                else:
                    self.log(f"   Desired boxes: {TARGET_1BOX_SPOTS}. Boxes not satisfied, aborting mission...")
                self.abort_mission(client)
                time.sleep(RETRY_DELAY)

        self.log("[*] Stopped.")
        self.root.after(0, self._reset_ui_after_stop)

    def _reset_ui_after_stop(self):
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.stop_flag = False
        self.reroll_thread = None

    def start_reroll(self):
        if self.reroll_thread and self.reroll_thread.is_alive():
            self.log("[WARN] Reroll already running.")
            return
        self.stop_flag = False
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.reroll_thread = threading.Thread(target=self.reroll_worker, daemon=True)
        self.reroll_thread.start()

    def stop_reroll(self):
        self.stop_flag = True
        self.log("[STOP] Requested stop after current attempt...")

    def on_close(self):
        self.stop_capture()
        self.stop_flag = True
        self.root.destroy()

# ========== 主入口 ==========
if __name__ == "__main__":
    root = tk.Tk()
    app = RerollApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()