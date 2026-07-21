# f2p_gui.py


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
    API_MISSION_END_TURN, API_MISSION_START_ENEMY_TURN,
    API_MISSION_END_ENEMY_TURN, API_MISSION_START_TURN,
    API_MISSION_ABORT, API_GUN_RETIRE, GUIDE_COURSE_11880,
)


API_INDEX = "Index/index"

MISSION_ID = 11869
START_SPOT = 901897


class F2PAutoApp:
    def __init__(self, root):
        self.root = root
        self.root.title("GFLH - F2P")
        self.root.geometry("700x700")
        try:
            self.root.iconbitmap("mk/icon.ico")
        except:
            pass

    
        self.proxy_instance = None
        self.active_proxy = False
        self.stop_flag = False
        self.worker_thread = None
        self.capture_thread = None
        self.capture_event = threading.Event()

        
        self.var_uid = tk.StringVar(value="")
        self.var_sign = tk.StringVar(value="")
        self.var_server = tk.StringVar()
        self.var_squad_id = tk.StringVar(value="")
        self.var_macro_loops = tk.IntVar(value="600")
        self.var_missions_per_retire = tk.IntVar(value="50")
        self.var_upstream_proxy = tk.StringVar(value="")  

        self.setup_ui()

  
    def setup_ui(self):
    
        frame_cfg = ttk.LabelFrame(self.root, text="1. 服务器与密钥", padding=10)
        frame_cfg.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(frame_cfg, text="服务器:").grid(row=0, column=0, sticky=tk.W, pady=2)
        server_items = [f"{name} | {url}" for name, url in SERVERS.items()]
        cb = ttk.Combobox(frame_cfg, textvariable=self.var_server, values=server_items, width=50, state='readonly')
        cb.grid(row=0, column=1, padx=5, sticky=tk.W)
        if server_items:
            cb.current(0)

        ttk.Label(frame_cfg, text="UID:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Entry(frame_cfg, textvariable=self.var_uid, width=50).grid(row=1, column=1, padx=5)

        ttk.Label(frame_cfg, text="Sign Key:").grid(row=2, column=0, sticky=tk.W, pady=2)
        ttk.Entry(frame_cfg, textvariable=self.var_sign, width=50).grid(row=2, column=1, padx=5)

       

        frame_param = ttk.LabelFrame(self.root, text="2. 基础配置", padding=10)
        frame_param.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(frame_param, text="重装ID:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(frame_param, textvariable=self.var_squad_id, width=10).grid(row=0, column=1, padx=5, sticky=tk.W)

        ttk.Label(frame_param, text="总循环次数 (MACRO_LOOPS):").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Entry(frame_param, textvariable=self.var_macro_loops, width=10).grid(row=1, column=1, sticky=tk.W, padx=5)

        ttk.Label(frame_param, text="每批次数 (MISSIONS_PER_RETIRE):").grid(row=2, column=0, sticky=tk.W, pady=2)
        ttk.Entry(frame_param, textvariable=self.var_missions_per_retire, width=10).grid(row=2, column=1, sticky=tk.W, padx=5)


        frame_ctrl = ttk.LabelFrame(self.root, text="3. 控制", padding=10)
        frame_ctrl.pack(fill=tk.X, padx=10, pady=5)

        btn_frame = ttk.Frame(frame_ctrl)
        btn_frame.pack()
        self.btn_capture = ttk.Button(btn_frame, text="捕获UID/SIGN_KEY/SQUAD ID", command=self.start_capture)
        self.btn_capture.pack(side=tk.LEFT, padx=5)
        self.btn_stop_capture = ttk.Button(btn_frame, text="停止捕获", command=self.stop_capture, state=tk.DISABLED)
        self.btn_stop_capture.pack(side=tk.LEFT, padx=5)
        self.btn_start = ttk.Button(btn_frame, text="开始", command=self.start_farming)
        self.btn_start.pack(side=tk.LEFT, padx=5)
        self.btn_stop = ttk.Button(btn_frame, text="停止", command=self.stop_farming, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=5)


        frame_log = ttk.LabelFrame(self.root, text="日志区", padding=5)
        frame_log.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.txt_log = tk.Text(frame_log, height=15, state=tk.DISABLED)
        self.txt_log.pack(fill=tk.BOTH, expand=True)

    def log(self, msg):
        self.root.after(0, self._append_log, msg)

    def _append_log(self, msg):
        self.txt_log.config(state=tk.NORMAL)
        self.txt_log.insert(tk.END, msg + "\n")
        self.txt_log.see(tk.END)
        self.txt_log.config(state=tk.DISABLED)

    
    def start_capture(self):
        if self.capture_thread and self.capture_thread.is_alive():
            self.log("[CAPTURE] Capture already in progress.")
            return
        if self.proxy_instance:
            self.log("[CAPTURE] Proxy already running.")
            return
        self.capture_event.clear()
        self.capture_thread = threading.Thread(target=self.capture_worker, daemon=True)
        self.capture_thread.start()
        self.btn_capture.config(state=tk.DISABLED)
        self.btn_stop_capture.config(state=tk.NORMAL)

    def stop_capture(self):
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_event.set()
            if self.proxy_instance:
                try:
                    self.proxy_instance.stop()
                    set_windows_proxy(False)
                except Exception as e:
                    self.log(f"[CAPTURE] Error during manual stop: {e}")
                self.proxy_instance = None
            self.log("[CAPTURE] Stop requested, exiting capture thread...")
        else:
            self.log("[CAPTURE] No capture thread running.")

    def capture_worker(self):
        proxy = None
        try:
            captured_uid = None
            captured_sign = None
            captured_squad_id = None

            def capture_callback(event_type, url, data):
                nonlocal captured_uid, captured_sign, captured_squad_id
                if event_type == "SYS_KEY_UPGRADE":
                    uid = data.get("uid")
                    sign = data.get("sign")
                    if uid and sign:
                        captured_uid = uid
                        captured_sign = sign
                        self.log(f"[CAPTURE] Captured UID: {uid}, SIGN.")
                elif event_type == "S2C" and "Index/index" in url:
                    if isinstance(data, dict):
                        squad_info = data.get("squad_with_user_info", {})
                        if squad_info:
                            first_key = next(iter(squad_info.keys()))
                            first_squad = squad_info[first_key]
                            squad_id = first_squad.get("id") or first_key
                            captured_squad_id = str(squad_id)
                            self.log(f"[CAPTURE] Found squad ID: {squad_id}")
                            if captured_uid and captured_sign:
                                self.capture_event.set()

            
            proxy = GFLProxy(8080, STATIC_KEY, capture_callback)
            self.proxy_instance = proxy
            proxy.start()
            set_windows_proxy(True, "127.0.0.1:8080")
            self.log("[CAPTURE] Proxy started. Please log in to the game (or reconnect) to capture keys and squad ID.")
            self.log("[CAPTURE] This may take a few moments. Click 'Stop Capture' to cancel.")

           
            self.capture_event.wait()

            
            if captured_uid and captured_sign and captured_squad_id:
                self.root.after(0, lambda: self.var_uid.set(captured_uid))
                self.root.after(0, lambda: self.var_sign.set(captured_sign))
                self.root.after(0, lambda: self.var_squad_id.set(captured_squad_id))
                self.log("[CAPTURE] UID, SIGN, and Squad ID updated successfully.")
            else:
                self.log("[CAPTURE] Capture incomplete: missing UID/SIGN or Squad ID.")
                if captured_uid and captured_sign:
                    self.log("[CAPTURE] UID/SIGN captured, but squad ID not found.")
                else:
                    self.log("[CAPTURE] UID/SIGN not captured.")

        except Exception as e:
            self.log(f"[CAPTURE] Error during capture: {e}")
        finally:
            
            if self.proxy_instance:
                try:
                    self.proxy_instance.stop()
                except Exception as e:
                    self.log(f"[CAPTURE] Error stopping proxy: {e}")
                self.proxy_instance = None
            try:
                set_windows_proxy(False)
            except Exception as e:
                self.log(f"[CAPTURE] Error disabling system proxy: {e}")
            self.log("[CAPTURE] Proxy stopped and system proxy disabled.")

            
            self.root.after(0, lambda: self.btn_capture.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.btn_stop_capture.config(state=tk.DISABLED))
            self.capture_thread = None

    def farm_mission(self, client, squad_id):
        if self.stop_flag:
            return None

  
        comb_resp = client.send_request(API_MISSION_COMBINFO, {"mission_id": MISSION_ID})
        if "error" in comb_resp or "error_local" in comb_resp:
            self.log(f"[-] combInfo error: {comb_resp}")
            return None

        
        start_payload = {
            "mission_id": MISSION_ID,
            "spots": [],
            "squad_spots": [{"spot_id": START_SPOT, "squad_with_user_id": int(squad_id), "battleskill_switch": 1}],
            "sangvis_spots": [], "vehicle_spots": [], "ally_spots": [], "mission_ally_spots": [],
            "ally_id": int(time.time())
        }
        start_resp = client.send_request(API_MISSION_START, start_payload)
        if "error" in start_resp or "error_local" in start_resp:
            self.log(f"[-] startMission error: {start_resp}")
            return None

        
        guide_payload = {"guide": json.dumps({"course": GUIDE_COURSE_11880}, separators=(',', ':'))}
        guide_resp = client.send_request(API_INDEX_GUIDE, guide_payload)
        if "error" in guide_resp or "error_local" in guide_resp:
            self.log(f"[-] guide error: {guide_resp}")
          

        time.sleep(0.2)

  
        end_resp = client.send_request(API_MISSION_END_TURN, {})
        if "error" in end_resp or "error_local" in end_resp:
            self.log(f"[-] endTurn error: {end_resp}")
            return None
        time.sleep(0.2)

        start_enemy = client.send_request(API_MISSION_START_ENEMY_TURN, {})
        if "error" in start_enemy or "error_local" in start_enemy:
            self.log(f"[-] startEnemyTurn error: {start_enemy}")
            return None
        time.sleep(0.2)

        end_enemy = client.send_request(API_MISSION_END_ENEMY_TURN, {})
        if "error" in end_enemy or "error_local" in end_enemy:
            self.log(f"[-] endEnemyTurn error: {end_enemy}")
            return None
        time.sleep(0.2)

        start_turn = client.send_request(API_MISSION_START_TURN, {})
        if "error" in start_turn or "error_local" in start_turn:
            self.log(f"[-] startTurn error: {start_turn}")
            return None

       
        win_result = start_turn.get("mission_win_result", {})
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

    def farming_worker(self):
        uid = self.var_uid.get().strip()
        sign = self.var_sign.get().strip()
        server_str = self.var_server.get().strip()
        if " | " in server_str:
            base_url = server_str.split(" | ")[1]
        else:
            base_url = server_str
        if not uid or not sign or not base_url:
            self.log("[ERROR] UID/SIGN/Server missing. Please capture or input.")
            self.root.after(0, self._reset_ui)
            return

        squad_id_str = self.var_squad_id.get().strip()
        if not squad_id_str:
            self.log("[ERROR] Squad ID missing. Please capture or input.")
            self.root.after(0, self._reset_ui)
            return
        try:
            squad_id = int(squad_id_str)
        except:
            self.log("[ERROR] Invalid Squad ID (must be integer).")
            self.root.after(0, self._reset_ui)
            return

        macro_loops = self.var_macro_loops.get()
        missions_per_retire = self.var_missions_per_retire.get()

        upstream = self.var_upstream_proxy.get().strip()
        proxies = {"http": upstream, "https": upstream} if upstream else None

        client = GFLClient(uid, sign, base_url, proxies=proxies)

        self.log("=== GFL Protocol Auto-Farming Started (Mission 11880) ===")
        self.log(f"Macro Loops: {macro_loops}, Missions per Retire: {missions_per_retire}, Squad ID: {squad_id}")

        for macro in range(1, macro_loops + 1):
            if self.stop_flag:
                break
            self.log(f"\n--- MACRO BATCH {macro} / {macro_loops} ---")
            batch_guns = []
            for micro in range(1, missions_per_retire + 1):
                if self.stop_flag:
                    break
                self.log(f"\n[*] Starting Micro Run {micro} / {missions_per_retire} ...")
                dropped = self.farm_mission(client, squad_id)
                if dropped is None:
                    self.log("[-] Run failed or aborted. Aborting mission...")
                    client.send_request(API_MISSION_ABORT, {"mission_id": MISSION_ID})
                    time.sleep(3)
                    continue
                batch_guns.extend(dropped)
                time.sleep(1)
            self.retire_guns(client, batch_guns)
            time.sleep(2)

        self.log("\n[*] Farming runs ended.")
        self.root.after(0, self._reset_ui)

    def _reset_ui(self):
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.stop_flag = False
        self.worker_thread = None

    def start_farming(self):
        if self.worker_thread and self.worker_thread.is_alive():
            self.log("[WARN] Farming already running.")
            return
        if self.proxy_instance:
            self.proxy_instance.stop()
            set_windows_proxy(False)
            self.proxy_instance = None
            self.active_proxy = False
        self.stop_flag = False
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.worker_thread = threading.Thread(target=self.farming_worker, daemon=True)
        self.worker_thread.start()

    def stop_farming(self):
        self.stop_flag = True
        self.log("[STOP] Requested stop after current micro run.")

    def on_close(self):
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_event.set()
            self.capture_thread.join(timeout=2)
        if self.proxy_instance:
            self.proxy_instance.stop()
        set_windows_proxy(False)
        self.stop_flag = True
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = F2PAutoApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
