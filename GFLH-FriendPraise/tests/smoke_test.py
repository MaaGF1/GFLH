"""Smoke tests for GFLH-FriendPraise/src/friend_praise_gui.py.

Run from the repository root:  python GFLH-FriendPraise/tests/smoke_test.py

The GUI is a faithful port of the original console script, so most checks compare this
module against the frozen copy of that script in tests/original_friend_ops.py.

Covers, without touching the network and without opening a real window:
  * the API paths and hardcoded timings are the original ones;
  * the two "get my friend state" packets and their payload keys are unchanged;
  * the full request order for a run, plus every payload key, end to end;
  * counters for visit / praise / vehicle visit / vehicle maintain;
  * stop handling mid-run;
  * UID and Sign Key start empty in the GUI and are never persisted.
"""
import importlib.util
import io
import json
import os
import re
import sys
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
MODULE = os.path.join(ROOT, "GFLH-FriendPraise", "src", "friend_praise_gui.py")
# Frozen copy of the original console script, kept purely as the parity baseline.
BASELINE = os.path.join(HERE, "original_friend_ops.py")
ORIGINAL = os.path.join(ROOT, "GFLH-FriendPraise", "FriendPraise.py")

# --------------------------------------------------------------- fake gflzirc
import gflzirc as REAL_GFLZIRC  # noqa: E402

CALLS = []

FAKE = types.ModuleType("gflzirc")
for _name in dir(REAL_GFLZIRC):
    if _name.isupper():
        setattr(FAKE, _name, getattr(REAL_GFLZIRC, _name))
FAKE.set_windows_proxy = lambda *a, **k: True


class FakeProxy:
    def __init__(self, port, key, cb):
        self.port, self.key, self.cb = port, key, cb

    def start(self):
        pass

    def stop(self):
        pass


FAKE.GFLProxy = FakeProxy

FRIENDS = [
    {"f_userid": 111, "f_zoneid": 1, "name": "Alpha"},
    {"f_userid": 222, "f_zoneid": 2, "name": "Beta"},
]
FAIL_FOR = {222}          # friend 222 fails every step, to exercise the fail counters


class FakeClient:
    def __init__(self, uid, sign, base_url):
        self.uid, self.sign, self.base_url = uid, sign, base_url

    def send_request(self, endpoint, payload):
        CALLS.append((endpoint, payload))
        if endpoint == "Friend/list":
            return {"list": [dict(f) for f in FRIENDS]}
        if endpoint in ("Friend/visit", "Friend/praise"):
            if payload.get("f_userid") in FAIL_FOR:
                return {"error": "boom"}
            return {"success": True}
        if endpoint in ("Vehicle/visit", "Vehicle/maintain"):
            if payload.get("to_user_id") in FAIL_FOR:
                return {"error": "boom"}
            return {"success": True}
        return {}


FAKE.GFLClient = FakeClient
sys.modules["gflzirc"] = FAKE

spec = importlib.util.spec_from_file_location("friend_praise_gui", MODULE)
mod = importlib.util.module_from_spec(spec)
sys.modules["friend_praise_gui"] = mod
spec.loader.exec_module(mod)

LOGS = []
mod.LOG_SINK = LOGS.append
mod.SLEEP_INTERVAL = 0        # keep the tests quick; the value itself is checked below

FAILURES = []


def check(label, condition, detail=""):
    if condition:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s %s" % (label, detail))
        FAILURES.append(label)


def run_worker(**kwargs):
    CALLS.clear()
    del LOGS[:]
    mod.reset_stats()
    mod.STOP_FLAG["stop"] = False
    mod.daily_worker(**kwargs)
    return [e for e, _ in CALLS]


# ============================================================ 1. configurables
print("\n[1] what is configurable")
check("UID / Sign Key start empty",
      mod.USER_UID == "" and mod.SIGN_KEY == "")
check("there is no hand-typed placeholder UID", "_InputYourID_" not in
      io.open(MODULE, encoding="utf-8").read())
check("default server is the original AR15",
      mod.BASE_URL == mod.SERVERS["AR15"])
check("capture port is the original 8081", mod.PROXY_PORT == 8081)
check("sleep interval is the original value",
      re.search(r"^SLEEP_INTERVAL = 0\.01", io.open(MODULE, encoding="utf-8").read(),
                re.M) is not None)
raw = io.open(MODULE, encoding="utf-8").read()
check("Chinese UI strings decode as UTF-8", "开始点赞" in raw)
check("no U+FFFD replacement characters", "\ufffd" not in raw)


# ============================================================ 2. parity vs original
print("\n[2] parity with the original console script")
baseline_path = BASELINE if os.path.exists(BASELINE) else (
    ORIGINAL if os.path.exists(ORIGINAL) else None)
