import hashlib
import base64
import time
import requests
import json
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
from tkinter.simpledialog import askinteger

# ==========================================
# Basic
# ==========================================

def md5(text: str) -> str:
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def gf_authcode(string: str, operation: str = 'ENCODE', key: str = '', expiry: int = 3600) -> str:
    key_hash = md5(key)
    keya = md5(key_hash[0:16])
    keyb = md5(key_hash[16:32])
    
    cryptkey = keyb + md5(keyb)
    key_length = len(cryptkey)
    
    if operation == 'DECODE':
        try:
            b64_str = string + "=" * ((4 - len(string) % 4) % 4)
            string_bytes = base64.b64decode(b64_str)
        except Exception:
            return ""
    else:
        expiry_time = (expiry + int(time.time())) if expiry > 0 else 0
        header = f"{expiry_time:010d}"
        checksum = md5(string + keya)[0:16]
        payload = header + checksum + string
        string_bytes = payload.encode('utf-8')

    string_length = len(string_bytes)
    result = bytearray()
    box = list(range(256))
    rndkey = [ord(cryptkey[i % key_length]) for i in range(256)]
    
    j = 0
    for i in range(256):
        j = (j + box[i] + rndkey[i]) % 256
        box[i], box[j] = box[j], box[i]
        
    a = j = 0
    for i in range(string_length):
        a = (a + 1) % 256
        j = (j + box[a]) % 256
        box[a], box[j] = box[j], box[a]
        result.append(string_bytes[i] ^ box[(box[a] + box[j]) % 256])
        
    if operation == 'DECODE':
        try:
            res_str = bytes(result)
            ext_time = int(res_str[0:10])
            if (ext_time == 0 or ext_time - int(time.time()) > 0):
                ext_checksum = res_str[10:26].decode('utf-8')
                ext_text = res_str[26:].decode('utf-8')
                if ext_checksum == md5(ext_text + keya)[0:16]:
                    return ext_text
            return ""
        except:
            return ""
    else:
        return base64.b64encode(bytes(result)).decode('utf-8')

# ==========================================
# API Calls
# ==========================================

def add_target_practice_enemy(url: str, uid: str, sign_key: str, enemy_id: int, req_idx: int, order_id: int, log_callback=None):
    json_payload = f'{{"enemy_team_id":{enemy_id},"fight_type":0,"fight_coef":"","fight_environment_group":"","order_id":{order_id}}}'
    encrypted_payload = gf_authcode(json_payload, 'ENCODE', sign_key)
    timestamp = int(time.time())
    req_id = f"{timestamp}000{req_idx}"
    payload_data = {"uid": uid, "outdatacode": encrypted_payload, "req_id": req_id}
    headers = {
        "User-Agent": "UnityPlayer/2018.4.36f1 (UnityWebRequest/1.0, libcurl/7.52.0-DEV)",
        "X-Unity-Version": "2018.4.36f1"
    }
    if log_callback:
        log_callback(f"[*] Sending Request - Enemy ID: {enemy_id} | Order ID: {order_id} ...")
    try:
        response = requests.post(url, headers=headers, data=payload_data, timeout=10)
        if "1" in response.text:
            if log_callback:
                log_callback("[ SUCCESS ]")
        else:
            if log_callback:
                log_callback(f"[ FAIL ] Server returned: {response.text.strip()}")
    except Exception as e:
        if log_callback:
            log_callback(f"[-] Request Failed: {e}")

def delete_target_practice_enemy(url: str, uid: str, sign_key: str, enemy_id: int, req_idx: int, log_callback=None):
    """删除靶机，payload 不含 order_id（基于抓包）"""
    json_payload = f'{{"enemy_team_id":{enemy_id},"fight_type":0,"fight_coef":"","fight_environment_group":""}}'
    encrypted_payload = gf_authcode(json_payload, 'ENCODE', sign_key)
    timestamp = int(time.time())
    req_id = f"{timestamp}000{req_idx}"
    payload_data = {"uid": uid, "outdatacode": encrypted_payload, "req_id": req_id}
    headers = {
        "User-Agent": "UnityPlayer/2018.4.36f1 (UnityWebRequest/1.0, libcurl/7.52.0-DEV)",
        "X-Unity-Version": "2018.4.36f1"
    }
    if log_callback:
        log_callback(f"[*] Deleting Enemy ID: {enemy_id} ...")
    try:
        response = requests.post(url, headers=headers, data=payload_data, timeout=10)
        if "1" in response.text:
            if log_callback:
                log_callback("[ SUCCESS ]")
        else:
            if log_callback:
                log_callback(f"[ FAIL ] Server returned: {response.text.strip()}")
    except Exception as e:
        if log_callback:
            log_callback(f"[-] Request Failed: {e}")

