# src/target_train/train_gui.py

import threading
import time
import tkinter as tk
from tkinter import ttk
from gflzirc import GFLClient
from utils import global_i18n
from include.constants import API_TARGET_TRAIN_ADD

class TargetTrainApp:
    def __init__(self, parent, get_config_callback, log_callback):
        self.parent = parent
        self.get_config = get_config_callback
        self.log = log_callback
        self.setup_ui()

    def setup_ui(self):
        self.frame = ttk.LabelFrame(self.parent, text=global_i18n.get("train_group"), padding=10)
        self.frame.pack(fill=tk.X, padx=10, pady=5)

        self.lbl_enemies = ttk.Label(self.frame, text=global_i18n.get("enemy_ids"))
        self.lbl_enemies.grid(row=0, column=0, sticky=tk.W, pady=2)
        
        self.var_enemies = tk.StringVar(value="6519263, 6519225, 6519223")
        ttk.Entry(self.frame, textvariable=self.var_enemies, width=40).grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)

        self.lbl_orders = ttk.Label(self.frame, text=global_i18n.get("order_ids"))
        self.lbl_orders.grid(row=1, column=0, sticky=tk.W, pady=2)
        
        self.var_orders = tk.StringVar(value="1, 2, 3")
        ttk.Entry(self.frame, textvariable=self.var_orders, width=40).grid(row=1, column=1, sticky=tk.W, padx=5, pady=2)

        self.btn_inject = ttk.Button(self.frame, text=global_i18n.get("btn_inject"), command=self.run_injection)
        self.btn_inject.grid(row=2, column=0, columnspan=2, pady=10)

    def refresh_ui(self):
        self.frame.config(text=global_i18n.get("train_group"))
        self.lbl_enemies.config(text=global_i18n.get("enemy_ids"))
        self.lbl_orders.config(text=global_i18n.get("order_ids"))
        self.btn_inject.config(text=global_i18n.get("btn_inject"))

    def run_injection(self):
        cfg = self.get_config()
        if not cfg['uid'] or not cfg['sign']:
            self.log("[TRAIN] Missing UID or SIGN!")
            return

        enemies = [int(x.strip()) for x in self.var_enemies.get().split(",") if x.strip()]
        orders = [int(x.strip()) for x in self.var_orders.get().split(",") if x.strip()]

        def worker():
            self.log("[TRAIN] Worker started...")
            
            # Using only the base URL from the config
            base_url = cfg['server'].split(" | ")[1].strip()
            client = GFLClient(cfg['uid'], cfg['sign'], base_url)
            
            for idx, e_id in enumerate(enemies):
                o_id = orders[idx] if idx < len(orders) else (idx + 1)
                payload = {
                    "enemy_team_id": e_id,
                    "fight_type": 0, "fight_coef": "", "fight_environment_group": "",
                    "order_id": o_id
                }
                
                # Using the imported API endpoint
                res = client.send_request(API_TARGET_TRAIN_ADD, payload)
                self.log(f"[TRAIN] Sent ID:{e_id} -> {res.get('success', 'Fail')}")
                time.sleep(1)
            self.log("[TRAIN] Finished injection.")

        threading.Thread(target=worker, daemon=True).start()