if baseline_path:
    print("  source: %s" % os.path.relpath(baseline_path, ROOT))
    src = io.open(baseline_path, encoding="utf-8").read()

    for name in ("API_FRIEND_MALL_BY_TYPE9", "API_FRIEND_TEAM_AND_PRAISE_PRIZE",
                 "API_FRIEND_LIST", "API_FRIEND_VISIT", "API_FRIEND_PRAISE",
                 "API_VEHICLE_VISIT", "API_VEHICLE_MAINTAIN"):
        original_value = re.search(r'^%s = "([^"]+)"' % name, src, re.M).group(1)
        check("%s unchanged" % name, getattr(mod, name) == original_value,
              (getattr(mod, name), original_value))

    check("SLEEP_INTERVAL unchanged",
          re.search(r"^SLEEP_INTERVAL = ([\d.]+)", src, re.M).group(1) == "0.01")
    check("PROXY_PORT unchanged",
          re.search(r"^PROXY_PORT = (\d+)", src, re.M).group(1) == str(mod.PROXY_PORT))
    check("BASE_URL unchanged",
          re.search(r'^BASE_URL = SERVERS\["(\w+)"\]', src, re.M).group(1) == "AR15")

    # the payload keys of the two setup packets and of the per-friend packets
    check("mallByType9 sends an empty payload",
          'API_FRIEND_MALL_BY_TYPE9, {}' in src
          and 'API_FRIEND_MALL_BY_TYPE9, {}' in raw)
    check("teamAndPraisePrize uses user_id",
          '{"user_id": TARGET_USER_ID}' in src and '{"user_id": TARGET_USER_ID}' in raw)
    check("friend packets use f_userid / f_zoneid",
          '{"f_userid": f_userid, "f_zoneid": f_zoneid}' in src
          and '{"f_userid": f_userid, "f_zoneid": f_zoneid}' in raw)
    check("vehicle packets use to_user_id / to_zone_id",
          '{"to_user_id": f_userid, "to_zone_id": f_zoneid}' in src
          and '{"to_user_id": f_userid, "to_zone_id": f_zoneid}' in raw)
    check("friend list is read from resp['list']",
          'resp.get("list", [])' in src and 'resp.get("list", [])' in raw)
    check("stat keys kept", all(key in raw for key in
          ("visit_success", "visit_fail", "praise_success", "praise_fail",
           "vehicle_visit_success", "vehicle_visit_fail",
           "vehicle_maintain_success", "vehicle_maintain_fail")))
else:
    print("  SKIP  no baseline found")


# ============================================================ 3. account plumbing
print("\n[3] account plumbing")
mod.set_account("123456", "abc")
check("set_account derives TARGET_USER_ID from the UID",
      mod.USER_UID == "123456" and mod.TARGET_USER_ID == 123456)
mod.set_account("not-a-number", "abc")
check("non-numeric UID falls back to 0", mod.TARGET_USER_ID == 0)
mod.set_account("999", "k" * 32)
check("explicit account state is used",
      mod.USER_UID == "999" and mod.SIGN_KEY == "k" * 32 and mod.TARGET_USER_ID == 999)

# an unconfigured account must not send anything
mod.USER_UID = ""
mod.SIGN_KEY = ""
mod.TARGET_USER_ID = 0
check("unconfigured account sends no requests", run_worker() == [])


# ============================================================ 4. end-to-end
print("\n[4] end-to-end run (fake server)")
mod.set_account("999", "k" * 32)
seq = run_worker()

check("two setup packets go first, in order",
      seq[:3] == ["Friend/mallByType9", "Friend/teamAndPraisePrize", "Friend/list"],
      seq[:3])
check("mallByType9 payload is empty", CALLS[0][1] == {})
check("teamAndPraisePrize carries our own user_id",
      CALLS[1][1] == {"user_id": 999}, CALLS[1][1])

per_friend = ["Friend/visit", "Friend/praise", "Vehicle/visit", "Vehicle/maintain"]
check("each friend gets the four operations in order",
      seq[3:] == per_friend * 2, seq[3:])
check("friend packets address the friend",
      CALLS[3][1] == {"f_userid": 111, "f_zoneid": 1}
      and CALLS[4][1] == {"f_userid": 111, "f_zoneid": 1},
      (CALLS[3][1], CALLS[4][1]))
check("vehicle packets address the friend's zone",
      CALLS[5][1] == {"to_user_id": 111, "to_zone_id": 1}
      and CALLS[6][1] == {"to_user_id": 111, "to_zone_id": 1},
      (CALLS[5][1], CALLS[6][1]))

check("friends_total counted", mod.stats["friends_total"] == 2)
check("visit counters", (mod.stats["visit_success"], mod.stats["visit_fail"]) == (1, 1))
check("praise counters", (mod.stats["praise_success"], mod.stats["praise_fail"]) == (1, 1))
check("vehicle visit counters",
      (mod.stats["vehicle_visit_success"], mod.stats["vehicle_visit_fail"]) == (1, 1))
check("vehicle maintain counters",
      (mod.stats["vehicle_maintain_success"], mod.stats["vehicle_maintain_fail"]) == (1, 1))
check("failure is logged for the friend's step",
      any("friendVisit Server Error" in line for line in LOGS),
      [l for l in LOGS if "Error" in l][:3])
check("per-friend header logged",
      any("[1/2] Alpha (ID: 111, Zone: 1)" in line for line in LOGS))