def run_batch_injection(url: str, uid: str, sign_key: str, enemies: list, orders: list, log_callback=None):
    if len(enemies) != len(orders):
        if log_callback:
            log_callback("[!] Order list length mismatch. Using auto-increment sequence (1, 2, 3...).")
        orders = list(range(1, len(enemies) + 1))
    else:
        if log_callback:
            log_callback("[*] Using provided order IDs.")
    if log_callback:
        log_callback("[*] Starting Batch Injection...")
    for idx, (enemy, order) in enumerate(zip(enemies, orders)):
        add_target_practice_enemy(url, uid, sign_key, enemy, idx, order, log_callback)
        time.sleep(1)
    if log_callback:
        log_callback("[*] All done.")

def run_batch_deletion(url: str, uid: str, sign_key: str, enemies: list, log_callback=None):
    if not enemies:
        if log_callback:
            log_callback("[!] No enemies to delete.")
        return
    if log_callback:
        log_callback(f"[*] Starting Batch Deletion of {len(enemies)} enemies...")
    for idx, enemy in enumerate(enemies):
        delete_target_practice_enemy(url, uid, sign_key, enemy, idx, log_callback)
        time.sleep(1)
    if log_callback:
        log_callback("[*] Deletion completed.")

# ==========================================
# GUI Application
# ==========================================

