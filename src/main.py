# src/main.py

import sys
import tkinter as tk
from tkinter import ttk
from gflzirc import GFLCaptureProxy, set_windows_proxy
from monitor.monitor_gui import MonitorApp
from target_train.train_gui import TargetTrainApp
from include.constants import SERVER_LIST
from utils import global_i18n, get_resource_path

class MainApp:
    def __init__(self, root):
        self.root = root
        self.root.title(global_i18n.get("app_title"))
        self.root.geometry("620x650")
        
        # Setup Window Icon
        try:
            icon_path = get_resource_path("mk/icon.ico")
            self.root.iconbitmap(icon_path)
        except Exception as e:
            print(f"Icon missing or OS not supported: {e}")
        
        self.proxy_capture = None
        
        self.setup_top_bar()
        self.monitor_app = MonitorApp(self.root, self.log)
        self.train_app = TargetTrainApp(self.root, self.get_config, self.log)
        self.setup_log_area()

    def log(self, msg):
        self.root.after(0, self._append_log, msg)

    def _append_log(self, msg):
        self.txt_log.config(state=tk.NORMAL)
        self.txt_log.insert(tk.END, msg + "\n")
        self.txt_log.see(tk.END)
        self.txt_log.config(state=tk.DISABLED)

    def get_config(self):
        return {
            "uid": self.var_uid.get(),
            "sign": self.var_sign.get(),
            "server": self.var_server.get()
        }

    def setup_top_bar(self):
        self.frame_top = ttk.LabelFrame(self.root, text=global_i18n.get("cfg_group"), padding=10)
        self.frame_top.pack(fill=tk.X, padx=10, pady=5)

        self.lbl_uid = ttk.Label(self.frame_top, text=global_i18n.get("uid"))
        self.lbl_uid.grid(row=0, column=0, sticky=tk.W)
        self.var_uid = tk.StringVar()
        ttk.Entry(self.frame_top, textvariable=self.var_uid, width=30).grid(row=0, column=1, padx=5, pady=2)

        self.lbl_sign = ttk.Label(self.frame_top, text=global_i18n.get("sign"))
        self.lbl_sign.grid(row=1, column=0, sticky=tk.W)
        self.var_sign = tk.StringVar()
        ttk.Entry(self.frame_top, textvariable=self.var_sign, width=30).grid(row=1, column=1, padx=5, pady=2)

        self.lbl_server = ttk.Label(self.frame_top, text=global_i18n.get("server"))
        self.lbl_server.grid(row=2, column=0, sticky=tk.W)
        self.var_server = tk.StringVar()
        
        # Load from Constants
        cb = ttk.Combobox(self.frame_top, textvariable=self.var_server, values=SERVER_LIST, width=45)
        cb.grid(row=2, column=1, padx=5, pady=2)
        cb.current(0)

        self.btn_cap = ttk.Button(self.frame_top, text=global_i18n.get("btn_capture"), command=self.start_capture)
        self.btn_cap.grid(row=0, column=2, padx=5)
        
        self.btn_stop_cap = ttk.Button(self.frame_top, text=global_i18n.get("btn_stop_capture"), command=self.stop_capture, state=tk.DISABLED)
        self.btn_stop_cap.grid(row=1, column=2, padx=5)

        # Language Switch Button
        self.btn_lang = ttk.Button(self.frame_top, text=global_i18n.get("btn_lang"), command=self.switch_language)
        self.btn_lang.grid(row=2, column=2, padx=5)

    def switch_language(self):
        new_lang = "zh" if global_i18n.lang == "en" else "en"
        global_i18n.load_lang(new_lang)
        self.refresh_ui()

    def refresh_ui(self):
        self.root.title(global_i18n.get("app_title"))
        self.frame_top.config(text=global_i18n.get("cfg_group"))
        self.lbl_uid.config(text=global_i18n.get("uid"))
        self.lbl_sign.config(text=global_i18n.get("sign"))
        self.lbl_server.config(text=global_i18n.get("server"))
        self.btn_cap.config(text=global_i18n.get("btn_capture"))
        self.btn_stop_cap.config(text=global_i18n.get("btn_stop_capture"))
        self.btn_lang.config(text=global_i18n.get("btn_lang"))
        
        self.monitor_app.refresh_ui()
        self.train_app.refresh_ui()
        self.frame_log.config(text=global_i18n.get("log_console"))

    def setup_log_area(self):
        self.frame_log = ttk.LabelFrame(self.root, text=global_i18n.get("log_console"), padding=5)
        self.frame_log.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.txt_log = tk.Text(self.frame_log, height=10, state=tk.DISABLED)
        self.txt_log.pack(fill=tk.BOTH, expand=True)

    def on_keys_captured(self, uid, sign):
        self.root.after(0, self.var_uid.set, uid)
        self.root.after(0, self.var_sign.set, sign)
        self.log(f"[SYS] Captured UID: {uid}")

    def start_capture(self):
        if not self.proxy_capture:
            self.proxy_capture = GFLCaptureProxy(8080, "yundoudou", self.on_keys_captured)
            self.proxy_capture.start()
            set_windows_proxy(True, "127.0.0.1:8080")
            self.log("[SYS] Capture proxy started on 8080.")
            self.btn_cap.config(state=tk.DISABLED)
            self.btn_stop_cap.config(state=tk.NORMAL)

    def stop_capture(self):
        if self.proxy_capture:
            self.proxy_capture.stop()
            set_windows_proxy(False)
            self.proxy_capture = None
            self.log("[SYS] Capture proxy stopped.")
            self.btn_cap.config(state=tk.NORMAL)
            self.btn_stop_cap.config(state=tk.DISABLED)

    def on_close(self):
        self.stop_capture()
        self.monitor_app.stop_monitor()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = MainApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()