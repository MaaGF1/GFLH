# friend_daily_gui.py
# GFLH - FriendPraise：每日好友互动 GUI
#   访问 / 点赞 / 载具访问 / 载具维护
#
# 由 GFLH-FriendPraise/FriendPraise.py（原控制台脚本）移植而来。
#
# 原则：原脚本流程本身可用，因此完全照搬，不做任何改动。
#       界面上只留三项 + 一个开始按钮：UID / Sign Key / 服务器 → 「开始点赞」。
#       UID 与 Sign Key 默认留空，由「自动捕获密钥」填入；不写入配置文件。
#
# 流程：捕获到 uid / sign 后
#         1) Friend/mallByType9          （空包）
#         2) Friend/teamAndPraisePrize   （user_id = 自己的 UID）
#         3) Friend/list                 （取好友列表）
#         4) 逐个好友：Friend/visit → Friend/praise → Vehicle/visit → Vehicle/maintain

import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from gflzirc import (
    GFLClient, GFLProxy, set_windows_proxy,
    SERVERS, STATIC_KEY, DEFAULT_SIGN,
)

# ==================== 硬编码配置（原脚本原样） ====================
SLEEP_INTERVAL = 0.01       # 每个请求之间的间隔
# ================================================================

# ==================== 账号配置（需要捕获/设定） ====================
USER_UID = ""
SIGN_KEY = ""
TARGET_USER_ID = 0
BASE_URL = SERVERS["M4A1"]
PROXY_PORT = 8080
# ================================================================

# ========== API 路径定义（原脚本原样） ==========
API_FRIEND_MALL_BY_TYPE9 = "Friend/mallByType9"
API_FRIEND_TEAM_AND_PRAISE_PRIZE = "Friend/teamAndPraisePrize"
API_FRIEND_LIST = "Friend/list"
API_FRIEND_VISIT = "Friend/visit"
API_FRIEND_PRAISE = "Friend/praise"
API_VEHICLE_VISIT = "Vehicle/visit"
API_VEHICLE_MAINTAIN = "Vehicle/maintain"

APP_TITLE = "GFLH - FriendPraise"
CONFIG_FILE = "friendpraise_gui_config.json"

# 统计变量（原脚本字段名保持一致）
stats = {
    "friends_total": 0,
    "visit_success": 0,
    "visit_fail": 0,
    "praise_success": 0,
    "praise_fail": 0,
    "vehicle_visit_success": 0,
    "vehicle_visit_fail": 0,
    "vehicle_maintain_success": 0,
    "vehicle_maintain_fail": 0,
    "start_time": None,
}

# 运行控制
STOP_FLAG = {"stop": False}
# 最近一次好友列表处理到的位置（仅用于界面进度显示）
PROGRESS = {"index": 0, "total": 0}


# ========== 日志出口 ==========
LOG_SINK = None


def log_line(msg):
    if LOG_SINK is not None:
        LOG_SINK(msg)
    else:
        print(msg)


def get_resource_path(relative_path):
    """兼容 PyInstaller 打包后的资源路径。"""
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


def server_items():
    return ["%s | %s" % (name, url) for name, url in SERVERS.items()]


def server_url_from_item(item):
    return item.split(" | ")[1].strip() if " | " in item else SERVERS.get(item.strip(), "")


def server_item_from_url(url):
    for name, base in SERVERS.items():
        if base.rstrip("/") == str(url).rstrip("/"):
            return "%s | %s" % (name, base)
    return ""


def set_account(uid, sign, target_user_id=None):
    """原脚本 on_traffic 的动作：写入 UID / SIGN，并由 UID 推出 TARGET_USER_ID。"""
    global USER_UID, SIGN_KEY, TARGET_USER_ID
    USER_UID = uid
    SIGN_KEY = sign
    if target_user_id is None:
        try:
            TARGET_USER_ID = int(uid)
        except (ValueError, TypeError):
            TARGET_USER_ID = 0
    else:
        TARGET_USER_ID = target_user_id


def check_step_error(resp: dict, step_name: str) -> bool:
    """原脚本同名函数（日志改为回调，其余一致）。"""
    if "error_local" in resp:
        log_line("[-] %s Local Error: %s" % (step_name, resp["error_local"]))
        return True
    if "error" in resp:
        log_line("[-] %s Server Error: %s" % (step_name, resp["error"]))
        return True
    return False