class InjectionGUI:
    def __init__(self, master):
        self.master = master
        master.title("GF1靶机抓取工具")
        master.geometry("800x1000")
        
        # 预设服务器地址列表
        self.url_options = [
            "M4 | http://gfcn-game.gw.merge.sunborngame.com/index.php/1000/Targettrain/addCollect",
            "15 | http://gfcn-game.bili.merge.sunborngame.com/index.php/5000/Targettrain/addCollect",
            "SOP | http://gfcn-game.ios.merge.sunborngame.com/index.php/3000/Targettrain/addCollect",
            "RO | http://gfcn-game.ly.merge.sunborngame.com/index.php/4000/Targettrain/addCollect",
            "M16 | http://gfcn-game.tx.sunborngame.com/index.php/2000/Targettrain/addCollect"
        ]
        
        self.url_var = tk.StringVar(value=self.url_options[0])
        self.delete_url_var = tk.StringVar(value="")  
        self.uid_var = tk.StringVar(value="")
        self.sign_key_var = tk.StringVar(value="")  
        self.use_custom_orders = tk.BooleanVar(value=False)
        self.enemies = []
        self.orders = []
        
        self.create_widgets()
        self.update_delete_url()  # 初始化删除地址
        # 绑定下拉菜单变化事件
        self.url_var.trace('w', lambda *args: self.update_delete_url())
    
    def update_delete_url(self):
        """根据当前选择的添加 URL，自动生成删除 URL"""
        raw = self.url_var.get().strip()
        if "|" in raw:
            add_url = raw.split("|", 1)[1].strip()
        else:
            add_url = raw
        if "addCollect" in add_url:
            delete_url = add_url.replace("addCollect", "delCollect")
        else:
            delete_url = add_url  # 保持原样
        self.delete_url_var.set(delete_url)
    
    def create_widgets(self):
        main_frame = ttk.Frame(self.master, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # URL 下拉菜单
        url_frame = ttk.LabelFrame(main_frame, text="添加靶机接口地址", padding="5")
        url_frame.pack(fill=tk.X, pady=5)
        url_combo = ttk.Combobox(url_frame, textvariable=self.url_var, values=self.url_options, width=77)
        url_combo.pack(fill=tk.X, expand=True)
        url_combo['state'] = 'normal'
        
        # 删除接口地址（自动生成）
        delete_url_frame = ttk.LabelFrame(main_frame, text="删除靶机接口地址", padding="5")
        delete_url_frame.pack(fill=tk.X, pady=5)
        delete_url_entry = ttk.Entry(delete_url_frame, textvariable=self.delete_url_var, width=77)
        delete_url_entry.pack(fill=tk.X, expand=True)
        delete_url_entry['state'] = 'readonly'  # 只读，自动生成
        
        # UID and Sign Key
        cred_frame = ttk.LabelFrame(main_frame, text="认证信息", padding="5")
        cred_frame.pack(fill=tk.X, pady=5)
        ttk.Label(cred_frame, text="UID:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Entry(cred_frame, textvariable=self.uid_var, width=40).grid(row=0, column=1, padx=5, pady=2)
        ttk.Label(cred_frame, text="Token:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Entry(cred_frame, textvariable=self.sign_key_var, width=40).grid(row=1, column=1, padx=5, pady=2)
        
        # Enemies list
        enemies_frame = ttk.LabelFrame(main_frame, text="目标敌人ID列表 (最多35组)", padding="5")
        enemies_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        list_frame = ttk.Frame(enemies_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        self.enemies_listbox = tk.Listbox(list_frame, height=10)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.enemies_listbox.yview)
        self.enemies_listbox.configure(yscrollcommand=scrollbar.set)
        self.enemies_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        btn_frame = ttk.Frame(enemies_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="添加敌人", command=self.add_enemy).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="删除选中", command=self.delete_enemy).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="编辑选中", command=self.edit_enemy).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="清空列表", command=self.clear_enemies).pack(side=tk.LEFT, padx=5)
        
        # Custom orders checkbox
        orders_frame = ttk.LabelFrame(main_frame, text="靶场ID设置", padding="5")
        orders_frame.pack(fill=tk.X, pady=5)
        ttk.Checkbutton(orders_frame, text="使用自定义靶场ID列表", variable=self.use_custom_orders,
                        command=self.toggle_orders).pack(anchor=tk.W)
        
        self.orders_frame = ttk.Frame(orders_frame)
        self.orders_frame.pack(fill=tk.X, pady=5)
        self.orders_listbox = tk.Listbox(self.orders_frame, height=5)
        orders_scroll = ttk.Scrollbar(self.orders_frame, orient=tk.VERTICAL, command=self.orders_listbox.yview)
        self.orders_listbox.configure(yscrollcommand=orders_scroll.set)
        self.orders_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        orders_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.orders_btn_frame = ttk.Frame(orders_frame)
        self.orders_btn_frame.pack(fill=tk.X, pady=5)
        self.btn_add_order = ttk.Button(self.orders_btn_frame, text="添加靶场ID", command=self.add_order, state=tk.DISABLED)
        self.btn_add_order.pack(side=tk.LEFT, padx=5)
        self.btn_del_order = ttk.Button(self.orders_btn_frame, text="删除选中", command=self.delete_order, state=tk.DISABLED)
        self.btn_del_order.pack(side=tk.LEFT, padx=5)
        self.btn_edit_order = ttk.Button(self.orders_btn_frame, text="编辑选中", command=self.edit_order, state=tk.DISABLED)
        self.btn_edit_order.pack(side=tk.LEFT, padx=5)
        self.btn_clear_orders = ttk.Button(self.orders_btn_frame, text="清空靶场ID", command=self.clear_orders, state=tk.DISABLED)
        self.btn_clear_orders.pack(side=tk.LEFT, padx=5)
        
        # 一键清空按钮
        delete_frame = ttk.LabelFrame(main_frame, text="清空操作", padding="5")
        delete_frame.pack(fill=tk.X, pady=5)
        ttk.Button(delete_frame, text="一键清空游戏内当前列表中的靶机", command=self.start_deletion).pack(side=tk.LEFT, padx=5)
        
        # Log area
        log_frame = ttk.LabelFrame(main_frame, text="日志", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, state=tk.NORMAL)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Control buttons
        ctrl_frame = ttk.Frame(main_frame)
        ctrl_frame.pack(fill=tk.X, pady=5)
        ttk.Button(ctrl_frame, text="靶机，启动", command=self.start_injection).pack(side=tk.LEFT, padx=5)
        ttk.Button(ctrl_frame, text="保存配置", command=self.save_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(ctrl_frame, text="加载配置", command=self.load_config_dialog).pack(side=tk.LEFT, padx=5)
        ttk.Button(ctrl_frame, text="清空日志", command=self.clear_log).pack(side=tk.LEFT, padx=5)
    
    def toggle_orders(self):
        state = tk.NORMAL if self.use_custom_orders.get() else tk.DISABLED
        self.orders_listbox.config(state=state)
        self.btn_add_order.config(state=state)
        self.btn_del_order.config(state=state)
        self.btn_edit_order.config(state=state)
        self.btn_clear_orders.config(state=state)
        if not self.use_custom_orders.get():
            self.orders.clear()
            self.update_orders_listbox()
    
    # --- Enemies management ---
    def add_enemy(self):
        enemy_id = askinteger("添加敌人", "请输入敌人ID:", parent=self.master)
        if enemy_id is not None:
            if len(self.enemies) >= 35:
                messagebox.showwarning("警告", "最多只能添加35组敌人")
                return
            self.enemies.append(enemy_id)
            self.update_enemies_listbox()
    
    def delete_enemy(self):
        selection = self.enemies_listbox.curselection()
        if selection:
            idx = selection[0]
            del self.enemies[idx]
            self.update_enemies_listbox()
    
    def edit_enemy(self):
        selection = self.enemies_listbox.curselection()
        if selection:
            idx = selection[0]
            old_val = self.enemies[idx]
            new_val = askinteger("编辑敌人", "请输入新的敌人ID:", initialvalue=old_val, parent=self.master)
            if new_val is not None:
                self.enemies[idx] = new_val
                self.update_enemies_listbox()
    
    def clear_enemies(self):
        self.enemies.clear()
        self.update_enemies_listbox()
    
    def update_enemies_listbox(self):
        self.enemies_listbox.delete(0, tk.END)
        for enemy in self.enemies:
            self.enemies_listbox.insert(tk.END, str(enemy))
    
    # --- Orders management ---
    def add_order(self):
        if not self.use_custom_orders.get():
            return
        order_id = askinteger("添加靶场ID", "请输入靶场ID:", parent=self.master)
        if order_id is not None:
            if len(self.orders) >= 35:
                messagebox.showwarning("警告", "最多只能添加35组靶场ID")
                return
            self.orders.append(order_id)
            self.update_orders_listbox()
    
    def delete_order(self):
        if not self.use_custom_orders.get():
            return
        selection = self.orders_listbox.curselection()
        if selection:
            idx = selection[0]
            del self.orders[idx]
            self.update_orders_listbox()
    
    def edit_order(self):
        if not self.use_custom_orders.get():
            return
        selection = self.orders_listbox.curselection()
        if selection:
            idx = selection[0]
            old_val = self.orders[idx]
            new_val = askinteger("编辑靶场ID", "请输入新的靶场ID:", initialvalue=old_val, parent=self.master)
            if new_val is not None:
                self.orders[idx] = new_val
                self.update_orders_listbox()
    
    def clear_orders(self):
        if not self.use_custom_orders.get():
            return
        self.orders.clear()
        self.update_orders_listbox()
    
    def update_orders_listbox(self):
        self.orders_listbox.delete(0, tk.END)
        for order in self.orders:
            self.orders_listbox.insert(tk.END, str(order))
    
    # --- Logging ---
    def log(self, message):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.master.update_idletasks()
    
    def clear_log(self):
        self.log_text.delete(1.0, tk.END)
    
    # --- Injection execution ---
    def start_injection(self):
        # 提取纯 URL
        url_raw = self.url_var.get().strip()
        if "|" in url_raw:
            url = url_raw.split("|", 1)[1].strip()
        else:
            url = url_raw

        if not url:
            messagebox.showerror("错误", "URL不能为空")
            return
        uid = self.uid_var.get().strip()
        if not uid:
            messagebox.showerror("错误", "UID不能为空")
            return
        sign_key = self.sign_key_var.get().strip()
        if not sign_key:
            messagebox.showerror("错误", "Token不能为空")
            return
        if not self.enemies:
            messagebox.showerror("错误", "请至少添加一个敌人ID")
            return
        
        if self.use_custom_orders.get():
            if len(self.orders) != len(self.enemies):
                messagebox.showwarning("警告", f"自定义靶场ID数量({len(self.orders)})与敌人ID数量({len(self.enemies)})不匹配，将自动使用1,2,3...")
                orders = list(range(1, len(self.enemies) + 1))
            else:
                orders = self.orders
        else:
            orders = list(range(1, len(self.enemies) + 1))
        
        # 禁用启动按钮
        start_btn = self.find_button_by_text("靶机，启动")
        if start_btn:
            start_btn.config(state=tk.DISABLED)
        
        def worker():
            try:
                run_batch_injection(url, uid, sign_key, self.enemies, orders, self.log)
            except Exception as e:
                self.log(f"发生错误: {str(e)}")
            finally:
                self.master.after(0, lambda: start_btn.config(state=tk.NORMAL) if start_btn else None)
        
        threading.Thread(target=worker, daemon=True).start()
    
    # --- Deletion execution ---
    def start_deletion(self):
        if not self.enemies:
            messagebox.showwarning("警告", "当前敌人列表为空，请先添加要删除的敌人ID")
            return

        # 获取删除接口 URL
        url = self.delete_url_var.get().strip()
        if not url:
            messagebox.showerror("错误", "删除接口地址不能为空")
            return
        uid = self.uid_var.get().strip()
        if not uid:
            messagebox.showerror("错误", "UID不能为空")
            return
        sign_key = self.sign_key_var.get().strip()
        if not sign_key:
            messagebox.showerror("错误", "Token不能为空")
            return

        if not messagebox.askyesno("确认", f"即将删除当前列表中的 {len(self.enemies)} 个靶机，是否继续？"):
            return

        delete_btn = self.find_button_by_text("一键清空游戏内当前列表中的靶机")
        if delete_btn:
            delete_btn.config(state=tk.DISABLED)

        def worker():
            try:
                run_batch_deletion(url, uid, sign_key, self.enemies, self.log)
            except Exception as e:
                self.log(f"发生错误: {str(e)}")
            finally:
                self.master.after(0, lambda: delete_btn.config(state=tk.NORMAL) if delete_btn else None)

        threading.Thread(target=worker, daemon=True).start()
    
    def find_button_by_text(self, text):
        for child in self.master.winfo_children():
            if isinstance(child, ttk.Frame):
                for sub in child.winfo_children():
                    if isinstance(sub, ttk.Button) and sub['text'] == text:
                        return sub
        return None
    
    # --- Config persistence ---
    def save_config(self):
        config = {
            "url": self.url_var.get(),
            "uid": self.uid_var.get(),
            "enemies": self.enemies,
            "use_custom_orders": self.use_custom_orders.get(),
            "orders": self.orders if self.use_custom_orders.get() else []
        }
        filename = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json")])
        if filename:
            with open(filename, 'w') as f:
                json.dump(config, f, indent=2)
            self.log(f"配置已保存到 {filename}")
    
    def load_config(self, filename=None):
        if not filename:
            filename = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
            if not filename:
                return
        try:
            with open(filename, 'r') as f:
                config = json.load(f)
            self.url_var.set(config.get("url", ""))
            self.uid_var.set(config.get("uid", ""))
            self.enemies = config.get("enemies", [])
            self.update_enemies_listbox()
            self.use_custom_orders.set(config.get("use_custom_orders", False))
            if self.use_custom_orders.get():
                self.orders = config.get("orders", [])
                self.update_orders_listbox()
                self.toggle_orders()
            else:
                self.orders.clear()
                self.update_orders_listbox()
                self.toggle_orders()
            self.log(f"配置已从 {filename} 加载")
        except Exception as e:
            messagebox.showerror("错误", f"加载配置失败: {str(e)}")
    
    def load_config_dialog(self):
        self.load_config()

# ==========================================
# Main Entry Point
# ==========================================

def main():
    root = tk.Tk()
    app = InjectionGUI(root)
    root.mainloop()

if __name__ == '__main__':
    main()
