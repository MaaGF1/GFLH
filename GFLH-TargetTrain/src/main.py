# src/main.py

import tkinter as tk
from tkinter import ttk
from gflzirc import GFLProxy, set_windows_proxy  
from target_train.train_gui import TargetTrainApp
from include.constants import SERVER_LIST
from utils import global_i18n, get_resource_path


class GFLCaptureProxy:
   
    def __init__(self, port: int, static_key: str, callback, mode='auth', log_callback=None):
        self.port = port
        self.static_key = static_key
        self.callback = callback          
        self.mode = mode
        self.log_callback = log_callback
        self._proxy = None
        self._captured = {
            'uid': None,
            'sign': None,
            'enemies': None,  
            'orders': None
        }

    def start(self):
        def on_traffic(event_type, url, json_obj):
            if event_type == "SYS_KEY_UPGRADE":
                uid = json_obj.get("uid")
                sign = json_obj.get("sign")
                if uid and sign:
                    self._captured['uid'] = uid
                    self._captured['sign'] = sign
                    self._check_and_callback()

            if self.mode == 'full' and event_type == "S2C" and "Index/index" in url:
                try:
                    if isinstance(json_obj, dict):
                        user_info = json_obj.get("targettrain_collect_user_info")
                        if user_info is not None and isinstance(user_info, list):
                            enemies = []
                            orders = []
                            for item in user_info:
                                enemy_id = item.get("enemy_team_id")
                                order_id = item.get("order_id")
                                if enemy_id is not None and order_id is not None:
                                    enemies.append(str(enemy_id))
                                    orders.append(str(order_id))
                            self._captured['enemies'] = enemies
                            self._captured['orders'] = orders
                            self._check_and_callback()
                        else:
                            if self.log_callback:
                                self.log_callback("[CAPTURE] targettrain_collect_user_info is not a list or is None.")
                except Exception as e:
                    if self.log_callback:
                        self.log_callback(f"[CAPTURE] Error parsing targettrain info: {e}")

        self._proxy = GFLProxy(self.port, self.static_key, on_traffic)
        self._proxy.start()

    def _check_and_callback(self):
        
        if self.mode == 'auth':
            if self._captured['uid'] and self._captured['sign']:
                self.callback(self._captured['uid'], self._captured['sign'], None, None)
                self.stop()
        else:  # full
            if (self._captured['uid'] and self._captured['sign'] and
                    self._captured['enemies'] is not None):  
                self.callback(
                    self._captured['uid'],
                    self._captured['sign'],
                    self._captured['enemies'],
                    self._captured['orders']
                )
                self.stop()

    def stop(self):
        if self._proxy:
            self._proxy.stop()
            self._proxy = None


