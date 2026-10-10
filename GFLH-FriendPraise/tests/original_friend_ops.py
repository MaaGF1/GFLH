# friend_daily.py
# 每日好友互动：访问、点赞、载具访问、载具维护

import sys
import time
import json
import threading
from gflzirc import (
    GFLClient, GFLProxy, set_windows_proxy,
    SERVERS, STATIC_KEY, DEFAULT_SIGN,
)

# ==================== 硬编码配置 ====================
SLEEP_INTERVAL = 0.01       # 每个请求之间的间隔
# ===================================================

# ========== API 路径定义 ==========
API_FRIEND_MALL_BY_TYPE9 = "Friend/mallByType9"
API_FRIEND_TEAM_AND_PRAISE_PRIZE = "Friend/teamAndPraisePrize"
API_FRIEND_LIST = "Friend/list"
API_FRIEND_VISIT = "Friend/visit"
API_FRIEND_PRAISE = "Friend/praise"
API_VEHICLE_VISIT = "Vehicle/visit"
API_VEHICLE_MAINTAIN = "Vehicle/maintain"

# ========== 全局变量 ==========
USER_UID = "_InputYourID_"
SIGN_KEY = DEFAULT_SIGN
TARGET_USER_ID = 0          
BASE_URL = SERVERS["AR15"]
PROXY_PORT = 8081

proxy_instance = None
stop_flag = False
loop_thread = None

# 统计变量
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

def on_traffic(event_type: str, url: str, data: dict):
    """自动捕获 UID 和 SIGN，并同步 TARGET_USER_ID"""
    global USER_UID, SIGN_KEY, TARGET_USER_ID
    if event_type == "SYS_KEY_UPGRADE":
        USER_UID = data.get("uid")
        SIGN_KEY = data.get("sign")
        try:
            TARGET_USER_ID = int(USER_UID)
        except (ValueError, TypeError):
            TARGET_USER_ID = 0
        print(f"\n[+] SUCCESS! Keys Auto-Configured:")
        print(f"    UID  : {USER_UID}")
        print(f"    SIGN : {SIGN_KEY}")
        print(f"    TARGET_USER_ID auto-set to: {TARGET_USER_ID}")
        print("\n[!] Please type '-r' to run daily friend operations.")

def check_step_error(resp: dict, step_name: str) -> bool:
    if "error_local" in resp:
        print(f"[-] {step_name} Local Error: {resp['error_local']}")
        return True
    if "error" in resp:
        print(f"[-] {step_name} Server Error: {resp['error']}")
        return True
    return False

# ========== 各步骤操作 ==========
def step_mall_by_type9(client: GFLClient) -> bool:
    """发送 Friend/mallByType9（空包）"""
    print("[*] [1/3] Sending Friend/mallByType9...")
    resp = client.send_request(API_FRIEND_MALL_BY_TYPE9, {})
    if check_step_error(resp, "mallByType9"):
        return False
    print("[+] mallByType9 done.")
    return True

def step_team_and_praise_prize(client: GFLClient) -> bool:
    """发送 Friend/teamAndPraisePrize，使用捕获的 UID"""
    payload = {"user_id": TARGET_USER_ID}
    print(f"[*] [2/3] Sending Friend/teamAndPraisePrize (user_id={TARGET_USER_ID})...")
    resp = client.send_request(API_FRIEND_TEAM_AND_PRAISE_PRIZE, payload)
    if check_step_error(resp, "teamAndPraisePrize"):
        return False
    print("[+] teamAndPraisePrize done.")
    return True

def get_friend_list(client: GFLClient) -> list:
    """发送 Friend/list 获取好友列表"""
    print("[*] [3/3] Fetching Friend/list...")
    resp = client.send_request(API_FRIEND_LIST, {})
    if check_step_error(resp, "friendList"):
        return []
    friends = resp.get("list", [])
    print(f"[+] Got {len(friends)} friends.")
    return friends

