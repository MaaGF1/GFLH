# sandbox_gui.py
# GFLH - Sandbox GUI
# 仿照 GFLH-PR+ 结构：抓包监视 + 结果面板。

import os
import sys
import time
import json
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

# 打包后 sandbox.py 会跟着放进同一目录，运行源码时 src 的上一级是项目根
try:
    from sandbox import (
        parse_hidden_spots, summarize, detect_turn, window_of_turn,
        order_regions, order_spots, focus_regions, focus_high_count,
        SPOT_REGION, TEAM_TABLE, classify,
    )
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from sandbox import (
        parse_hidden_spots, summarize, detect_turn, window_of_turn,
        order_regions, order_spots, focus_regions, focus_high_count,
        SPOT_REGION, TEAM_TABLE, classify,
    )

from gflzirc import GFLProxy, set_windows_proxy, STATIC_KEY

APP_TITLE = "GFLH - Sandbox"
DEFAULT_PORT = 8081


def get_resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


class SandboxApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1080x880")

        self._setup_icon()

        self.proxy_instance = None
        self.active_proxy = False
        self.monitor_thread = None
        self.stop_monitor_flag = False
        self.is_closing = False

        self.var_port = tk.IntVar(value=DEFAULT_PORT)
        self.var_auto_stop = tk.BooleanVar(value=True)
        self.var_debug = tk.BooleanVar(value=False)

        self.latest_spots = []      # 最近一次解析结果
        self.latest_turn = None

        self.setup_ui()

    # ------------------------------------------------------------------ UI
    def _setup_icon(self):
        for icon_path in [
            get_resource_path("mk/icon.ico"),
            get_resource_path("../mk/icon.ico"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "mk", "icon.ico"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "mk", "icon.ico"),
        ]:
            if os.path.exists(icon_path):
                try:
                    self.root.iconbitmap(icon_path)
                    break
                except Exception:
                    pass

    def setup_ui(self):
        frame_ctrl = ttk.LabelFrame(self.root, text="1. 监视控制", padding=10)
        frame_ctrl.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(frame_ctrl, text="端口:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(frame_ctrl, textvariable=self.var_port, width=8).grid(
            row=0, column=1, sticky=tk.W, padx=5)

        self.btn_start = ttk.Button(frame_ctrl, text="开始监视", command=self.start_monitor)
        self.btn_start.grid(row=0, column=2, padx=10)
        self.btn_stop = ttk.Button(frame_ctrl, text="停止监视", command=self.stop_monitor,
                                   state=tk.DISABLED)
        self.btn_stop.grid(row=0, column=3, padx=5)

        self.lbl_status = ttk.Label(frame_ctrl, text="● 未监视", foreground="gray")
        self.lbl_status.grid(row=0, column=4, padx=15)

        self.lbl_turn = ttk.Label(frame_ctrl, text="回合: -", font=("", 10, "bold"))
        self.lbl_turn.grid(row=0, column=5, padx=15)

        frame_opts = ttk.LabelFrame(self.root, text="2. 选项", padding=10)
        frame_opts.pack(fill=tk.X, padx=10, pady=5)
        ttk.Checkbutton(frame_opts, text="监视到 7T 后自动停止",
                        variable=self.var_auto_stop).pack(anchor=tk.W, pady=2)
        ttk.Checkbutton(frame_opts, text="调试：打印原始信号",
                        variable=self.var_debug).pack(anchor=tk.W, pady=2)

        # 结果面板：顶部汇总 + 滚动明细表
        frame_res = ttk.LabelFrame(self.root, text="3. 隐藏点刷怪统计", padding=8)
        frame_res.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.lbl_summary = ttk.Label(frame_res, text="等待捕获…", justify=tk.LEFT)
        self.lbl_summary.pack(anchor=tk.W, pady=(0, 6))

        cols = ("spot", "region", "team", "power", "score", "tier", "comp")
        self.tree = ttk.Treeview(frame_res, columns=cols, show="headings", height=12)
        for cid, text, width in (
            ("spot", "隐藏点", 70),
            ("region", "区域", 105),
            ("team", "怪组", 75),
            ("power", "效能", 75),
            ("score", "分数", 65),
            ("tier", "档位", 45),
            ("comp", "配置", 380),
        ):
            self.tree.heading(cid, text=text)
            self.tree.column(cid, width=width, anchor=tk.W)
        vsb = ttk.Scrollbar(frame_res, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.tag_configure("高", foreground="#c0392b")
        self.tree.tag_configure("中", foreground="#b9770e")
        self.tree.tag_configure("低", foreground="#1e8449")

        # 日志
        frame_log = ttk.LabelFrame(self.root, text="4. 日志", padding=5)
        frame_log.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.txt_log = scrolledtext.ScrolledText(frame_log, height=8, state=tk.DISABLED,
                                                 font=("Consolas", 9))
        self.txt_log.pack(fill=tk.BOTH, expand=True)
        self.txt_log.tag_config("found", foreground="#c0392b")
        self.txt_log.tag_config("info")
        self.txt_log.tag_config("warn", foreground="#b9770e")

    # ------------------------------------------------------------------ 日志
    def log(self, msg, tag=None):
        try:
            if self.is_closing:
                return
            if self.root.winfo_exists():
                self.root.after(0, self._append_log, msg, tag)
        except (tk.TclError, RuntimeError):
            pass

    def _append_log(self, msg, tag=None):
        if self.is_closing:
            return
        try:
            if self.root.winfo_exists():
                self.txt_log.config(state=tk.NORMAL)
                self.txt_log.insert(tk.END, msg + "\n", tag or "")
                self.txt_log.see(tk.END)
                self.txt_log.config(state=tk.DISABLED)
        except (tk.TclError, RuntimeError):
            pass

    # ------------------------------------------------------------------ 结果渲染
    def render_result(self, data):
        spots = parse_hidden_spots(data)
        if not spots:
            return
        turn = detect_turn(data)
        counts, by_region = summarize(spots)
        focus, others = order_regions(by_region.keys(), turn)
        focus_high = focus_high_count(spots, turn)

        self.latest_spots = spots
        self.latest_turn = turn

        def _apply():
            if self.is_closing:
                return
            self.lbl_turn.config(text="回合: %s" % (turn if turn else "?"))
            # 汇总行：建议关注区域的高效能优先
            lines = ["高效能怪组: 建议关注区域 %d 个  |  全部 %d 个"
                     % (focus_high, counts["高"])]
            lines.append("中: %d  |  低: %d" % (counts["中"], counts["低"]))
            # 区域明细：只显示建议关注区域，按优先级顺序
            if focus:
                lines.append("建议关注区域:  " + "   ".join(
                    "%s(高%d/中%d/低%d)" % (r, by_region[r]["高"],
                                            by_region[r]["中"], by_region[r]["低"])
                    for r in focus))
            else:
                lines.append("本回合无明确的建议关注区域")
            self.lbl_summary.config(text="\n".join(lines))

            # 明细表：建议关注区域排在前面
            self.tree.delete(*self.tree.get_children())
            for s in order_spots(spots, turn):
                self.tree.insert("", tk.END, values=(
                    s["spot_id"], s["region"], s["team_id"],
                    s["power"] if s["power"] is not None else "?",
                    s["score"] if s.get("score") is not None else "?",
                    s["tier"], s["comp"]),
                    tags=(s["tier"],))

        try:
            self.root.after(0, _apply)
        except (tk.TclError, RuntimeError):
            pass

        self.log("捕获到隐藏点数据（回合 %s）：高效能 %d 个（建议关注区域 %d 个），"
                 "中 %d / 低 %d" %
                 (turn, counts["高"], focus_high, counts["中"], counts["低"]), "found")

    # ------------------------------------------------------------------ 回调
    def _traffic_callback(self, event_type, url, data):
        if self.is_closing:
            return
        if event_type.upper() != "S2C":
            return

        debug_mode = False
        auto_stop = False
        try:
            if not self.is_closing and self.root.winfo_exists():
                debug_mode = self.var_debug.get()
                auto_stop = self.var_auto_stop.get()
        except (tk.TclError, RuntimeError):
            return

        if debug_mode:
            self.log("探测到信号: %s" % url, "info")

        # 1T 在 startMission，2~7T 在 startTurn；两者都带 fairy_skill_return
        is_mission_packet = ("startMission" in url) or ("Mission_startTurn" in url) \
            or ("startTurn" in url)
        if not is_mission_packet:
            return

        if not isinstance(data, dict):
            return

        if debug_mode:
            self.log("收到 mission 包，解析隐藏点…", "info")

        self.render_result(data)

        if auto_stop and self.latest_turn and self.latest_turn >= 7:
            self.log("已监视到 7T，自动停止。", "info")
            self.stop_monitor_safe()

    # ------------------------------------------------------------------ 线程
    def monitor_worker(self):
        port = self.var_port.get()
        try:
            self.proxy_instance = GFLProxy(port, STATIC_KEY, self._traffic_callback)
            self.proxy_instance.start()
            set_windows_proxy(True, "127.0.0.1:%d" % port)
            self.active_proxy = True
            self.log("[*] 监视已启动，端口 %d，Windows 代理已设置" % port, "info")
            self.log("[*] 请进入游戏，进入/结束回合即可看到隐藏点刷怪统计", "info")

            while not self.stop_monitor_flag and not self.is_closing:
                time.sleep(0.5)
        except Exception as e:
            self.log("[!] 监视线程出错: %s" % e, "warn")
        finally:
            if self.proxy_instance:
                try:
                    self.proxy_instance.stop()
                except Exception:
                    pass
                self.proxy_instance = None
            if self.active_proxy:
                try:
                    set_windows_proxy(False)
                except Exception:
                    pass
                self.active_proxy = False
            if not self.is_closing:
                try:
                    if self.root.winfo_exists():
                        self.root.after(0, self._reset_ui)
                except (tk.TclError, RuntimeError):
                    pass
            else:
                self.monitor_thread = None

    def start_monitor(self):
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.log("已经在监视了", "warn")
            return
        try:
            port = self.var_port.get()
            if not (1024 <= port <= 65535):
                raise ValueError("端口范围 1024-65535")
        except Exception as e:
            messagebox.showerror("错误", "端口无效: %s" % e)
            return

        self.stop_monitor_flag = False
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.lbl_status.config(text="● 监视中", foreground="green")

        self.monitor_thread = threading.Thread(target=self.monitor_worker, daemon=True)
        self.monitor_thread.start()

    def stop_monitor_safe(self):
        try:
            if self.is_closing:
                return
            if self.root.winfo_exists():
                self.root.after(0, self.stop_monitor)
        except (tk.TclError, RuntimeError):
            pass

    def stop_monitor(self):
        if not self.monitor_thread or not self.monitor_thread.is_alive():
            self._reset_ui()
            return
        self.stop_monitor_flag = True
        self.log("[*] 停止监视中…", "info")

    def _reset_ui(self):
        if self.is_closing:
            return
        try:
            if self.root.winfo_exists():
                self.btn_start.config(state=tk.NORMAL)
                self.btn_stop.config(state=tk.DISABLED)
                self.lbl_status.config(text="● 监视结束", foreground="gray")
                self.monitor_thread = None
        except (tk.TclError, RuntimeError):
            pass

    def on_close(self):
        self.is_closing = True
        self.stop_monitor_flag = True
        if self.proxy_instance:
            try:
                self.proxy_instance.stop()
            except Exception:
                pass
            self.proxy_instance = None
        if self.active_proxy:
            try:
                set_windows_proxy(False)
            except Exception:
                pass
            self.active_proxy = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2.0)
        try:
            self.root.destroy()
        except tk.TclError:
            pass


if __name__ == "__main__":
    root = tk.Tk()
    app = SandboxApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
