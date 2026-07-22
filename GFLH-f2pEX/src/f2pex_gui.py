# farm_144_gui.py
# 刷取关卡 144 的 GUI 工具（使用 team_id 部署）
import os
import sys
import time
import threading
import tkinter as tk
from tkinter import ttk

from gflzirc import (
    GFLClient, GFLProxy, set_windows_proxy,
    SERVERS, STATIC_KEY, DEFAULT_SIGN,
    API_MISSION_COMBINFO, API_MISSION_START,
    API_MISSION_END_TURN, API_MISSION_START_ENEMY_TURN,
    API_MISSION_END_ENEMY_TURN, API_MISSION_START_TURN,
    API_MISSION_ABORT, API_GUN_RETIRE
)

def get_resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


MISSION_ID = 144
START_SPOT = 97026          
TEAM_ID_DEFAULT = 1

class Farm144App:
    def __init__(self, root):
        self.root = root
        self.root.title("GFLH - F2Pex")
        self.root.geometry("620x600")
        icon_path = get_resource_path("mk/icon.ico")
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except Exception as e:
                print(f"Set icon failed: {e}")
            else:
                print(f"Icon not found: {icon_path}")

        self.proxy_capture = None
        self.active_proxy = False
        self.stop_flag = False
        self.worker_thread = None

        self.var_uid = tk.StringVar()
        self.var_sign = tk.StringVar()
        self.var_server = tk.StringVar()
        self.var_team_id = tk.IntVar(value=TEAM_ID_DEFAULT)
        self.var_macro_loops = tk.IntVar(value=4000)
        self.var_missions_per_retire = tk.IntVar(value=50)

        self.setup_top_bar()
        self.setup_control_panel()
        self.setup_log_area()

    # ---------- UI 构建 ----------
    def setup_top_bar(self):
        frame_top = ttk.LabelFrame(self.root, text="1. 用户配置", padding=10)
        frame_top.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(frame_top, text="UID:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(frame_top, textvariable=self.var_uid, width=30).grid(row=0, column=1, padx=5, pady=2)

        ttk.Label(frame_top, text="Sign Key:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Entry(frame_top, textvariable=self.var_sign, width=30).grid(row=1, column=1, padx=5, pady=2)

        ttk.Label(frame_top, text="服务器:").grid(row=2, column=0, sticky=tk.W, pady=2)
        server_items = [f"{name} | {url}" for name, url in SERVERS.items()]
        cb = ttk.Combobox(frame_top, textvariable=self.var_server, values=server_items, width=45)
        cb.grid(row=2, column=1, padx=5, pady=2)
        if server_items:
            cb.current(0)

        self.btn_cap = ttk.Button(frame_top, text="自动捕获密钥", command=self.start_capture)
        self.btn_cap.grid(row=0, column=2, padx=5)
        self.btn_stop_cap = ttk.Button(frame_top, text="停止捕获", command=self.stop_capture, state=tk.DISABLED)
        self.btn_stop_cap.grid(row=1, column=2, padx=5)

    def setup_control_panel(self):
        frame_ctrl = ttk.LabelFrame(self.root, text="2. 挂机设置", padding=10)
        frame_ctrl.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(frame_ctrl, text="梯队 ID :").grid(row=0, column=0, sticky=tk.W, pady=5)
        team_spin = ttk.Spinbox(frame_ctrl, from_=1, to=14, textvariable=self.var_team_id, width=5)
        team_spin.grid(row=0, column=1, sticky=tk.W, padx=5)

        ttk.Label(frame_ctrl, text="总循环次数 (MACRO_LOOPS):").grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Entry(frame_ctrl, textvariable=self.var_macro_loops, width=10).grid(row=1, column=1, sticky=tk.W, padx=5)

        ttk.Label(frame_ctrl, text="每批次数 (MISSIONS_PER_RETIRE):").grid(row=2, column=0, sticky=tk.W, pady=5)
        ttk.Entry(frame_ctrl, textvariable=self.var_missions_per_retire, width=10).grid(row=2, column=1, sticky=tk.W, padx=5)

        btn_frame = ttk.Frame(frame_ctrl)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=10)
        self.btn_start = ttk.Button(btn_frame, text="开始", command=self.start_farming)
        self.btn_start.pack(side=tk.LEFT, padx=5)
        self.btn_stop = ttk.Button(btn_frame, text="停止", command=self.stop_farming, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=5)

    def setup_log_area(self):
        frame_log = ttk.LabelFrame(self.root, text="日志区", padding=5)
        frame_log.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.txt_log = tk.Text(frame_log, height=15, state=tk.DISABLED)
        self.txt_log.pack(fill=tk.BOTH, expand=True)

    def log(self, msg):
        try:
            if self.root.winfo_exists():
                self.root.after(0, self._append_log, msg)
        except tk.TclError:
            pass

    def _append_log(self, msg):
        self.txt_log.config(state=tk.NORMAL)
        self.txt_log.insert(tk.END, msg + "\n")
        self.txt_log.see(tk.END)
        self.txt_log.config(state=tk.DISABLED)

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
                self.root.after(0, self.var_uid.set, uid)
                self.root.after(0, self.var_sign.set, sign)
                self.log(f"[CAPTURE] Captured UID: {uid}, SIGN.")

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

    def farm_mission(self, client, team_id):
        mission_id = MISSION_ID

        comb_resp = client.send_request(API_MISSION_COMBINFO, {"mission_id": mission_id})
        if "error" in comb_resp or "error_local" in comb_resp:
            self.log(f"[-] combinationInfo error: {comb_resp}")
            return None

        start_payload = {
            "mission_id": mission_id,
            "spots": [{"spot_id": START_SPOT, "team_id": team_id}],
            "squad_spots": [],
            "sangvis_spots": [],
            "vehicle_spots": [],
            "ally_spots": [],
            "mission_ally_spots": [],
            "ally_id": int(time.time())
        }
        start_resp = client.send_request(API_MISSION_START, start_payload)
        if "error" in start_resp or "error_local" in start_resp:
            self.log(f"[-] startMission error: {start_resp}")
            return None

        
        time.sleep(0.01)
        end_resp = client.send_request(API_MISSION_END_TURN, {})
        if "error" in end_resp or "error_local" in end_resp:
            self.log(f"[-] endTurn error: {end_resp}")
            return None

        time.sleep(0.01)
        start_enemy = client.send_request(API_MISSION_START_ENEMY_TURN, {})
        if "error" in start_enemy or "error_local" in start_enemy:
            self.log(f"[-] startEnemyTurn error: {start_enemy}")
            return None

        time.sleep(0.01)
        end_enemy = client.send_request(API_MISSION_END_ENEMY_TURN, {})
        if "error" in end_enemy or "error_local" in end_enemy:
            self.log(f"[-] endEnemyTurn error: {end_enemy}")
            return None

        time.sleep(0.01)
        final_resp = client.send_request(API_MISSION_START_TURN, {})
        if "error" in final_resp or "error_local" in final_resp:
            self.log(f"[-] startTurn error: {final_resp}")
            return None

        win_result = final_resp.get("mission_win_result", {})
        dropped = []
        reward_guns = win_result.get("reward_gun", [])
        for gun in reward_guns:
            gun_uid = int(gun.get("gun_with_user_id"))
            gun_id = gun.get("gun_id")
            self.log(f"[+] Got T-Doll! Gun ID: {gun_id} | UID: {gun_uid}")
            dropped.append(gun_uid)
        return dropped

    def retire_guns(self, client, gun_uids):
        if not gun_uids:
            return
        self.log(f"[*] Submitting {len(gun_uids)} T-Dolls for Auto-Retire...")
        resp = client.send_request(API_GUN_RETIRE, gun_uids)
        if resp.get("success"):
            self.log("[+] Auto-Retire Successful!")
        else:
            self.log(f"[-] Retire Failed: {resp}")

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
                self.root.after(0, self._reset_ui)
                return

            if not uid or not sign or not base_url:
                self.log("[ERROR] UID/SIGN/Server missing. Please capture or input manually.")
                self.root.after(0, self._reset_ui)
                return

            self.log("=== GFL Protocol Auto-Farming Started (Mission 144) ===")
            self.log(f"Team ID: {team_id}, MACRO_LOOPS: {macro_loops}, MISSIONS_PER_RETIRE: {missions_per_retire}")

            client = GFLClient(uid, sign, base_url)

            for macro in range(1, macro_loops + 1):
                if self.stop_flag:
                    break
                self.log(f"\n--- MACRO BATCH {macro} / {macro_loops} ---")
                batch_guns = []
                for micro in range(1, missions_per_retire + 1):
                    if self.stop_flag:
                        break
                    self.log(f"\n[*] Starting Micro Run {micro} / {missions_per_retire} ...")
                    dropped = self.farm_mission(client, team_id)
                    if dropped is None:
                        self.log("[-] Run failed or aborted. Aborting mission...")
                        client.send_request(API_MISSION_ABORT, {"mission_id": MISSION_ID})
                        time.sleep(3)
                        continue
                    batch_guns.extend(dropped)
                    time.sleep(0.01)  

                self.retire_guns(client, batch_guns)
                time.sleep(1)

            self.log("\n[*] Farming runs ended.")
            self.root.after(0, self._reset_ui)

        except Exception as e:
            self.log(f"[Error] farm_worker error: {e}")
            traceback.print_exc()
            self.root.after(0, self._reset_ui)

    def _reset_ui(self):
        """恢复 UI 按钮状态"""
        try:
            if self.root.winfo_exists():
                self.btn_start.config(state=tk.NORMAL)
                self.btn_stop.config(state=tk.DISABLED)
                self.stop_flag = False
                self.worker_thread = None
        except tk.TclError:
            pass

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
        self.log("[STOP] Requested stop after current micro run...")

    def on_close(self):
        self.stop_capture()
        self.stop_flag = True
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2.0)
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = Farm144App(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()