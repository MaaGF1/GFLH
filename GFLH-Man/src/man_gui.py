
import os
import sys
import time
import queue
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

APP_TITLE = "GFLH - 科比模拟器"
APP_VERSION = "0.4.0"
DEFAULT_PROCESS = "GrilsFrontLine.exe"


def build_stamp():

    try:
        p = sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__)
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(p)))
    except Exception:
        return "?"


def get_resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def _import_core():
    try:
        from man_core import Controller
        return Controller
    except ImportError:
        for p in (os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"),
                  os.path.join(get_resource_path("tools"))):
            p = os.path.abspath(p)
            if p not in sys.path:
                sys.path.insert(0, p)
        from man_core import Controller
        return Controller


class ManApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("760x560")
        self.root.minsize(680, 480)
        self._setup_icon()

        self.controller = None
        self.msgq = queue.Queue()
        self.is_closing = False

        self.var_process = tk.StringVar(value=DEFAULT_PROCESS)
        self.var_status = tk.StringVar(value="状态：未起飞")

        self.setup_ui()
        self.log("GFLH-Man v%s · 直升机构建 %s · 进程 %s"
                 % (APP_VERSION, build_stamp(), sys.executable if getattr(sys, "frozen", False) else "源码运行"))
        self.root.protocol("WM_DELETE_WINDOW", self.on_exit)
        self.root.after(100, self._pump)

    # ------------------------------------------------------------------ UI
    def _setup_icon(self):
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ico_cands = [get_resource_path("mk/icon.ico"), os.path.join(base, "mk", "icon.ico")]
        png_cands = [get_resource_path("mk/icon_256.png"), os.path.join(base, "mk", "icon_256.png")]

        for path in ico_cands:
            try:
                if os.path.exists(path):
                    self.root.iconbitmap(path)     # 任务栏 + 标题栏
                    break
            except Exception:
                pass
        # 有些 Windows 主题下 iconbitmap 不生效，PNG 再补一次
        for path in png_cands:
            try:
                if os.path.exists(path):
                    self._icon_img = tk.PhotoImage(file=path)
                    self.root.iconphoto(True, self._icon_img)
                    break
            except Exception:
                pass

    def setup_ui(self):
        pad = {"padx": 8, "pady": 6}

        top = ttk.Frame(self.root)
        top.pack(fill="x", **pad)

        ttk.Label(top, text="进程名").pack(side="left")
        self.entry_process = ttk.Entry(top, textvariable=self.var_process, width=28)
        self.entry_process.pack(side="left", padx=(6, 16))

        self.btn_start = ttk.Button(top, text="起飞", width=10, command=self.on_start)
        self.btn_start.pack(side="left", padx=4)
        self.btn_stop = ttk.Button(top, text="停止", width=10, command=self.on_stop, state="disabled")
        self.btn_stop.pack(side="left", padx=4)
        self.btn_exit = ttk.Button(top, text="退出", width=10, command=self.on_exit)
        self.btn_exit.pack(side="left", padx=4)

        status = ttk.Frame(self.root)
        status.pack(fill="x", **pad)
        ttk.Label(status, textvariable=self.var_status).pack(side="left")

        hint = ttk.Label(
            self.root,
            text="启动游戏后点击起飞，之后的所有战斗默认在空难状态下进行。",
            foreground="#666666",
            wraplength=720,
            justify="left",
        )
        hint.pack(fill="x", padx=8)

        self.log_box = scrolledtext.ScrolledText(self.root, height=22, wrap="word", state="disabled")
        self.log_box.pack(fill="both", expand=True, padx=8, pady=(4, 8))

    # ------------------------------------------------------------------ log
    def log(self, msg):
        self.msgq.put(msg)

    def _pump(self):
        try:
            while True:
                msg = self.msgq.get_nowait()
                self.log_box.configure(state="normal")
                self.log_box.insert("end", str(msg) + "\n")
                self.log_box.see("end")
                self.log_box.configure(state="disabled")
        except queue.Empty:
            pass

        self._refresh_state()
        if not self.is_closing:
            self.root.after(100, self._pump)

    def _refresh_state(self):
        running = bool(self.controller and self.controller.running)
        if running:
            self.var_status.set("状态：科比坠机中%s" % (
                "（对象 %s）" % self.controller.objects
                if self.controller.objects is not None else ""))
        elif self.controller is not None and self.controller.last_error:
            self.var_status.set("状态：已坠毁（%s）" % self.controller.last_error)
        elif self.controller is not None:
            self.var_status.set("状态：未起飞")

        self.btn_start.configure(state="disabled" if running else "normal")
        self.btn_stop.configure(state="normal" if running else "disabled")
        self.entry_process.configure(state="disabled" if running else "normal")

    # ------------------------------------------------------------------ actions
    def on_start(self):
        if self.controller and self.controller.running:
            return
        Controller = _import_core()
        process = self.var_process.get().strip() or DEFAULT_PROCESS
        self.controller = Controller(process=process, log=self.log)
        self.log("=== 开始：%s ===" % process)
        self.controller.start_async()

    def on_stop(self):
        if self.controller and self.controller.running:
            self.log("=== 降落 ===")
            self.controller.stop()
        self.var_status.set("状态：未起飞")

    def on_exit(self):
        if self.is_closing:
            return
        self.is_closing = True
        try:
            if self.controller and self.controller.running:
                self.controller.stop()
        except Exception:
            pass
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except Exception:
        pass
    ManApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
