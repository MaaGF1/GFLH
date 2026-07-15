# pick_coin_gui.py
# 刷取 10352 关卡随机节点掉落的 GUI 工具

import sys
import time
import json
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from gflzirc import (
    GFLClient, GFLProxy, set_windows_proxy,
    SERVERS, STATIC_KEY, DEFAULT_SIGN,
    API_MISSION_COMBINFO, API_MISSION_START, API_INDEX_GUIDE,
    API_MISSION_TEAM_MOVE, API_MISSION_ABORT, API_GUN_RETIRE,
    GUIDE_COURSE_10352
)

# ========== 常量配置 ==========
MISSION_ID = 10352
START_SPOT = 13280
MOVE1_TO = 13277
MOVE2_TO = 13278

class PickCoinApp:
    def __init__(self, root):
        self.root = root
        self.root.title("GFLH - PickCoin")
        self.root.geometry("620x600")
        try:
            self.root.iconbitmap("mk/icon.ico")
        except:
            pass

        self.proxy_capture = None
        self.active_proxy = False
        self.stop_flag = False
        self.worker_thread = None

        self.var_uid = tk.StringVar()
        self.var_sign = tk.StringVar()
        self.var_server = tk.StringVar()
        self.var_team_id = tk.IntVar(value=1)
        self.var_macro_loops = tk.IntVar(value=500)
        self.var_missions_per_retire = tk.IntVar(value=50)

        self.setup_top_bar()
        self.setup_control_panel()
        self.setup_log_area()

    def setup_top_bar(self):
        self.frame_top = ttk.LabelFrame(self.root, text="1. 用户配置", padding=10)
        self.frame_top.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(self.frame_top, text="UID:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(self.frame_top, textvariable=self.var_uid, width=30).grid(row=0, column=1, padx=5, pady=2)

        ttk.Label(self.frame_top, text="Sign Key:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Entry(self.frame_top, textvariable=self.var_sign, width=30).grid(row=1, column=1, padx=5, pady=2)

        ttk.Label(self.frame_top, text="服务器:").grid(row=2, column=0, sticky=tk.W, pady=2)
        server_items = [f"{name} | {url}" for name, url in SERVERS.items()]
        cb = ttk.Combobox(self.frame_top, textvariable=self.var_server, values=server_items, width=45)
        cb.grid(row=2, column=1, padx=5, pady=2)
        if server_items:
            cb.current(0)

        self.btn_cap = ttk.Button(self.frame_top, text="自动捕获密钥", command=self.start_capture)
        self.btn_cap.grid(row=0, column=2, padx=5)
        self.btn_stop_cap = ttk.Button(self.frame_top, text="停止捕获", command=self.stop_capture, state=tk.DISABLED)
        self.btn_stop_cap.grid(row=1, column=2, padx=5)

    def setup_control_panel(self):
        self.frame_ctrl = ttk.LabelFrame(self.root, text="2. 捡垃圾设置", padding=10)
        self.frame_ctrl.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(self.frame_ctrl, text="梯队 ID:").grid(row=0, column=0, sticky=tk.W, pady=5)
        team_spin = ttk.Spinbox(self.frame_ctrl, from_=1, to=14, textvariable=self.var_team_id, width=5)
        team_spin.grid(row=0, column=1, sticky=tk.W, padx=5)

        ttk.Label(self.frame_ctrl, text="总循环次数 :").grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Entry(self.frame_ctrl, textvariable=self.var_macro_loops, width=10).grid(row=1, column=1, sticky=tk.W, padx=5)

        ttk.Label(self.frame_ctrl, text="每轮次数 :").grid(row=2, column=0, sticky=tk.W, pady=5)
        ttk.Entry(self.frame_ctrl, textvariable=self.var_missions_per_retire, width=10).grid(row=2, column=1, sticky=tk.W, padx=5)

        btn_frame = ttk.Frame(self.frame_ctrl)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=10)
        self.btn_start = ttk.Button(btn_frame, text="启动", command=self.start_farming)
        self.btn_start.pack(side=tk.LEFT, padx=5)
        self.btn_stop = ttk.Button(btn_frame, text="停止", command=self.stop_farming, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=5)

    def setup_log_area(self):
        self.frame_log = ttk.LabelFrame(self.root, text="日志区", padding=5)
        self.frame_log.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.txt_log = tk.Text(self.frame_log, height=15, state=tk.DISABLED)
        self.txt_log.pack(fill=tk.BOTH, expand=True)

    def log(self, msg):
        
        self.root.after(0, self._append_log, msg)

    def _append_log(self, msg):
        self.txt_log.config(state=tk.NORMAL)
        self.txt_log.insert(tk.END, msg + "\n")
        self.txt_log.see(tk.END)
        self.txt_log.config(state=tk.DISABLED)

    
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

    def parse_random_node_drop(self, resp_data):

        keys = list(resp_data.keys())
        try:
            target_idx = keys.index("building_defender_change") - 1
            if target_idx >= 0:
                reward_key = keys[target_idx]
                if reward_key not in ["trigger_para", "mission_win_step_control_ids", "spot_act_info"]:
                    reward_val = resp_data[reward_key]
                    self.log(f"[+] Random Node Drop Captured -> {reward_key} : {reward_val}")
        except ValueError:
            pass

    def farm_mission(self, client, team_id):
        # combinationInfo
        comb_resp = client.send_request(API_MISSION_COMBINFO, {"mission_id": MISSION_ID})
        if "error" in comb_resp or "error_local" in comb_resp:
            self.log(f"[-] combinationInfo error: {comb_resp}")
            return None

        start_payload = {
            "mission_id": MISSION_ID,
            "spots": [{"spot_id": START_SPOT, "team_id": team_id}],
            "squad_spots": [], "sangvis_spots": [], "vehicle_spots": [],
            "ally_spots": [], "mission_ally_spots": [],
            "ally_id": int(time.time())
        }
        start_resp = client.send_request(API_MISSION_START, start_payload)
        if "error" in start_resp or "error_local" in start_resp:
            self.log(f"[-] startMission error: {start_resp}")
            return None

        guide_payload = {"guide": json.dumps({"course": GUIDE_COURSE_10352}, separators=(',', ':'))}
        guide_resp = client.send_request(API_INDEX_GUIDE, guide_payload)
        if "error" in guide_resp or "error_local" in guide_resp:
            self.log(f"[-] guide error: {guide_resp}")
        time.sleep(0.2)

        move1_payload = {
            "person_type": 1, "person_id": team_id,
            "from_spot_id": START_SPOT, "to_spot_id": MOVE1_TO, "move_type": 1
        }
        move1_resp = client.send_request(API_MISSION_TEAM_MOVE, move1_payload)
        if "error" in move1_resp or "error_local" in move1_resp:
            self.log(f"[-] teamMove1 error: {move1_resp}")
            return None
        time.sleep(0.2)

        move2_payload = {
            "person_type": 1, "person_id": team_id,
            "from_spot_id": MOVE1_TO, "to_spot_id": MOVE2_TO, "move_type": 1
        }
        move2_resp = client.send_request(API_MISSION_TEAM_MOVE, move2_payload)
        if "error" in move2_resp or "error_local" in move2_resp:
            self.log(f"[-] teamMove2 error: {move2_resp}")
            return None
        self.parse_random_node_drop(move2_resp)
        time.sleep(0.1)

        abort_resp = client.send_request(API_MISSION_ABORT, {"mission_id": MISSION_ID})
        if "error" in abort_resp or "error_local" in abort_resp:
            self.log(f"[-] abortMission error: {abort_resp}")
        time.sleep(0.2)

        return []  

    def farm_worker(self):
        import os
        import traceback

        try:
            os.environ['HTTP_PROXY'] = ''
            os.environ['HTTPS_PROXY'] = ''
            os.environ['http_proxy'] = ''
            os.environ['https_proxy'] = ''

            uid = self.var_uid.get().strip()
            sign = self.var_sign.get().strip()
            server_str = self.var_server.get().strip()
            if " | " in server_str:
                base_url = server_str.split(" | ")[1]
            else:
                base_url = server_str

            try:
                team_id = self.var_team_id.get()
                macro_loops = self.var_macro_loops.get()
                missions_per_retire = self.var_missions_per_retire.get()
            except tk.TclError as e:
                self.log(f"[ERROR] Please type in valid integers: {e}")
                self.root.after(0, self._reset_ui_after_stop)
                return

            if not uid or not sign or not base_url:
                self.log("[ERROR] UID/SIGN/Server missing. Please capture or input manually.")
                self.root.after(0, self._reset_ui_after_stop)
                return

            team_id = self.var_team_id.get()
            macro_loops = self.var_macro_loops.get()
            missions_per_retire = self.var_missions_per_retire.get()

            self.log("=== GFL Protocol Auto-Farming Started (Mission 10352) ===")
            self.log(f"Team ID: {team_id}, MACRO_LOOPS: {macro_loops}, MISSIONS_PER_RETIRE: {missions_per_retire}")

            client = GFLClient(uid, sign, base_url)
            stop_macro = False
            stop_micro = False

            for macro in range(1, macro_loops + 1):
                if stop_macro or self.stop_flag:
                    break
                self.log(f"\n--- MACRO BATCH {macro} / {macro_loops} ---")
                batch_guns = []
                for micro in range(1, missions_per_retire + 1):
                    if stop_micro or self.stop_flag:
                        break
                    self.log(f"\n[*] Starting Micro Run {micro} / {missions_per_retire} ...")
                    dropped = self.farm_mission(client, team_id)
                    if dropped is None:
                        self.log("[-] Run failed or aborted. Aborting mission...")
                        client.send_request(API_MISSION_ABORT, {"mission_id": MISSION_ID})
                        time.sleep(3)
                        continue
                    batch_guns.extend(dropped)
                    time.sleep(0.2)
                
                if batch_guns:
                    self.log(f"[*] Submitting {len(batch_guns)} T-Dolls for Auto-Retire...")
                    resp = client.send_request(API_GUN_RETIRE, batch_guns)
                    if resp.get("success"):
                        self.log("[+] Auto-Retire Successful!")
                    else:
                        self.log(f"[-] Retire Failed: {resp}")
                time.sleep(1)

            self.log("\n[*] Farming runs ended.")
            self.root.after(0, self._reset_ui_after_stop)
        
        except Exception as e:
            self.log(f"[Error] farm_worker error: {e}")
            traceback.print_exc()
            self.root.after(0, self._reset_ui_after_stop)

    def _reset_ui_after_stop(self):
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.stop_flag = False
        self.worker_thread = None

    def start_farming(self):
        if self.worker_thread and self.worker_thread.is_alive():
            self.log("[WARN] Farming already running.")
            return
       
        if self.proxy_capture:
            self.stop_capture()
        self.stop_flag = False
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.worker_thread = threading.Thread(target=self.farm_worker, daemon=True)
        self.worker_thread.start()

    def stop_farming(self):
        self.stop_flag = True
        self.log("[STOP] Requested stop after current attempt...")

    def on_close(self):
        self.stop_capture()
        self.stop_flag = True
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = PickCoinApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
