# src/target_train/train_gui.py

import threading
import time
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from gflzirc import GFLClient
from utils import global_i18n
from include.constants import API_TARGET_TRAIN_ADD, API_TARGET_TRAIN_DEL

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
        self.lbl_enemies.grid(row=0, column=0, sticky=tk.NW, pady=2)
        self.txt_enemies = tk.Text(self.frame, width=50, height=6, wrap=tk.WORD)
        self.txt_enemies.grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)

        
        self.lbl_orders = ttk.Label(self.frame, text=global_i18n.get("order_ids"))
        self.lbl_orders.grid(row=1, column=0, sticky=tk.NW, pady=2)
        self.txt_orders = tk.Text(self.frame, width=50, height=6, wrap=tk.WORD)
        self.txt_orders.grid(row=1, column=1, sticky=tk.W, padx=5, pady=2)

        
        btn_frame = ttk.Frame(self.frame)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=10)

        self.btn_inject = ttk.Button(btn_frame, text=global_i18n.get("btn_inject"), command=self.run_injection)
        self.btn_inject.pack(side=tk.LEFT, padx=5)

        self.btn_clear_all = ttk.Button(btn_frame, text=global_i18n.get("btn_clear_all"), command=self.clear_all_targets)
        self.btn_clear_all.pack(side=tk.LEFT, padx=5)

        self.btn_import = ttk.Button(btn_frame, text=global_i18n.get("btn_import_file"), command=self.import_from_file)
        self.btn_import.pack(side=tk.LEFT, padx=5)

    def refresh_ui(self):
        self.frame.config(text=global_i18n.get("train_group"))
        self.lbl_enemies.config(text=global_i18n.get("enemy_ids"))
        self.lbl_orders.config(text=global_i18n.get("order_ids"))
        self.btn_inject.config(text=global_i18n.get("btn_inject"))
        self.btn_clear_all.config(text=global_i18n.get("btn_clear_all"))
        self.btn_import.config(text=global_i18n.get("btn_import_file"))

    def get_enemies_and_orders_from_text(self):
        
        enemies_text = self.txt_enemies.get("1.0", tk.END).strip()
        orders_text = self.txt_orders.get("1.0", tk.END).strip()
        
        def parse_ids(text):
            if not text:
                return []
            
            parts = [p.strip() for p in text.split(',') if p.strip()]
            ids = []
            for p in parts:
                try:
                    ids.append(str(int(p)))   
                except ValueError:
                    self.log(f"[TRAIN] Warning: Invalid ID format: {p}")
            return ids
            

        enemies = parse_ids(enemies_text)
        orders = parse_ids(orders_text)
        return enemies, orders

    def set_enemies_and_orders(self, enemies, orders):
        self.txt_enemies.delete("1.0", tk.END)
        self.txt_orders.delete("1.0", tk.END)
        self.txt_enemies.insert("1.0", ", ".join(enemies))
        self.txt_orders.insert("1.0", ", ".join(orders))
        self.log(f"[TRAIN] Auto-filled {len(enemies)} enemies, {len(orders)} orders.")

    def import_from_file(self):
        filepath = filedialog.askopenfilename(
            title=global_i18n.get("btn_import_file"),
            filetypes=[("JSON files", "*.json"), ("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if not filepath:
            return
        try:
            if filepath.endswith('.json'):
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                enemies = []
                orders = []
                if isinstance(data, list):
                    for item in data:
                        e = item.get("enemy_id") or item.get("enemy_team_id")
                        o = item.get("order_id")
                        if e is not None and o is not None:
                            enemies.append(str(e))
                            orders.append(str(o))
                elif isinstance(data, dict):
                    if "enemies" in data and "orders" in data:
                        enemies = [str(x) for x in data["enemies"]]
                        orders = [str(x) for x in data["orders"]]
                if enemies:
                    self.set_enemies_and_orders(enemies, orders)
                else:
                    self.log("[TRAIN] No valid enemy/order pairs found in JSON.")
            else:  
                enemies = []
                orders = []
                with open(filepath, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        parts = line.split(',')
                        if len(parts) >= 2:
                            enemies.append(parts[0].strip())
                            orders.append(parts[1].strip())
                if enemies:
                    self.set_enemies_and_orders(enemies, orders)
                else:
                    self.log("[TRAIN] No valid rows found in CSV.")
        except Exception as e:
            self.log(f"[TRAIN] Import failed: {e}")

    def clear_all_targets(self):
        enemies, orders = self.get_enemies_and_orders_from_text()
        if not enemies:
            self.log("[TRAIN] No enemies to clear.")
            return
        if not messagebox.askyesno(global_i18n.get("clear_all_confirm"), global_i18n.get("clear_all_confirm")):
            return

        cfg = self.get_config()
        if not cfg['uid'] or not cfg['sign']:
            self.log("[TRAIN] Error: Missing UID or SIGN!")
            return
        server_str = cfg.get('server', '')
        if " | " in server_str:
            base_url = server_str.split(" | ")[1].strip()
        else:
            base_url = server_str.strip()
        if not base_url:
            self.log("[TRAIN] Error: Server URL is empty.")
            return

        def worker():
            self.log(f"[TRAIN] Clearing {len(enemies)} targets...")
            client = GFLClient(cfg['uid'], cfg['sign'], base_url)
            success_count = 0
            for e_id in enemies:
                payload = {
                    "enemy_team_id": int(e_id),
                    "fight_type": 0,
                    "fight_coef": "",
                    "fight_environment_group": ""
                }
                try:
                    res = client.send_request(API_TARGET_TRAIN_DEL, payload)
                    if res.get("success", False) or "success" in str(res).lower():
                        success_count += 1
                        self.log(f"[TRAIN] Deleted enemy {e_id}")
                    else:
                        self.log(f"[TRAIN] Failed to delete {e_id}: {res}")
                    time.sleep(0.5)
                except Exception as e:
                    self.log(f"[TRAIN] Error deleting {e_id}: {e}")
            self.log(f"[TRAIN] Clear finished. Success: {success_count}/{len(enemies)}")
            self.txt_enemies.delete("1.0", tk.END)
            self.txt_orders.delete("1.0", tk.END)

        threading.Thread(target=worker, daemon=True).start()

    def run_injection(self):
        cfg = self.get_config()
        if not cfg['uid'] or not cfg['sign']:
            self.log("[TRAIN] Error: Missing UID or SIGN!")
            return

        enemies, orders = self.get_enemies_and_orders_from_text()
        if not enemies:
            self.log("[TRAIN] Error: Enemy list is empty.")
            return

        server_str = cfg.get('server', '')
        if " | " in server_str:
            base_url = server_str.split(" | ")[1].strip()
        else:
            base_url = server_str.strip()

        if not base_url:
            self.log("[TRAIN] Error: Server URL is empty.")
            return

        def worker():
            self.log("[TRAIN] Worker started...")
            client = GFLClient(cfg['uid'], cfg['sign'], base_url)
            
            for idx, e_id in enumerate(enemies):
                o_id = orders[idx] if idx < len(orders) else str(idx + 1)
                payload = {
                    "enemy_team_id": int(e_id),
                    "fight_type": 0,
                    "fight_coef": "",
                    "fight_environment_group": "",
                    "order_id": int(o_id)
                }
                
                try:
                    res = client.send_request(API_TARGET_TRAIN_ADD, payload)
                    self.log(f"[TRAIN] Sent ID:{e_id} -> {res.get('success', 'Fail')}")
                except Exception as e:
                    self.log(f"[TRAIN] Request Failed for ID:{e_id} -> {e}")
                
                time.sleep(1)
                
            self.log("[TRAIN] Finished injection.")

        threading.Thread(target=worker, daemon=True).start()