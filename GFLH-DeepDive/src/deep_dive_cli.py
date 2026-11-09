# -*- coding: utf-8 -*-
# deep_dive_cli.py
# GFLH - DeepDive（虚数迷宫+）刷开局 控制台版
#
# 与 GUI 共用 deep_dive_core：
#   -c 捕获密钥（并自动解析阵容写入配置）
#   -r 开始重掷（按配置决定是否校验 2T）
#   -1 只校验 1T 补给点
#   -s 单次试跑（结果不保留）
#   -q 停止
#   -E 退出
#
# 用法：python src/deep_dive_cli.py

import sys
import threading
import time

from gflzirc import GFLClient, GFLProxy, set_windows_proxy, STATIC_KEY

from deep_dive_core import (
    CaptureCollector, DEFAULT_RULES, DeepDiveReroll,
    config_path, extract_roster, format_roster, load_config, normalize_roster,
    save_config, validate_roster,
)

PROXY_PORT = 8080

STATE = {
    "uid": "",
    "sign": "",
    "base_url": "",
    "roster": {},
    "rules": dict(DEFAULT_RULES),
    "check_2t": True,
    "max_attempts": 0,
    "delay": 0.15,
    "proxy": None,
    "worker": None,
    "stop_flag": False,
}


def load_state():
    config = load_config()
    STATE["uid"] = str(config.get("uid") or "")
    STATE["base_url"] = str(config.get("server") or "")
    STATE["roster"] = normalize_roster(config.get("roster") or {})
    STATE["rules"] = config.get("rules") or dict(DEFAULT_RULES)
    STATE["check_2t"] = bool(config.get("check_2t", True))
    STATE["max_attempts"] = int(config.get("max_attempts", 0) or 0)
    STATE["delay"] = float(config.get("delay", 0.15) or 0.15)


def persist_state():
    save_config({
        "uid": STATE["uid"],
        "server": STATE["base_url"],
        "roster": STATE["roster"],
        "rules": STATE["rules"],
        "check_2t": STATE["check_2t"],
        "max_attempts": STATE["max_attempts"],
        "delay": STATE["delay"],
    })


def print_state():
    print("  服务器   : %s" % (STATE["base_url"] or "<未设置>"))
    print("  UID      : %s" % (STATE["uid"] or "<未设置>"))
    print("  SIGN     : %s" % ("已捕获" if STATE["sign"] else "<未捕获>"))
    print("  阵容     : %s" % format_roster(STATE["roster"]))
    print("  校验 2T  : %s" % ("是" if STATE["check_2t"] else "否（只校验 1T）"))
    print("  配置路径 : %s" % config_path())
    problems = validate_roster(STATE["roster"])
    if problems:
        print("  [!] 阵容问题: %s" % "；".join(problems))


def stop_proxy():
    proxy = STATE.get("proxy")
    if proxy:
        try:
            proxy.stop()
        except Exception:
            pass
        STATE["proxy"] = None
        set_windows_proxy(False)


