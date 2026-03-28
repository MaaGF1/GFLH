import frida
import sys
import gzip
import os
import json
import time
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext
import shutil

# Configuration
OUTPUT_DIR = "traffic_dumps"
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

packet_counter = 1
latest_token = None

def save_json(content_obj, tag):
    """Helper to save JSON content to file"""
    global packet_counter
    timestamp = int(time.time())
    filename = f"{packet_counter:04d}_{tag}_{timestamp}.json"
    filepath = os.path.join(OUTPUT_DIR, filename)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(content_obj, f, indent=4, ensure_ascii=False)
        packet_counter += 1
    except Exception as e:
        print(f"[!] Error saving file: {e}")

def clean_traffic_dumps():
    """Delete all JSON files in traffic_dumps directory."""
    if os.path.exists(OUTPUT_DIR):
        for filename in os.listdir(OUTPUT_DIR):
            if filename.endswith(".json"):
                os.remove(os.path.join(OUTPUT_DIR, filename))
        print("[*] Cleaned up JSON files.")

class TokenGrabberGUI:
    def __init__(self, master):
        self.master = master
        master.title("GF1 Token 抓取工具")
        master.geometry("500x400")
        master.protocol("WM_DELETE_WINDOW", self.on_closing)

        # 状态
        self.running = False
        self.script = None
        self.session = None

        # 创建控件
        self.label = tk.Label(master, text="等待发球", fg="blue")
        self.label.pack(pady=10)

        self.token_var = tk.StringVar()
        self.token_entry = tk.Entry(master, textvariable=self.token_var, width=60, state='readonly')
        self.token_entry.pack(pady=10)

        self.copy_btn = tk.Button(master, text="复制 Token", command=self.copy_token, state=tk.DISABLED)
        self.copy_btn.pack(pady=5)

        self.log_text = scrolledtext.ScrolledText(master, height=10, width=70)
        self.log_text.pack(pady=10, fill=tk.BOTH, expand=True)

        self.status_label = tk.Label(master, text="未连接", fg="red")
        self.status_label.pack(pady=5)

        # 启动抓包线程
        self.start_capture()

    def log(self, message):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.master.update_idletasks()

    def on_message(self, message, data):
        if message['type'] == 'send':
            payload = message['payload']
            msg_id = payload.get('id')

            if msg_id == 'C2S':
                content = payload.get('content')
                self.log(f"[--> C2S] Captured Request: {len(content)} chars")
                try:
                    json_obj = json.loads(content)
                    # 保存 JSON 文件（仍保存，用于调试，但退出时会清理）
                    save_json(json_obj, "C2S")
                except Exception as e:
                    self.log(f"[!] C2S Parse Error: {e}")

            elif msg_id == 'LOG':
                log_content = payload.get('content')
                self.log(log_content)
                # 尝试提取 token
                if "Encode Key is:" in log_content:
                    token = log_content.split("Encode Key is:")[-1].strip()
                    self.token_var.set(token)
                    self.copy_btn.config(state=tk.NORMAL)
                    self.status_label.config(text="Token 已捕获", fg="green")
                    self.label.config(text="Token 已获取，可以复制使用", fg="green")
                    self.log(f"[*] Token 已捕获: {token}")

            elif msg_id == 'S2C':
                # 处理 S2C 数据（可选，不显示）
                if data:
                    self.log(f"[<-- S2C] Received Gzip Data: {len(data)} bytes")
                    try:
                        decompressed_data = gzip.decompress(data)
                        json_str = decompressed_data.decode('utf-8')
                        json_obj = json.loads(json_str)
                        save_json(json_obj, "S2C")
                    except Exception as e:
                        self.log(f"[!] S2C Decompression Error: {e}")
            else:
                # 其他消息
                self.log(f"[?] Unknown message: {payload}")

    def start_capture(self):
        """启动 Frida 抓包线程"""
        def capture_thread():
            process_name = "GrilsFrontLine.exe"
            self.log(f"[*] 正在附加到进程: {process_name} ...")
            try:
                session = frida.attach(process_name)
                self.session = session
            except Exception as e:
                self.log(f"[!] 附加失败: {e}")
                self.log("[!] 请确保游戏已运行。")
                self.status_label.config(text="附加失败", fg="red")
                return

            # 加载 JS 脚本
            if not os.path.exists("hook_dual.js"):
                self.log("[!] Error: hook_dual.js not found.")
                return

            with open("hook_dual.js", "r", encoding="utf-8") as f:
                script_code = f.read()

            script = session.create_script(script_code)
            script.on('message', self.on_message)
            script.load()
            self.script = script
            self.log("[*] 脚本已加载，正在监听网络数据...")
            self.status_label.config(text="监听中", fg="green")
            # 保持运行
            sys.stdin.read()  # 阻塞，但我们会在关闭时处理

        self.running = True
        self.thread = threading.Thread(target=capture_thread, daemon=True)
        self.thread.start()

    def copy_token(self):
        token = self.token_var.get()
        if token:
            self.master.clipboard_clear()
            self.master.clipboard_append(token)
            self.log("[*] Token 已复制到剪贴板")
        else:
            messagebox.showwarning("警告", "尚未捕获到 Token")

    def on_closing(self):
        """关闭窗口时停止抓包并清理文件"""
        self.log("[*] 正在停止抓包...")
        if self.script:
            try:
                self.script.unload()
            except:
                pass
        if self.session:
            try:
                self.session.detach()
            except:
                pass
        self.running = False
        # 清理 JSON 文件
        clean_traffic_dumps()
        self.log("[*] 已清理 JSON 文件")
        self.master.destroy()

def main():
    root = tk.Tk()
    app = TokenGrabberGUI(root)
    root.mainloop()

if __name__ == '__main__':
    main()
