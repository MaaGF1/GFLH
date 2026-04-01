# src/monitor/monitor_gui.py

import os
import time
import json
import tkinter as tk
from tkinter import ttk
from gflzirc import GFLMonitorProxy
from utils import global_i18n

class MonitorApp:
    def __init__(self, parent, log_callback, proxy_callback):
        self.parent = parent
        self.log = log_callback
        self.set_proxy_state = proxy_callback
        self.proxy_instance = None
        self.packet_counter = 1
        self.setup_ui()

    def setup_ui(self):
        self.frame = ttk.LabelFrame(self.parent, text=global_i18n.get("mon_group"), padding=10)
        self.frame.pack(fill=tk.X, padx=10, pady=5)

        self.btn_start = ttk.Button(self.frame, text=global_i18n.get("btn_start_mon"), command=self.start_monitor)
        self.btn_start.pack(side=tk.LEFT, padx=5)

        self.btn_stop = ttk.Button(self.frame, text=global_i18n.get("btn_stop_mon"), command=self.stop_monitor, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=5)

    def refresh_ui(self):
        self.frame.config(text=global_i18n.get("mon_group"))
        self.btn_start.config(text=global_i18n.get("btn_start_mon"))
        self.btn_stop.config(text=global_i18n.get("btn_stop_mon"))

    def on_traffic(self, direction, url, json_obj):
        if direction == "SYS":
            self.log(f"[MONITOR] Key updated - UID: {json_obj.get('uid')}")
            return
        
        self.log(f"[MONITOR] Captured {direction}: {url}")
        if not os.path.exists("traffic_dumps"):
            os.makedirs("traffic_dumps")
        
        ts = int(time.time())
        fname = f"traffic_dumps/{self.packet_counter:04d}_{direction}_{ts}.json"
        try:
            with open(fname, "w", encoding="utf-8") as f:
                json.dump(json_obj, f, indent=4, ensure_ascii=False)
            self.packet_counter += 1
        except Exception as e:
            self.log(f"[MONITOR] File error: {e}")

    def start_monitor(self):
        try:
            self.proxy_instance = GFLMonitorProxy(8081, "yundoudou", self.on_traffic)
            self.proxy_instance.start()
            self.set_proxy_state("monitor", True, 8081)
            self.log("[MONITOR] Started on port 8081.")
            self.btn_start.config(state=tk.DISABLED)
            self.btn_stop.config(state=tk.NORMAL)
        except Exception as e:
            self.log(f"[MONITOR] Error: {e}")

    def stop_monitor(self):
        if self.proxy_instance:
            self.proxy_instance.stop()
            self.proxy_instance = None
            self.set_proxy_state("monitor", False, 8081)
            self.log("[MONITOR] Stopped safely.")
            self.btn_start.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.DISABLED)