# ========== 各步骤操作（原脚本原样） ==========
def step_mall_by_type9(client: GFLClient) -> bool:
    """发送 Friend/mallByType9（空包）"""
    log_line("[*] [1/3] Sending Friend/mallByType9...")
    resp = client.send_request(API_FRIEND_MALL_BY_TYPE9, {})
    if check_step_error(resp, "mallByType9"):
        return False
    log_line("[+] mallByType9 done.")
    return True


def step_team_and_praise_prize(client: GFLClient) -> bool:
    """发送 Friend/teamAndPraisePrize，使用捕获的 UID"""
    payload = {"user_id": TARGET_USER_ID}
    log_line("[*] [2/3] Sending Friend/teamAndPraisePrize (user_id=%d)..." % TARGET_USER_ID)
    resp = client.send_request(API_FRIEND_TEAM_AND_PRAISE_PRIZE, payload)
    if check_step_error(resp, "teamAndPraisePrize"):
        return False
    log_line("[+] teamAndPraisePrize done.")
    return True


def get_friend_list(client: GFLClient) -> list:
    """发送 Friend/list 获取好友列表"""
    log_line("[*] [3/3] Fetching Friend/list...")
    resp = client.send_request(API_FRIEND_LIST, {})
    if check_step_error(resp, "friendList"):
        return []
    friends = resp.get("list", [])
    log_line("[+] Got %d friends." % len(friends))
    return friends


def do_friend_operations(client: GFLClient, friend: dict, index: int, total: int):
    """对单个好友依次执行：访问、点赞、载具访问、载具维护"""
    f_userid = int(friend.get("f_userid"))
    f_zoneid = int(friend.get("f_zoneid"))
    name = friend.get("name", "Unknown")
    log_line("\n--- [%d/%d] %s (ID: %d, Zone: %d) ---"
             % (index, total, name, f_userid, f_zoneid))

    # 1. Friend/visit
    resp = client.send_request(API_FRIEND_VISIT,
                              {"f_userid": f_userid, "f_zoneid": f_zoneid})
    if check_step_error(resp, "friendVisit"):
        stats["visit_fail"] += 1
    else:
        stats["visit_success"] += 1
        log_line("   [OK] Friend/visit OK")
    time.sleep(SLEEP_INTERVAL)

    if STOP_FLAG["stop"]:
        return

    # 2. Friend/praise
    resp = client.send_request(API_FRIEND_PRAISE,
                              {"f_userid": f_userid, "f_zoneid": f_zoneid})
    if check_step_error(resp, "friendPraise"):
        stats["praise_fail"] += 1
    else:
        stats["praise_success"] += 1
        log_line("   [OK] Friend/praise OK")
    time.sleep(SLEEP_INTERVAL)

    if STOP_FLAG["stop"]:
        return

    # 3. Vehicle/visit
    resp = client.send_request(API_VEHICLE_VISIT,
                              {"to_user_id": f_userid, "to_zone_id": f_zoneid})
    if check_step_error(resp, "vehicleVisit"):
        stats["vehicle_visit_fail"] += 1
    else:
        stats["vehicle_visit_success"] += 1
        log_line("   [OK] Vehicle/visit OK")
    time.sleep(SLEEP_INTERVAL)

    if STOP_FLAG["stop"]:
        return

    # 4. Vehicle/maintain
    resp = client.send_request(API_VEHICLE_MAINTAIN,
                              {"to_user_id": f_userid, "to_zone_id": f_zoneid})
    if check_step_error(resp, "vehicleMaintain"):
        stats["vehicle_maintain_fail"] += 1
    else:
        stats["vehicle_maintain_success"] += 1
        log_line("   [OK] Vehicle/maintain OK")
    time.sleep(SLEEP_INTERVAL)


