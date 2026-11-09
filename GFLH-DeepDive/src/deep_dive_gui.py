# -*- coding: utf-8 -*-
# deep_dive_gui.py
# GFLH - DeepDive（虚数迷宫+）刷开局 GUI
#
# 判定条件见 GFLH-DeepDive/README.md 与 README-Reroll.md：
#   1) 1T startMission 刷出左上补给点 9414（type 6）
#   2) 进入 2T 时 9438 / 9442 被占领、9447 与 9421 至少一点空闲、9446 无敌人
#
# 结构与 GFLH-NestReroll 保持一致：捕获密钥 → 自动读取阵容 → 循环重掷 → 成功后原地保留任务。

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

from gflzirc import GFLClient, GFLProxy, set_windows_proxy, SERVERS, STATIC_KEY

from deep_dive_core import (
    DeepDiveReroll, CaptureCollector, DEFAULT_RULES, MISSION_ID, START_SPOT,
    config_path, extract_roster, format_roster, load_config, normalize_roster,
    save_config, validate_roster,
)

APP_TITLE = "GFLH - DeepDive 刷开局"
PROXY_PORT = 8080
SERVER_ITEMS = ["%s | %s" % (name, url) for name, url in SERVERS.items()]


def get_resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


class DeepDiveApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("820x760")

        self._setup_icon()

        self.proxy = None
        self.active_proxy = False
        self.collector = CaptureCollector(self._on_capture_event)

        self.worker = None
        self.stop_event = threading.Event()
        self.is_closing = False
        self.dry_run = False
        self.run_options = {}
        self.auto_stop_pending = False
        self.stats = {"attempts": 0, "cond1": 0, "cond2": 0}

        self.config = load_config()
        self.rules = self.config.get("rules") or DEFAULT_RULES
        self.roster = normalize_roster(self.config.get("roster") or {})

        self.var_uid = tk.StringVar(value=str(self.config.get("uid") or ""))
        self.var_sign = tk.StringVar()
        self.var_server = tk.StringVar(value=self._saved_server())
        self.var_sangvis_team = tk.IntVar(value=self.roster["sangvis_team_id"])
        self.var_griffin_team = tk.IntVar(value=self.roster["griffin_team_id"])
        self.var_check_2t = tk.BooleanVar(value=bool(self.config.get("check_2t", True)))
        self.var_max_attempts = tk.IntVar(value=int(self.config.get("max_attempts", 0) or 0))
        self.var_delay = tk.DoubleVar(value=float(self.config.get("delay", 0.15) or 0.15))
        self.var_auto_stop_capture = tk.BooleanVar(value=True)

        self.setup_ui()
        self._refresh_roster_label()
        self.log("[*] 配置文件: %s" % config_path())
        self.log("[*] 关卡: %d，部署点: %d，铁血交战点: 9399，格里芬交战点: 9401" % (MISSION_ID, START_SPOT))

    # ------------------------------------------------------------ 基础
    def _saved_server(self):
        url = str(self.config.get("server") or "")
        for item in SERVER_ITEMS:
            if item.split("|", 1)[1].strip() == url:
                return item
        return SERVER_ITEMS[0] if SERVER_ITEMS else ""

    def _setup_icon(self):
        for icon_path in (
            get_resource_path("mk/icon.ico"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mk", "icon.ico"),
        ):
            if os.path.exists(icon_path):
                try:
                    self.root.iconbitmap(icon_path)
                    return
                except Exception:
                    pass

    # ------------------------------------------------------------ 界面
    def setup_ui(self):
        frame_user = ttk.LabelFrame(self.root, text="1. 用户配置", padding=10)
        frame_user.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(frame_user, text="服务器:").grid(row=0, column=0, sticky=tk.W, pady=2)
        combo = ttk.Combobox(frame_user, textvariable=self.var_server, values=SERVER_ITEMS,
                             width=52, state="readonly")
        combo.grid(row=0, column=1, padx=5, pady=2, sticky=tk.W)

        ttk.Label(frame_user, text="UID:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Entry(frame_user, textvariable=self.var_uid, width=30).grid(
            row=1, column=1, padx=5, pady=2, sticky=tk.W)

        ttk.Label(frame_user, text="Sign Key:").grid(row=2, column=0, sticky=tk.W, pady=2)
        ttk.Entry(frame_user, textvariable=self.var_sign, width=42).grid(
            row=2, column=1, padx=5, pady=2, sticky=tk.W)

        btn_box = ttk.Frame(frame_user)
        btn_box.grid(row=0, column=2, rowspan=3, padx=10)
        self.btn_capture = ttk.Button(btn_box, text="自动捕获密钥", command=self.start_capture)
        self.btn_capture.pack(fill=tk.X, pady=2)
        self.btn_stop_capture = ttk.Button(btn_box, text="停止捕获", command=self.stop_capture,
                                           state=tk.DISABLED)
        self.btn_stop_capture.pack(fill=tk.X, pady=2)
        ttk.Checkbutton(btn_box, text="捕获后自动停止", variable=self.var_auto_stop_capture).pack(
            anchor=tk.W, pady=2)

        frame_roster = ttk.LabelFrame(self.root, text="2. 阵容（1T 布下的 1 队铁血 + 2 队格里芬）", padding=10)
        frame_roster.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(frame_roster, text="铁血梯队:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Spinbox(frame_roster, from_=1, to=10, textvariable=self.var_sangvis_team,
                    width=6, command=self._on_team_changed).grid(
            row=0, column=1, sticky=tk.W, padx=5, pady=2)
        ttk.Label(frame_roster, text="格里芬梯队:").grid(row=0, column=2, sticky=tk.W,
                                                       padx=(20, 0), pady=2)
        ttk.Spinbox(frame_roster, from_=1, to=14, textvariable=self.var_griffin_team,
                    width=6, command=self._on_team_changed).grid(
            row=0, column=3, sticky=tk.W, padx=5, pady=2)
        ttk.Button(frame_roster, text="从捕获刷新阵容", command=self.refresh_roster).grid(
            row=0, column=4, padx=15)
        ttk.Button(frame_roster, text="重新加载配置", command=self.reload_config).grid(
            row=0, column=5, padx=5)

        self.lbl_roster = ttk.Label(frame_roster, text="", justify=tk.LEFT)
        self.lbl_roster.grid(row=1, column=0, columnspan=6, sticky=tk.W, pady=(6, 0))

        frame_opt = ttk.LabelFrame(self.root, text="3. 重掷设定", padding=10)
        frame_opt.pack(fill=tk.X, padx=10, pady=5)

        ttk.Checkbutton(frame_opt, text="同时校验 2T 开局（不勾选则只校验 1T 补给点）",
                        variable=self.var_check_2t).grid(row=0, column=0, columnspan=4,
                                                         sticky=tk.W, pady=2)

        ttk.Label(frame_opt, text="最大尝试次数（0 = 不限）:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Entry(frame_opt, textvariable=self.var_max_attempts, width=8).grid(
            row=1, column=1, sticky=tk.W, padx=5)

        ttk.Label(frame_opt, text="请求间隔 (秒):").grid(row=1, column=2, sticky=tk.W,
                                                       padx=(20, 0), pady=2)
        ttk.Entry(frame_opt, textvariable=self.var_delay, width=8).grid(
            row=1, column=3, sticky=tk.W, padx=5)

        btn_row = ttk.Frame(frame_opt)
        btn_row.grid(row=2, column=0, columnspan=4, pady=8)
        self.btn_start = ttk.Button(btn_row, text="开始重掷", command=self.start_reroll)
        self.btn_start.pack(side=tk.LEFT, padx=5)
        self.btn_stop = ttk.Button(btn_row, text="停止", command=self.stop_reroll, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=5)
        self.btn_once = ttk.Button(btn_row, text="单次试跑", command=self.start_single_test)
        self.btn_once.pack(side=tk.LEFT, padx=5)

        self.lbl_stats = ttk.Label(frame_opt, text="尝试 0 次 | 1T 通过 0 | 2T 通过 0")
        self.lbl_stats.grid(row=3, column=0, columnspan=4, sticky=tk.W)

        frame_log = ttk.LabelFrame(self.root, text="4. 日志", padding=5)
        frame_log.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.txt_log = scrolledtext.ScrolledText(frame_log, height=18, state=tk.DISABLED,
                                                 font=("Consolas", 9))
        self.txt_log.pack(fill=tk.BOTH, expand=True)
        self.txt_log.tag_config("ok", foreground="#1e8449")
        self.txt_log.tag_config("warn", foreground="#b9770e")
        self.txt_log.tag_config("err", foreground="#c0392b")

    # ------------------------------------------------------------ 日志 / 状态
    def log(self, msg, tag=None):
        if self.is_closing:
            return
        try:
            if self.root.winfo_exists():
                self.root.after(0, self._append_log, msg, tag)
        except (tk.TclError, RuntimeError):
            pass

    def _append_log(self, msg, tag=None):
        if self.is_closing:
            return
        try:
            if not self.root.winfo_exists():
                return
            self.txt_log.config(state=tk.NORMAL)
            self.txt_log.insert(tk.END, msg + "\n", tag or "")
            self.txt_log.see(tk.END)
            self.txt_log.config(state=tk.DISABLED)
        except (tk.TclError, RuntimeError):
            pass

    def _refresh_stats(self):
        self.lbl_stats.config(text="尝试 %d 次 | 1T 通过 %d | 2T 通过 %d" % (
            self.stats["attempts"], self.stats["cond1"], self.stats["cond2"]))

    def _refresh_roster_label(self):
        if self.roster.get("sangvis_units") or self.roster.get("guns"):
            text = format_roster(self.roster)
            problems = validate_roster(self.roster)
            if problems:
                text += "\n⚠ " + "；".join(problems)
            self.lbl_roster.config(text=text)
        else:
            self.lbl_roster.config(text="⚠ 尚未获取阵容：请先「自动捕获密钥」登录一次，或手动编辑配置文件后重新加载")

    def _base_url(self):
        value = self.var_server.get().strip()
        return value.split("|", 1)[1].strip() if "|" in value else value

    # ------------------------------------------------------------ 捕获
    def _on_capture_event(self, event):
        if self.is_closing:
            return
        try:
            if self.root.winfo_exists():
                self.root.after(0, self._apply_capture_event, event)
        except (tk.TclError, RuntimeError):
            pass

    def _apply_capture_event(self, event):
        if self.is_closing:
            return
        if event == "server":
            self._apply_server(self.collector.server_url)
        elif event in ("keys", "reset"):
            if self.collector.uid:
                self.var_uid.set(self.collector.uid)
            if self.collector.sign:
                self.var_sign.set(self.collector.sign)
            if event == "keys":
                self.log("[捕获] UID: %s / SIGN 已更新" % self.collector.uid, "ok")
        elif event == "device":
            self.roster["user_device"] = self.collector.user_device
            self._refresh_roster_label()
            self._persist()
            self.log("[捕获] 已获取设备指纹（micalog.user_device）", "ok")
        elif event == "index":
            self.log("[捕获] 收到 Index/index，正在解析阵容…", "ok")
            self._derive_roster(self.collector.index)

        if (self.collector.has_keys and self.collector.index
                and self.var_auto_stop_capture.get() and not self.auto_stop_pending):
            self.auto_stop_pending = True
            self.root.after(3000, self._auto_stop_capture)

    def _auto_stop_capture(self):
        self.auto_stop_pending = False
        if self.proxy and not (self.worker and self.worker.is_alive()):
            self.log("[捕获] 信息已齐备，自动停止捕获并恢复系统代理")
            self.stop_capture()

    def start_capture(self):
        if self.proxy:
            self.log("[捕获] 代理已在运行", "warn")
            return
        try:
            self.collector.reset()
            self.auto_stop_pending = False
            self.proxy = GFLProxy(PROXY_PORT, STATIC_KEY, self._on_traffic)
            self.proxy.start()
            set_windows_proxy(True, "127.0.0.1:%d" % PROXY_PORT)
            self.active_proxy = True
        except Exception as exc:
            self.log("[捕获] 启动失败: %r" % (exc,), "err")
            self.proxy = None
            return
        self.btn_capture.config(state=tk.DISABLED)
        self.btn_stop_capture.config(state=tk.NORMAL)
        self.log("[捕获] 代理已启动（端口 %d），系统代理已设置。" % PROXY_PORT)
        self.log("[捕获] 请重新登录游戏；如需自动获取设备指纹，可在捕获期间手动打一场战斗。")

    def _on_traffic(self, event_type, url, data):
        self.collector.handle(event_type, url, data)

    def _apply_server(self, base_url):
        """按捕获到的流量自动选中区服，避免把请求发到别的区服。"""
        if not base_url:
            return
        for item in SERVER_ITEMS:
            if item.split("|", 1)[1].strip() == base_url:
                if self.var_server.get() != item:
                    self.var_server.set(item)
                    self.log("[捕获] 已自动识别区服: %s" % item, "ok")
                    self._persist()
                return
        self.log("[捕获] 捕获到未收录的区服 URL: %s（可手动在服务器下拉框选择）" % base_url, "warn")

    def stop_capture(self):
        if self.proxy:
            try:
                self.proxy.stop()
            except Exception:
                pass
            self.proxy = None
        if self.active_proxy:
            try:
                set_windows_proxy(False)
            except Exception:
                pass
            self.active_proxy = False
            self.log("[捕获] 已停止捕获，系统代理已恢复")
        if not self.is_closing:
            try:
                self.btn_capture.config(state=tk.NORMAL)
                self.btn_stop_capture.config(state=tk.DISABLED)
            except tk.TclError:
                pass

    # ------------------------------------------------------------ 阵容
    def _derive_roster(self, index):
        if not isinstance(index, dict):
            return
        try:
            sangvis_team = int(self.var_sangvis_team.get())
            griffin_team = int(self.var_griffin_team.get())
        except (tk.TclError, ValueError):
            return
        try:
            roster = extract_roster(index, sangvis_team, griffin_team)
        except Exception as exc:
            self.log("[阵容] 解析失败: %r" % (exc,), "err")
            return

        if self.collector.user_device:
            roster["user_device"] = self.collector.user_device
        elif self.roster.get("user_device"):
            roster["user_device"] = self.roster["user_device"]

        self.roster = normalize_roster(roster)
        self.var_sangvis_team.set(self.roster["sangvis_team_id"])
        self.var_griffin_team.set(self.roster["griffin_team_id"])
        self._refresh_roster_label()
        self._persist()
        self.log("[阵容] %s" % format_roster(self.roster), "ok")
        problems = validate_roster(self.roster)
        if problems:
            self.log("[阵容] ⚠ " + "；".join(problems), "warn")

    def _on_team_changed(self):
        if isinstance(self.collector.index, dict):
            self._derive_roster(self.collector.index)

    def refresh_roster(self):
        if not isinstance(self.collector.index, dict):
            self.log("[阵容] 还没有捕获到 Index/index，无法刷新", "warn")
            return
        self._derive_roster(self.collector.index)

    def reload_config(self):
        self.config = load_config()
        self.roster = normalize_roster(self.config.get("roster") or {})
        self.rules = self.config.get("rules") or DEFAULT_RULES
        if self.config.get("uid"):
            self.var_uid.set(str(self.config["uid"]))
        self.var_server.set(self._saved_server())
        self.var_sangvis_team.set(self.roster["sangvis_team_id"])
        self.var_griffin_team.set(self.roster["griffin_team_id"])
        self.var_check_2t.set(bool(self.config.get("check_2t", True)))
        self.var_max_attempts.set(int(self.config.get("max_attempts", 0) or 0))
        self.var_delay.set(float(self.config.get("delay", 0.15) or 0.15))
        self._refresh_roster_label()
        self.log("[配置] 已重新加载 %s" % config_path())

    def _persist(self):
        data = {
            "uid": self.var_uid.get().strip(),
            "server": self._base_url(),
            "roster": self.roster,
            "rules": self.rules,
            "check_2t": bool(self.var_check_2t.get()),
            "max_attempts": int(self.var_max_attempts.get() or 0),
            "delay": float(self.var_delay.get() or 0.15),
        }
        if not save_config(data):
            self.log("[配置] 写入失败: %s" % config_path(), "warn")

    # ------------------------------------------------------------ 重掷
    def _build_engine(self, log):
        options = self.run_options
        client = GFLClient(options["uid"], options["sign"], options["base_url"])
        return DeepDiveReroll(
            client, self.roster, rules=self.rules,
            delay=options["delay"], log=log,
        )

    def _prepare_run(self) -> bool:
        if self.worker and self.worker.is_alive():
            self.log("[重掷] 已有任务在运行", "warn")
            return False
        if not self.var_uid.get().strip() or not self.var_sign.get().strip():
            messagebox.showerror("缺少密钥", "请先捕获或手动填写 UID / Sign Key。")
            return False
        problems = validate_roster(self.roster)
        if problems:
            messagebox.showerror("阵容不可用", "；".join(problems) +
                                 "\n\n请先「自动捕获密钥」登录一次，或编辑配置文件后重新加载。")
            return False
        self.stop_capture()
        self.stop_event.clear()
        self.stats = {"attempts": 0, "cond1": 0, "cond2": 0}
        self._refresh_stats()
        self._persist()
        # 在主线程读取 Tk 变量，线程里只用这份拷贝
        self.run_options = {
            "uid": self.var_uid.get().strip(),
            "sign": self.var_sign.get().strip(),
            "base_url": self._base_url(),
            "check_2t": bool(self.var_check_2t.get()),
            "max_attempts": int(self.var_max_attempts.get() or 0),
            "delay": float(self.var_delay.get() or 0.15),
        }
        self.btn_start.config(state=tk.DISABLED)
        self.btn_once.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.log("[重掷] 目标区服: %s" % self.run_options["base_url"])
        return True

    def start_reroll(self):
        if not self._prepare_run():
            return
        self.dry_run = False
        self.worker = threading.Thread(target=self._run_worker, args=(False,), daemon=True)
        self.worker.start()

    def start_single_test(self):
        if not self._prepare_run():
            return
        self.dry_run = True
        self.worker = threading.Thread(target=self._run_worker, args=(True,), daemon=True)
        self.worker.start()

    def _run_worker(self, dry_run):
        options = self.run_options
        try:
            engine = self._build_engine(self.log)
            self.log("[重掷] 清理可能残留的任务状态…")
            engine.abort_quietly()
            if dry_run:
                self.log("[重掷] 单次试跑（结束后自动中止，不保留任务）", "warn")
                result = engine.attempt(1, check_2t=options["check_2t"], dry_run=True)
                self._on_result(result)
            else:
                self.log("[重掷] 开始循环，勾选 2T 校验 = %s" % options["check_2t"])
                engine.run(
                    check_2t=options["check_2t"],
                    max_attempts=options["max_attempts"],
                    should_stop=self.stop_event.is_set,
                    on_result=self._on_result,
                )
        except Exception as exc:
            self.log("[重掷] 线程异常: %r" % (exc,), "err")
        finally:
            if not self.is_closing:
                try:
                    self.root.after(0, self._finish_run)
                except (tk.TclError, RuntimeError):
                    pass

    def _on_result(self, result):
        self.stats["attempts"] += 1
        if result.cond1:
            self.stats["cond1"] += 1
        if result.cond2:
            self.stats["cond2"] += 1

        def _apply():
            if self.is_closing:
                return
            try:
                self._refresh_stats()
                if result.ok and self.dry_run:
                    self.log("[单次试跑] 该局满足全部条件（已中止，不保留）", "ok")
                elif result.ok:
                    self.log("[结果] 第 %d 次尝试满足全部条件，任务已保留" % result.number, "ok")
                    self._notify_success(result)
                elif result.error:
                    self.log("[结果] 第 %d 次尝试出错：%s" % (result.number, result.error), "warn")
            except (tk.TclError, RuntimeError):
                pass

        try:
            self.root.after(0, _apply)
        except (tk.TclError, RuntimeError):
            pass

    def _notify_success(self, result):
        if result.cond2:
            detail = "2T 判定: %s" % result.detail
            where = "2T"
        else:
            detail = result.detail or "1T 补给点已刷出"
            where = "1T"
        message = (
            "第 %d 次尝试成功！\n\n%s\n\n"
            "任务已保留在 %s，回游戏即可继续。\n"
            "（脚本不会中止该局）" % (result.number, detail, where)
        )
        self.log("[+] " + message.replace("\n", " "), "ok")
        try:
            messagebox.showinfo("刷开局成功", message)
        except tk.TclError:
            pass

    def stop_reroll(self):
        self.stop_event.set()
        self.log("[重掷] 已请求停止，将在当前尝试结束后退出", "warn")

    def _finish_run(self):
        if self.is_closing:
            return
        try:
            self.btn_start.config(state=tk.NORMAL)
            self.btn_once.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.DISABLED)
        except tk.TclError:
            pass
        self.worker = None
        if self.stop_event.is_set():
            self.log("[重掷] 已停止")
        else:
            self.log("[重掷] 本轮结束")

    # ------------------------------------------------------------ 关闭
    def on_close(self):
        self.is_closing = True
        self.stop_event.set()
        self.stop_capture()
        if self.worker and self.worker.is_alive():
            self.worker.join(timeout=2.0)
        try:
            self.root.destroy()
        except tk.TclError:
            pass


def main():
    root = tk.Tk()
    app = DeepDiveApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