def do_friend_operations(client: GFLClient, friend: dict, index: int, total: int):
    """对单个好友依次执行：访问、点赞、载具访问、载具维护"""
    f_userid = int(friend.get("f_userid"))
    f_zoneid = int(friend.get("f_zoneid"))
    name = friend.get("name", "Unknown")
    print(f"\n--- [{index}/{total}] {name} (ID: {f_userid}, Zone: {f_zoneid}) ---")

    # 1. Friend/visit
    resp = client.send_request(API_FRIEND_VISIT, {"f_userid": f_userid, "f_zoneid": f_zoneid})
    if check_step_error(resp, "friendVisit"):
        stats["visit_fail"] += 1
    else:
        stats["visit_success"] += 1
        print(f"   ✅ Friend/visit OK")
    time.sleep(SLEEP_INTERVAL)

    if stop_flag:
        return

    # 2. Friend/praise
    resp = client.send_request(API_FRIEND_PRAISE, {"f_userid": f_userid, "f_zoneid": f_zoneid})
    if check_step_error(resp, "friendPraise"):
        stats["praise_fail"] += 1
    else:
        stats["praise_success"] += 1
        print(f"   ✅ Friend/praise OK")
    time.sleep(SLEEP_INTERVAL)

    if stop_flag:
        return

    # 3. Vehicle/visit
    resp = client.send_request(API_VEHICLE_VISIT, {"to_user_id": f_userid, "to_zone_id": f_zoneid})
    if check_step_error(resp, "vehicleVisit"):
        stats["vehicle_visit_fail"] += 1
    else:
        stats["vehicle_visit_success"] += 1
        print(f"   ✅ Vehicle/visit OK")
    time.sleep(SLEEP_INTERVAL)

    if stop_flag:
        return

    # 4. Vehicle/maintain
    resp = client.send_request(API_VEHICLE_MAINTAIN, {"to_user_id": f_userid, "to_zone_id": f_zoneid})
    if check_step_error(resp, "vehicleMaintain"):
        stats["vehicle_maintain_fail"] += 1
    else:
        stats["vehicle_maintain_success"] += 1
        print(f"   ✅ Vehicle/maintain OK")
    time.sleep(SLEEP_INTERVAL)

# ========== 主流程 ==========
def daily_worker():
    """主工作线程：执行完整的每日好友互动"""
    global stop_flag, USER_UID, SIGN_KEY, TARGET_USER_ID, loop_thread

    if USER_UID == "_InputYourID_" or SIGN_KEY == DEFAULT_SIGN or TARGET_USER_ID == 0:
        print("[!] UID or SIGN not configured. Please run capture (-c) first!")
        loop_thread = None
        return

    client = GFLClient(USER_UID, SIGN_KEY, BASE_URL)
    stats["start_time"] = time.time()

    print("\n=== Daily Friend Operations Started ===")
    print(f"  Sleep interval: {SLEEP_INTERVAL}s")
    print(f"  Target user_id: {TARGET_USER_ID}")
    print("-" * 60)

    # 步骤 1：mallByType9
    if stop_flag:
        return
    step_mall_by_type9(client)
    time.sleep(SLEEP_INTERVAL)

    # 步骤 2：teamAndPraisePrize
    if stop_flag:
        return
    step_team_and_praise_prize(client)
    time.sleep(SLEEP_INTERVAL)

    # 步骤 3：获取好友列表
    if stop_flag:
        return
    friends = get_friend_list(client)
    stats["friends_total"] = len(friends)

    if not friends:
        print("[-] No friends found or failed to fetch list.")
        print_stats()
        loop_thread = None
        return

    # 步骤 4：遍历好友执行操作
    for i, friend in enumerate(friends, 1):
        if stop_flag:
            print("\n[*] Stop signal received, aborting...")
            break
        try:
            do_friend_operations(client, friend, i, len(friends))
        except Exception as e:
            print(f"   ❌ Error processing friend: {e}")
            continue

        # 每 10 个打印一次进度
        if i % 10 == 0:
            print(f"\n>>> Progress: {i}/{len(friends)} friends processed <<<")

    print_stats()
    print("\n[*] Daily friend operations finished.")
    loop_thread = None