# ========== 主流程（原脚本原样） ==========
def daily_worker(on_progress=None):
    """主工作线程：执行完整的每日好友互动"""
    if not USER_UID or not SIGN_KEY or TARGET_USER_ID == 0:
        log_line("[!] UID or SIGN not configured. Please run capture (-c) first!")
        return

    client = GFLClient(USER_UID, SIGN_KEY, BASE_URL)
    stats["start_time"] = time.time()

    log_line("\n=== Daily Friend Operations Started ===")
    log_line("  Sleep interval: %ss" % SLEEP_INTERVAL)
    log_line("  Target user_id: %d" % TARGET_USER_ID)
    log_line("-" * 60)

    # 步骤 1：mallByType9
    if STOP_FLAG["stop"]:
        return
    step_mall_by_type9(client)
    time.sleep(SLEEP_INTERVAL)

    # 步骤 2：teamAndPraisePrize
    if STOP_FLAG["stop"]:
        return
    step_team_and_praise_prize(client)
    time.sleep(SLEEP_INTERVAL)

    # 步骤 3：获取好友列表
    if STOP_FLAG["stop"]:
        return
    friends = get_friend_list(client)
    stats["friends_total"] = len(friends)

    if on_progress:
        on_progress()

    if not friends:
        log_line("[-] No friends found or failed to fetch list.")
        print_stats_to_log()
        return

    # 步骤 4：遍历好友执行操作
    for i, friend in enumerate(friends, 1):
        if STOP_FLAG["stop"]:
            log_line("\n[*] Stop signal received, aborting...")
            break
        PROGRESS["index"] = i
        PROGRESS["total"] = len(friends)
        try:
            do_friend_operations(client, friend, i, len(friends))
        except Exception as e:
            log_line("   [X] Error processing friend: %s" % e)
            continue

        # 每 10 个打印一次进度
        if i % 10 == 0:
            log_line("\n>>> Progress: %d/%d friends processed <<<" % (i, len(friends)))

        if on_progress:
            on_progress()

    print_stats_to_log()
    log_line("\n[*] Daily friend operations finished.")


def print_stats_to_log():
    """打印统计信息（原脚本 print_stats 的内容）"""
    elapsed = time.time() - stats["start_time"] if stats["start_time"] else 0
    log_line("\n" + "=" * 60)
    log_line("DAILY FRIEND OPERATIONS STATISTICS")
    log_line("-" * 60)
    log_line("  Friends total: %d" % stats["friends_total"])
    log_line("  Elapsed: %.1fs" % elapsed)
    log_line("\n  Friend/visit       : %d OK | %d FAIL"
             % (stats["visit_success"], stats["visit_fail"]))
    log_line("  Friend/praise      : %d OK | %d FAIL"
             % (stats["praise_success"], stats["praise_fail"]))
    log_line("  Vehicle/visit      : %d OK | %d FAIL"
             % (stats["vehicle_visit_success"], stats["vehicle_visit_fail"]))
    log_line("  Vehicle/maintain   : %d OK | %d FAIL"
             % (stats["vehicle_maintain_success"], stats["vehicle_maintain_fail"]))
    log_line("=" * 60)


def reset_stats():
    """原脚本 '-r' 命令里的统计重置"""
    stats["friends_total"] = 0
    stats["visit_success"] = 0
    stats["visit_fail"] = 0
    stats["praise_success"] = 0
    stats["praise_fail"] = 0
    stats["vehicle_visit_success"] = 0
    stats["vehicle_visit_fail"] = 0
    stats["vehicle_maintain_success"] = 0
    stats["vehicle_maintain_fail"] = 0
    stats["start_time"] = None
    PROGRESS["index"] = 0
    PROGRESS["total"] = 0