def do_capture():
    if STATE["proxy"]:
        print("[!] 代理已在运行")
        return

    collector = CaptureCollector()
    proxy = GFLProxy(PROXY_PORT, STATIC_KEY, collector.handle)
    STATE["proxy"] = proxy
    proxy.start()
    set_windows_proxy(True, "127.0.0.1:%d" % PROXY_PORT)
    print("[*] 代理已启动（端口 %d），系统代理已设置。" % PROXY_PORT)
    print("[*] 请重新登录游戏；如需设备指纹，可在捕获期间手动打一场战斗。")
    print("[*] 捕获完成后会自动停止；按 Ctrl+C 可提前结束。")

    try:
        waited = 0
        while not (collector.has_keys and collector.index):
            time.sleep(0.5)
            waited += 1
            if collector.has_keys and not STATE["sign"]:
                STATE["uid"] = collector.uid
                STATE["sign"] = collector.sign
                print("[+] UID: %s / SIGN 已捕获" % collector.uid)
            if waited % 40 == 0:
                print("[*] 仍在等待…（UID/SIGN=%s，Index=%s）按 Ctrl+C 结束" % (
                    "已捕获" if collector.has_keys else "未捕获",
                    "已捕获" if collector.index else "未捕获"))
        STATE["uid"] = collector.uid
        STATE["sign"] = collector.sign
    except KeyboardInterrupt:
        print("\n[!] 捕获被中断")
    finally:
        stop_proxy()

    if not (collector.uid and collector.sign):
        print("[-] 未捕获到 UID / SIGN")
        return

    if isinstance(collector.index, dict):
        try:
            roster = extract_roster(
                collector.index,
                int(STATE["roster"].get("sangvis_team_id") or 1),
                int(STATE["roster"].get("griffin_team_id") or 2),
            )
        except Exception as exc:
            print("[-] 阵容解析失败: %r" % (exc,))
        else:
            if collector.user_device:
                roster["user_device"] = collector.user_device
            elif STATE["roster"].get("user_device"):
                roster["user_device"] = STATE["roster"]["user_device"]
            STATE["roster"] = normalize_roster(roster)
            print("[+] 阵容: %s" % format_roster(STATE["roster"]))
    else:
        print("[!] 未捕获到 Index/index，阵容需要手动写入配置")

    if collector.server_url:
        STATE["base_url"] = collector.server_url
        print("[+] 区服: %s" % STATE["base_url"])
    elif not STATE["base_url"]:
        STATE["base_url"] = "http://gfcn-game.ly.merge.sunborngame.com/index.php/4000"
        print("[!] 未识别到区服，暂用 RO635（可用配置文件 server 字段修改）")
    persist_state()
    print("[+] 配置已保存: %s" % config_path())


def _run_worker(mode):
    problems = validate_roster(STATE["roster"])
    if problems:
        print("[-] 阵容不可用: %s" % "；".join(problems))
        return
    if not STATE["sign"]:
        print("[-] 未捕获 SIGN，请先执行 -c")
        return

    client = GFLClient(STATE["uid"], STATE["sign"], STATE["base_url"])
    engine = DeepDiveReroll(client, STATE["roster"], rules=STATE["rules"],
                            delay=STATE["delay"], log=print)
    print("[*] 清理可能残留的任务状态…")
    engine.abort_quietly()

    if mode == "single":
        print("[*] 单次试跑（结束后自动中止）")
        engine.attempt(1, check_2t=STATE["check_2t"], dry_run=True)
        return

    print("[*] 开始重掷（校验 2T = %s）" % STATE["check_2t"])
    engine.run(
        check_2t=STATE["check_2t"],
        max_attempts=STATE["max_attempts"],
        should_stop=lambda: STATE["stop_flag"],
    )


def start_worker(mode):
    worker = STATE.get("worker")
    if worker and worker.is_alive():
        print("[!] 已有任务在运行")
        return
    STATE["stop_flag"] = False
    STATE["worker"] = threading.Thread(target=_run_worker, args=(mode,), daemon=True)
    STATE["worker"].start()


def print_menu():
    print("\n================= GFLH DeepDive 刷开局 =================")
    print(" -c : 捕获密钥（自动解析阵容）")
    print(" -r : 开始重掷（按配置校验 1T / 2T）")
    print(" -1 : 只校验 1T 补给点后重掷")
    print(" -s : 单次试跑（结果不保留）")
    print(" -q : 停止重掷")
    print(" -i : 显示当前配置")
    print(" -E : 退出")
    print("=======================================================")
    print_state()


def main():
    load_state()
    print_menu()
    while True:
        try:
            cmd = input("DeepDive> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("")
            cmd = "-E"
        if not cmd:
            continue
        prefix = cmd.split()[0]

        if prefix == "-c":
            do_capture()
        elif prefix in ("-r", "-1"):
            STATE["check_2t"] = (prefix == "-r")
            persist_state()
            start_worker("reroll")
        elif prefix == "-s":
            start_worker("single")
        elif prefix == "-q":
            STATE["stop_flag"] = True
            print("[*] 将在当前尝试结束后停止")
        elif prefix == "-i":
            print_state()
        elif prefix == "-E":
            stop_proxy()
            STATE["stop_flag"] = True
            worker = STATE.get("worker")
            if worker and worker.is_alive():
                worker.join(timeout=3.0)
            print("[*] 已退出，系统代理已恢复")
            sys.exit(0)
        else:
            print("[!] 未知指令: %s" % cmd)


if __name__ == "__main__":
    main()