class MainApp:
    def __init__(self, root):
        self.root = root
        self.root.title(global_i18n.get("app_title"))
        self.root.geometry("620x620")  
        
        try:
            icon_path = get_resource_path("mk/icon.ico")
            self.root.iconbitmap(icon_path)
        except Exception as e:
            print(f"Icon missing or OS not supported: {e}")
        
        self.proxy_capture = None
        
        self.setup_top_bar()
        
        self.train_app = TargetTrainApp(self.root, self.get_config, self.log ,self.stop_capture)
        self.setup_log_area()

    def update_system_proxy(self, is_active, port=8080):
        
        if is_active:
            set_windows_proxy(True, f"127.0.0.1:{port}")
            self.log(f"[SYS] Windows proxy enabled: 127.0.0.1:{port}.")
        else:
            set_windows_proxy(False)
            self.log("[SYS] Windows proxy disabled.")

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

        # 行0：UID
        self.lbl_uid = ttk.Label(self.frame_top, text=global_i18n.get("uid"))
        self.lbl_uid.grid(row=0, column=0, sticky=tk.W)
        self.var_uid = tk.StringVar()
        ttk.Entry(self.frame_top, textvariable=self.var_uid, width=30).grid(row=0, column=1, padx=5, pady=2)

        # 行1：SIGN
        self.lbl_sign = ttk.Label(self.frame_top, text=global_i18n.get("sign"))
        self.lbl_sign.grid(row=1, column=0, sticky=tk.W)
        self.var_sign = tk.StringVar()
        ttk.Entry(self.frame_top, textvariable=self.var_sign, width=30).grid(row=1, column=1, padx=5, pady=2)

        # 行2：服务器
        self.lbl_server = ttk.Label(self.frame_top, text=global_i18n.get("server"))
        self.lbl_server.grid(row=2, column=0, sticky=tk.W)
        self.var_server = tk.StringVar()
        cb = ttk.Combobox(self.frame_top, textvariable=self.var_server, values=SERVER_LIST, width=45)
        cb.grid(row=2, column=1, padx=5, pady=2)
        cb.current(0)

        # 行3：按钮容器（均匀分布）
        btn_frame = ttk.Frame(self.frame_top)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=8)

        self.btn_cap_auth = ttk.Button(btn_frame, text=global_i18n.get("btn_auth_capture"), command=lambda: self.start_capture('auth'))
        self.btn_cap_auth.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        self.btn_cap_full = ttk.Button(btn_frame, text=global_i18n.get("btn_full_capture"), command=lambda: self.start_capture('full'))
        self.btn_cap_full.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        self.btn_stop_cap = ttk.Button(btn_frame, text=global_i18n.get("btn_stop_capture"), command=self.stop_capture, state=tk.DISABLED)
        self.btn_stop_cap.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        self.btn_lang = ttk.Button(btn_frame, text=global_i18n.get("btn_lang"), command=self.switch_language)
        self.btn_lang.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

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
        self.btn_stop_cap.config(text=global_i18n.get("btn_stop_capture"))
        self.btn_cap_auth.config(text=global_i18n.get("btn_auth_capture"))
        self.btn_cap_full.config(text=global_i18n.get("btn_full_capture"))
        self.btn_lang.config(text=global_i18n.get("btn_lang"))
        self.train_app.refresh_ui()
        self.frame_log.config(text=global_i18n.get("log_console"))

    def setup_log_area(self):
        self.frame_log = ttk.LabelFrame(self.root, text=global_i18n.get("log_console"), padding=5)
        self.frame_log.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.txt_log = tk.Text(self.frame_log, height=12, state=tk.DISABLED)
        self.txt_log.pack(fill=tk.BOTH, expand=True)

    def on_capture_result(self, uid, sign, enemies=None, orders=None):
        self.update_system_proxy(False)
        self.root.after(0, self.var_uid.set, uid)
        self.root.after(0, self.var_sign.set, sign)
        self.log(f"[SYS] Captured UID: {uid}")
        if enemies is not None:
            
            self.train_app.set_enemies_and_orders(enemies, orders)
            self.log(f"[SYS] Captured {len(enemies)} enemies and {len(orders)} orders.")
        
        self.proxy_capture = None
        self.root.after(0, self._enable_capture_buttons)

    def _enable_capture_buttons(self):
        self.btn_cap_auth.config(state=tk.NORMAL)
        self.btn_cap_full.config(state=tk.NORMAL)
        self.btn_stop_cap.config(state=tk.DISABLED)

    def _disable_capture_buttons(self):
        self.btn_cap_auth.config(state=tk.DISABLED)
        self.btn_cap_full.config(state=tk.DISABLED)
        self.btn_stop_cap.config(state=tk.NORMAL)

    def start_capture(self, mode):
        
        if self.proxy_capture:
            self.log("[SYS] Capture already running. Stop it first.")
            return
        try:
            self.proxy_capture = GFLCaptureProxy(
                8080, "yundoudou", self.on_capture_result, mode, log_callback=self.log
            )
            self.proxy_capture.start()
            self.update_system_proxy(True, 8080)
            self.log(f"[SYS] Capture proxy started (mode={mode}) on port 8080.")
            self._disable_capture_buttons()
        except Exception as e:
            self.proxy_capture = None
            self.log(f"[SYS] Error starting capture proxy: {e}")
            self._enable_capture_buttons()

    def stop_capture(self):
        if self.proxy_capture:
            self.proxy_capture.stop()
            self.proxy_capture = None
            self.update_system_proxy(False)
            self.log("[SYS] Capture proxy stopped.")
            self._enable_capture_buttons()
        else:
            self.log("[SYS] No capture proxy running.")

    def on_close(self):
        self.stop_capture()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = MainApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()