# ==========================================================================
# GUI
# ==========================================================================
LANG = {
    "zh": {
        "sec_account": "1. 账号",
        "uid": "UID:",
        "sign": "Sign Key:",
        "server": "服务器:",
        "target": "user_id:",
        "target_hint": "（由 UID 自动得出）",
        "lang": "语言:",
        "btn_capture": "自动捕获密钥",
        "btn_stop_capture": "停止捕获",
        "sec_run": "2. 操作",
        "btn_start": "开始点赞",
        "btn_stop": "停止",
        "sec_stats": "3. 统计",
        "friends": "好友总数:",
        "progress": "进度:",
        "visit": "Friend/visit:",
        "praise": "Friend/praise:",
        "vehicle_visit": "Vehicle/visit:",
        "vehicle_maintain": "Vehicle/maintain:",
        "log_title": "GFLH - FriendPraise 日志",
        "status_idle": "就绪。请先捕获密钥，再点「开始点赞」。",
        "status_capture": "捕获代理运行中：端口 {p}，系统代理已设置。",
        "status_running": "正在执行好友互动……",
        "status_stopping": "正在停止，等待当前请求结束……",
        "warn_no_key": "UID / Sign Key 不能为空。请先点「自动捕获密钥」。",
        "captured": "已捕获 UID / Sign Key。可以点「开始点赞」了。",
    },
    "en": {
        "sec_account": "1. Account",
        "uid": "UID:",
        "sign": "Sign Key:",
        "server": "Server:",
        "target": "user_id:",
        "target_hint": "(derived from UID)",
        "lang": "Language:",
        "btn_capture": "Capture Key",
        "btn_stop_capture": "Stop Capture",
        "sec_run": "2. Actions",
        "btn_start": "Start Praise",
        "btn_stop": "Stop",
        "sec_stats": "3. Stats",
        "friends": "Friends:",
        "progress": "Progress:",
        "visit": "Friend/visit:",
        "praise": "Friend/praise:",
        "vehicle_visit": "Vehicle/visit:",
        "vehicle_maintain": "Vehicle/maintain:",
        "log_title": "GFLH - FriendPraise Log",
        "status_idle": "Idle. Capture the key first, then press Start Praise.",
        "status_capture": "Capture proxy running on port {p}; Windows proxy is set.",
        "status_running": "Running friend operations...",
        "status_stopping": "Stopping, waiting for the current request...",
        "warn_no_key": "UID / Sign Key must not be empty. Press Capture Key first.",
        "captured": "UID / Sign Key captured. You can press Start Praise now.",
    },
}