def print_stats():
    """打印统计信息"""
    elapsed = time.time() - stats["start_time"] if stats["start_time"] else 0
    print("\n" + "=" * 60)
    print("📊 DAILY FRIEND OPERATIONS STATISTICS")
    print("-" * 60)
    print(f"  Friends total: {stats['friends_total']}")
    print(f"  Elapsed: {elapsed:.1f}s")
    print(f"\n  Friend/visit       : ✅ {stats['visit_success']} | ❌ {stats['visit_fail']}")
    print(f"  Friend/praise      : ✅ {stats['praise_success']} | ❌ {stats['praise_fail']}")
    print(f"  Vehicle/visit      : ✅ {stats['vehicle_visit_success']} | ❌ {stats['vehicle_visit_fail']}")
    print(f"  Vehicle/maintain   : ✅ {stats['vehicle_maintain_success']} | ❌ {stats['vehicle_maintain_fail']}")
    print("=" * 60)

def print_menu():
    print("\n" + "=" * 60)
    print("  DAILY FRIEND OPERATIONS TOOL")
    print("=" * 60)
    print("  -c     : Start Capture Proxy (获取 UID/SIGN)")
    print("  -r     : Run Daily Friend Operations")
    print("  -s     : Stop Operations")
    print("  -stats : Show Statistics")
    print("  -E     : Exit program")
    print("=" * 60)

if __name__ == "__main__":
    print_menu()
    while True:
        try:
            cmd = input("\nFRIEND> ").strip()
            if not cmd:
                continue
            cmd_prefix = cmd.split()[0]

            if cmd_prefix == '-c':
                if proxy_instance:
                    print("[!] Proxy is already running!")
                    continue
                try:
                    proxy_instance = GFLProxy(PROXY_PORT, STATIC_KEY, on_traffic)
                    proxy_instance.start()
                    set_windows_proxy(True, f"127.0.0.1:{PROXY_PORT}")
                    print(f"[*] Capture Proxy Started on {PROXY_PORT}. Windows Proxy SET.")
                    print("[*] Please log in to the game to capture UID and SIGN.")
                except Exception as e:
                    print(f"[!] Failed to start proxy: {e}")
                    proxy_instance = None

            elif cmd_prefix == '-r':
                # 停止代理（若运行）
                if proxy_instance:
                    print("[*] Stopping Proxy before starting operations...")
                    proxy_instance.stop()
                    set_windows_proxy(False)
                    proxy_instance = None
                    time.sleep(1)

                # 重置统计
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

                stop_flag = False
                loop_thread = threading.Thread(target=daily_worker, daemon=True)
                loop_thread.start()
                print("[*] Daily operations started in background thread.")
                print("[*] Type '-s' to stop, '-stats' for statistics.")

            elif cmd_prefix == '-s':
                stop_flag = True
                print("[*] Stop flag set. Waiting for current request to finish...")
                if loop_thread and loop_thread.is_alive():
                    loop_thread.join(timeout=5)
                    loop_thread = None

            elif cmd_prefix == '-stats':
                if loop_thread and loop_thread.is_alive():
                    print_stats()
                else:
                    print("[!] No operations running.")

            elif cmd_prefix == '-E':
                if proxy_instance:
                    proxy_instance.stop()
                    set_windows_proxy(False)
                stop_flag = True
                if loop_thread and loop_thread.is_alive():
                    loop_thread.join(timeout=2)
                    loop_thread = None
                print("[*] Exited cleanly. Windows proxy restored.")
                sys.exit(0)

            else:
                print(f"[!] Unknown command: {cmd}")
                print_menu()

        except KeyboardInterrupt:
            print("\n[!] Use '-E' to exit safely!")
        except Exception as e:
            print(f"[!] Error: {e}")