check("statistics block logged",
      any("DAILY FRIEND OPERATIONS STATISTICS" in line for line in LOGS))
check("finish message logged",
      any("Daily friend operations finished." in line for line in LOGS))


# ============================================================ 5. progress + stop
print("\n[5] progress reporting and stop handling")
snapshots = []
mod.set_account("999", "k" * 32)
CALLS.clear()
mod.reset_stats()
mod.STOP_FLAG["stop"] = False
mod.daily_worker(on_progress=lambda: snapshots.append(dict(mod.PROGRESS)))
check("progress is reported at least once per friend and once for the list",
      len(snapshots) >= 3, snapshots)
check("progress ends at the last friend",
      snapshots[-1] == {"index": 2, "total": 2}, snapshots[-1])

# stop mid-run: the second friend must not be processed
CALLS.clear()
mod.reset_stats()
mod.STOP_FLAG["stop"] = False
original_ops = mod.do_friend_operations


def stop_after_first(client, friend, index, total):
    result = original_ops(client, friend, index, total)
    mod.STOP_FLAG["stop"] = True
    return result


mod.do_friend_operations = stop_after_first
seq = run_worker()
mod.do_friend_operations = original_ops
check("stop flag aborts the loop before the next friend",
      [e for e in seq if e == "Friend/visit"] == ["Friend/visit"], seq)
check("stop is logged",
      any("Stop signal received" in line for line in LOGS), LOGS[-3:])


# ============================================================ 6. no friends
print("\n[6] empty friend list")


class EmptyListClient(FakeClient):
    def send_request(self, endpoint, payload):
        CALLS.append((endpoint, payload))
        if endpoint == "Friend/list":
            return {"list": []}
        return {}


mod.GFLClient = EmptyListClient
mod.set_account("999", "k" * 32)
seq = run_worker()
check("stops after the list when there are no friends",
      seq == ["Friend/mallByType9", "Friend/teamAndPraisePrize", "Friend/list"], seq)
check("empty list is reported",
      any("No friends found" in line for line in LOGS), LOGS[-4:])
mod.GFLClient = FakeClient


# ============================================================ 7. GUI + config
print("\n[7] GUI construction and config persistence")
try:
    import tempfile
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    app = mod.FriendPraiseApp(root)
    root.update_idletasks()
    root.update()

    check("UID entry starts empty", app.var_uid.get() == "")
    check("Sign Key entry starts empty", app.var_sign.get() == "")
    check("server combo pre-selected to AR15",
          app.var_server.get().startswith("AR15"), app.var_server.get())
    check("start button exists", app.btn_start is not None)

    app._log_from_thread("log routing probe")
    app._pump_queue()
    root.update_idletasks()
    check("log lines reach the widget",
          "log routing probe" in app.txt_log.get("1.0", "end"))

    # simulated capture fills the fields and derives user_id
    app._capture_callback("SYS_KEY_UPGRADE", "url", {"uid": "4242", "sign": "z" * 32})
    root.update_idletasks()
    root.update()
    check("capture fills UID / Sign", app.var_uid.get() == "4242"
          and app.var_sign.get() == "z" * 32)
    check("capture derives user_id", app.var_target.get() == "4242"
          and mod.TARGET_USER_ID == 4242)

    app._show_stats({"friends": "5", "index": 3, "total": 5, "visit": "3 / 0",
                     "praise": "3 / 0", "vehicle_visit": "3 / 0",
                     "vehicle_maintain": "3 / 0"})
    root.update_idletasks()
    check("stats rendered", app.stat_vars["friends"].get() == "5"
          and app.stat_vars["progress"].get() == "3/5"
          and app.stat_vars["visit"].get() == "3 / 0")

    cfg_path = os.path.join(tempfile.gettempdir(), "_tmp_friendpraise_config.json")
    if os.path.exists(cfg_path):
        os.remove(cfg_path)
    app._config_path = lambda: cfg_path
    app._save_config()
    check("config written", os.path.exists(cfg_path))
    if os.path.exists(cfg_path):
        saved = json.load(open(cfg_path, encoding="utf-8"))
        check("UID and Sign are never persisted",
              "USER_UID" not in saved and "SIGN_KEY" not in saved
              and "uid" not in saved and "sign" not in saved, sorted(saved))
        check("only server and language persisted",
              set(saved) == {"BASE_URL", "LANG"}, sorted(saved))
        os.remove(cfg_path)

    app._config_path = lambda: os.path.join(HERE, "_no_such_dir", "cfg.json")
    try:
        app._save_config()
        check("unwritable config path degrades gracefully", True)
    except Exception as exc:
        check("unwritable config path degrades gracefully", False,
              "%s: %s" % (type(exc).__name__, exc))

    root.destroy()
except tk.TclError as exc:  # headless environment
    print("  SKIP  GUI checks (no display: %s)" % exc)


# ============================================================ summary
print("\n" + "=" * 60)
if FAILURES:
    print("FAILED %d check(s): %s" % (len(FAILURES), ", ".join(FAILURES)))
    sys.exit(1)
print("ALL CHECKS PASSED")