class FriendPraiseApp:
    def __init__(self, root):
        global LOG_SINK

        self.root = root
        self.lang = "zh"
        self.text = LANG[self.lang]

        self.root.title(APP_TITLE)
        self.root.geometry("700x600")
        self.root.minsize(640, 540)
        self._set_icon()

        self.proxy_instance = None
        self.active_proxy = False
        self.worker_thread = None
        self.msg_queue = queue.Queue()
        self.stat_vars = {}

        # UID / Sign Key 默认留空，等捕获填入（不写配置文件）
        self.var_uid = tk.StringVar(value="")
        self.var_sign = tk.StringVar(value="")
        self.var_server = tk.StringVar(value=server_item_from_url(BASE_URL))
        self.var_target = tk.StringVar(value="0")
        self.var_lang = tk.StringVar(value="zh")

        self._build_ui()
        self._load_config()

        LOG_SINK = self._log_from_thread
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self._pump_queue)

    # ---------- 通用 ----------
    def _set_icon(self):
        icon_path = get_resource_path("mk/icon.ico")
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except tk.TclError:
                pass

    def _set_status(self, text):
        try:
            self.var_status.set(text)
        except (AttributeError, tk.TclError):
            pass

    def _set_btn(self, name, state):
        widget = getattr(self, name, None)
        if widget is not None:
            try:
                widget.config(state=state)
            except tk.TclError:
                pass

    def _log_from_thread(self, msg):
        """供 worker 线程使用的日志出口（原脚本这里是 print）。"""
        self.msg_queue.put(msg)

    # ---------- UI ----------
    def _build_ui(self):
        self._build_account_frame()
        self._build_run_frame()
        self._build_stats_frame()
        self._build_log_frame()

        self.var_status = tk.StringVar(value="")
        ttk.Label(self.root, textvariable=self.var_status, anchor=tk.W,
                  relief=tk.SUNKEN, padding=(6, 3)).pack(fill=tk.X, side=tk.BOTTOM)

    def _build_account_frame(self):
        f = ttk.LabelFrame(self.root, text=self.text["sec_account"], padding=10)
        f.pack(fill=tk.X, padx=10, pady=(10, 4))

        ttk.Label(f, text=self.text["uid"]).grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(f, textvariable=self.var_uid, width=34).grid(row=0, column=1,
                                                               padx=5, pady=2)

        ttk.Label(f, text=self.text["sign"]).grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Entry(f, textvariable=self.var_sign, width=34).grid(row=1, column=1,
                                                                padx=5, pady=2)

        ttk.Label(f, text=self.text["server"]).grid(row=2, column=0, sticky=tk.W, pady=2)
        self.cmb_server = ttk.Combobox(f, textvariable=self.var_server,
                                       values=server_items(), width=32, state="readonly")
        self.cmb_server.grid(row=2, column=1, padx=5, pady=2, sticky=tk.W)

        ttk.Label(f, text=self.text["target"]).grid(row=3, column=0, sticky=tk.W, pady=2)
        ttk.Label(f, textvariable=self.var_target).grid(row=3, column=1, sticky=tk.W, padx=5)

        ttk.Label(f, text=self.text["lang"]).grid(row=4, column=0, sticky=tk.W, pady=2)
        cmb_lang = ttk.Combobox(f, textvariable=self.var_lang, values=["zh", "en"],
                                width=6, state="readonly")
        cmb_lang.grid(row=4, column=1, padx=5, pady=2, sticky=tk.W)
        cmb_lang.bind("<<ComboboxSelected>>", self._on_lang_change)

        self.btn_cap = ttk.Button(f, text=self.text["btn_capture"], command=self.start_capture)
        self.btn_cap.grid(row=0, column=2, padx=6, pady=2)
        self.btn_stop_cap = ttk.Button(f, text=self.text["btn_stop_capture"],
                                       command=self.stop_capture, state=tk.DISABLED)
        self.btn_stop_cap.grid(row=1, column=2, padx=6, pady=2)

    def _build_run_frame(self):
        f = ttk.LabelFrame(self.root, text=self.text["sec_run"], padding=10)
        f.pack(fill=tk.X, padx=10, pady=4)

        self.btn_start = ttk.Button(f, text=self.text["btn_start"], command=self.start_praise,
                                    width=18)
        self.btn_start.pack(side=tk.LEFT)
        self.btn_stop = ttk.Button(f, text=self.text["btn_stop"], command=self.stop_praise,
                                   state=tk.DISABLED, width=10)
        self.btn_stop.pack(side=tk.LEFT, padx=8)

    def _build_stats_frame(self):
        f = ttk.LabelFrame(self.root, text=self.text["sec_stats"], padding=10)
        f.pack(fill=tk.X, padx=10, pady=4)

        for key in ("friends", "progress", "visit", "praise",
                    "vehicle_visit", "vehicle_maintain"):
            self.stat_vars[key] = tk.StringVar(value="0")

        ttk.Label(f, text=self.text["friends"]).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(f, textvariable=self.stat_vars["friends"], width=10,
                  anchor=tk.W).grid(row=0, column=1, sticky=tk.W)
        ttk.Label(f, text=self.text["progress"]).grid(row=0, column=2, sticky=tk.W,
                                                      padx=(24, 0))
        ttk.Label(f, textvariable=self.stat_vars["progress"], width=12,
                  anchor=tk.W).grid(row=0, column=3, sticky=tk.W)

        for row, (key, label_key) in enumerate((
                ("visit", "visit"),
                ("praise", "praise"),
                ("vehicle_visit", "vehicle_visit"),
                ("vehicle_maintain", "vehicle_maintain")), start=1):
            ttk.Label(f, text=self.text[label_key]).grid(row=row, column=0, sticky=tk.W)
            ttk.Label(f, textvariable=self.stat_vars[key], width=10,
                      anchor=tk.W).grid(row=row, column=1, sticky=tk.W)

    def _build_log_frame(self):
        f = ttk.LabelFrame(self.root, text=self.text["log_title"], padding=5)
        f.pack(fill=tk.BOTH, expand=True, padx=10, pady=(4, 10))

        self.txt_log = tk.Text(f, height=14, state=tk.DISABLED, wrap=tk.WORD)
        scroll = ttk.Scrollbar(f, orient=tk.VERTICAL, command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_log.pack(fill=tk.BOTH, expand=True)

    # ---------- 语言 ----------
    def _on_lang_change(self, _event=None):
        self.lang = self.var_lang.get()
        self.text = LANG[self.lang]
        messagebox.showinfo(APP_TITLE, "语言已切换，重新打开程序后完整生效。\n"
                                       "Language switched; reopen the app to apply it fully.")

    # ---------- 日志 ----------
    def _append_log(self, msg):
        line = "[%s] %s\n" % (time.strftime("%H:%M:%S"), msg)
        try:
            self.txt_log.config(state=tk.NORMAL)
            self.txt_log.insert(tk.END, line)
            # 限制日志长度，避免长时间运行占用内存
            if int(self.txt_log.index("end-1c").split(".")[0]) > 4000:
                self.txt_log.delete("1.0", "500.0")
            self.txt_log.see(tk.END)
            self.txt_log.config(state=tk.DISABLED)
        except tk.TclError:
            pass

    def _pump_queue(self):
        try:
            while True:
                item = self.msg_queue.get_nowait()
                if isinstance(item, tuple) and item and item[0] == "stats":
                    self._show_stats(item[1])
                    continue
                self._append_log(item)
        except queue.Empty:
            pass
        self.root.after(150, self._pump_queue)

    def _show_stats(self, snapshot):
        for key in ("friends", "visit", "praise", "vehicle_visit", "vehicle_maintain"):
            self.stat_vars[key].set(snapshot.get(key, "0"))
        self.stat_vars["progress"].set("%d/%d" % (snapshot.get("index", 0),
                                                  snapshot.get("total", 0)))

    # ---------- 配置持久化（只记服务器与语言，不记 UID / Sign） ----------
    def _config_path(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), CONFIG_FILE)

    def _load_config(self):
        path = self._config_path()
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                cfg = json.load(fh)
        except (OSError, ValueError):
            return

        if cfg.get("BASE_URL") in SERVERS.values():
            self.var_server.set(server_item_from_url(cfg["BASE_URL"]))
        if cfg.get("LANG") in LANG:
            self.var_lang.set(cfg["LANG"])
            self.lang = cfg["LANG"]
            self.text = LANG[self.lang]

    def _save_config(self):
        cfg = {
            "BASE_URL": server_url_from_item(self.var_server.get()),
            "LANG": self.var_lang.get(),
        }
        try:
            with open(self._config_path(), "w", encoding="utf-8") as fh:
                json.dump(cfg, fh, ensure_ascii=False, indent=2)
        except (OSError, TypeError, ValueError) as exc:
            self._append_log("[!] Failed to save config: %s" % exc)

    # ---------- 账号 ----------
    def _sync_account(self):
        """把界面上的 UID / Sign / 服务器写回模块级配置（等同原脚本的全局变量）。"""
        global BASE_URL
        uid = self.var_uid.get().strip()
        sign = self.var_sign.get().strip()
        set_account(uid, sign)
        BASE_URL = server_url_from_item(self.var_server.get()) or BASE_URL
        self.var_target.set(str(TARGET_USER_ID))
        return bool(uid and sign and BASE_URL)

    # ---------- 捕获 ----------
    def start_capture(self):
        if self.proxy_instance:
            self._append_log("[CAPTURE] Proxy already running.")
            return
        try:
            self.proxy_instance = GFLProxy(PROXY_PORT, STATIC_KEY, self._capture_callback)
            self.proxy_instance.start()
            set_windows_proxy(True, "127.0.0.1:%d" % PROXY_PORT)
            self.active_proxy = True
            self._set_btn("btn_cap", tk.DISABLED)
            self._set_btn("btn_stop_cap", tk.NORMAL)
            self._set_status(self.text["status_capture"].format(p=PROXY_PORT))
            self._append_log("[CAPTURE] Proxy started on port %d; Windows proxy SET."
                             % PROXY_PORT)
            self._append_log("[CAPTURE] Please log in to the game to capture UID and SIGN.")
        except Exception as exc:
            self._append_log("[!] Failed to start proxy: %s" % exc)
            self.proxy_instance = None

    def _capture_callback(self, event_type, url, data):
        if event_type != "SYS_KEY_UPGRADE" or not isinstance(data, dict):
            return
        uid = data.get("uid")
        sign = data.get("sign")
        if not uid or not sign:
            return

        def _apply():
            self.var_uid.set(str(uid))
            self.var_sign.set(str(sign))
            set_account(str(uid), str(sign))
            self.var_target.set(str(TARGET_USER_ID))
            self._append_log("[+] SUCCESS! Keys Auto-Configured:")
            self._append_log("    UID  : %s" % uid)
            self._append_log("    TARGET_USER_ID auto-set to: %d" % TARGET_USER_ID)
            self._append_log("[!] " + self.text["captured"])

        try:
            self.root.after(0, _apply)
        except tk.TclError:
            pass

    def stop_capture(self):
        if self.proxy_instance:
            self.proxy_instance.stop()
            self.proxy_instance = None
        if self.active_proxy:
            set_windows_proxy(False)
            self.active_proxy = False
        self._set_btn("btn_cap", tk.NORMAL)
        self._set_btn("btn_stop_cap", tk.DISABLED)
        self._set_status(self.text["status_idle"])
        self._append_log("[CAPTURE] Proxy stopped; Windows proxy restored.")

    # ---------- 点赞 ----------
    def start_praise(self):
        if self.worker_thread and self.worker_thread.is_alive():
            self._append_log("[WARN] Operations are already running.")
            return

        if not self._sync_account():
            messagebox.showwarning(APP_TITLE, self.text["warn_no_key"])
            return

        if SIGN_KEY == DEFAULT_SIGN:
            if not messagebox.askyesno(APP_TITLE,
                                       "Sign Key 仍是默认值，操作很可能全部失败。\n"
                                       "Sign Key is still the default value; the operations "
                                       "will most likely fail.\n\nContinue anyway?"):
                return

        # 原脚本 '-r' 的行为：先停代理，再重置统计，然后开线程
        if self.proxy_instance:
            self._append_log("[*] Stopping Proxy before starting operations...")
            self.stop_capture()
            time.sleep(1)

        reset_stats()
        self._show_stats({"friends": "0", "index": 0, "total": 0, "visit": "0",
                          "praise": "0", "vehicle_visit": "0", "vehicle_maintain": "0"})

        STOP_FLAG["stop"] = False
        self._set_btn("btn_start", tk.DISABLED)
        self._set_btn("btn_stop", tk.NORMAL)
        self._set_status(self.text["status_running"])

        self.worker_thread = threading.Thread(target=self._worker_entry, daemon=True)
        self.worker_thread.start()

    def _worker_entry(self):
        try:
            daily_worker(on_progress=self._report_progress)
        except Exception:
            import traceback
            traceback.print_exc()
            self.msg_queue.put("[!] worker crashed, see console for details")
        finally:
            self.root.after(0, self._reset_ui)

    def _report_progress(self):
        self.msg_queue.put(("stats", {
            "friends": str(stats["friends_total"]),
            "index": PROGRESS["index"],
            "total": PROGRESS["total"],
            "visit": "%d / %d" % (stats["visit_success"], stats["visit_fail"]),
            "praise": "%d / %d" % (stats["praise_success"], stats["praise_fail"]),
            "vehicle_visit": "%d / %d" % (stats["vehicle_visit_success"],
                                          stats["vehicle_visit_fail"]),
            "vehicle_maintain": "%d / %d" % (stats["vehicle_maintain_success"],
                                             stats["vehicle_maintain_fail"]),
        }))

    def stop_praise(self):
        STOP_FLAG["stop"] = True
        self._set_btn("btn_stop", tk.DISABLED)
        self._set_status(self.text["status_stopping"])
        self._append_log("[*] Stop flag set. Waiting for current request to finish...")

    def _reset_ui(self):
        self._set_btn("btn_start", tk.NORMAL)
        self._set_btn("btn_stop", tk.DISABLED)
        self._set_status(self.text["status_idle"])

    def on_close(self):
        if self.worker_thread and self.worker_thread.is_alive():
            if not messagebox.askyesno(APP_TITLE, "操作仍在运行，确定退出？\n"
                                                  "Operations are still running. Quit anyway?"):
                return
            STOP_FLAG["stop"] = True
            self.worker_thread.join(timeout=2)
        self.stop_capture()
        self._save_config()
        self.root.destroy()


def main():
    root = tk.Tk()
    FriendPraiseApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
