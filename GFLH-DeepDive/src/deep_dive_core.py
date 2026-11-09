# -*- coding: utf-8 -*-
# deep_dive_core.py
# GFLH - DeepDive（虚数迷宫+）刷开局核心逻辑：协议流程 / 判定 / 配置
#
# 一次「开局」按 README.md 的要求需要同时满足：
#
#   条件 1（1T）：
#       S2C Mission/startMission 的 new_spot_change 中出现左上补给点
#       spot 9414，type = 6。
#
#   条件 2（1T 结束进入 2T，S2C Mission/startTurn）：
#       - spot 9438 被占领（belong = 2 且有敌人）
#       - spot 9442 被占领（belong = 2 且有敌人）
#       - spot 9447 / 9421 至少有一点没有被占领
#         （README 补充：不在 S2C_Mission_startTurn 的 spot_act_info 中表现，
#           即视为「不被占领」）
#       - spot 9446 不存在敌人（同样：未出现即视为没有敌人）
#
# 1T 的行动流程取自 动作顺序/ 下的抓包：
#   startMission → supplyTeam(铁血) → teamMove(铁血 9457→9399)
#   → sangvisBattleFinish → combinationInfo → reinforceTeam(9457, 2队)
#   → supplyTeam(2队) → teamMove(2队 9457→9401) → battleFinish
#   → combinationInfo → endTurn → startEnemyTurn → endEnemyTurn → startTurn
#
# 本模块只负责协议与判定，GUI / CLI / 打包脚本都复用它。

import copy
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from gflzirc import (
    GFLClient, SERVERS,
    API_MISSION_COMBINFO, API_MISSION_START, API_MISSION_ABORT,
    API_MISSION_TEAM_MOVE, API_MISSION_SUPPLY, API_MISSION_BATTLE_FINISH,
    API_MISSION_END_TURN, API_MISSION_START_ENEMY_TURN,
    API_MISSION_END_ENEMY_TURN, API_MISSION_START_TURN,
)

# gflzirc 0.4.4 的 constants.py 里没有导出这两个端点，
# 这里按 动作顺序/ 抓包文件名补齐（Mission/reinforceTeam、Mission/sangvisBattleFinish）。
API_MISSION_REINFORCE = "Mission/reinforceTeam"
API_MISSION_SANGVIS_BATTLE_FINISH = "Mission/sangvisBattleFinish"

# ============================================================
# 关卡常量（虚数迷宫+，mission 10158）
# ============================================================
MISSION_ID = 10158

START_SPOT = 9457          # 开局部署点（铁血 1 队 / 格里芬 2 队都从这里出发）
SANGVIS_MOVE_TO = 9399     # 铁血 1 队 1T 移动并交战
GRIFFIN_MOVE_TO = 9401     # 格里芬 2 队 1T 移动并交战

# 判定规则：可在 deep_dive_config.json 的 rules 里覆盖
DEFAULT_RULES = {
    "supply_spot": 9414,          # 左上补给点
    "supply_type": 6,             # 补给点 type
    "required_occupied": [9438, 9442],   # 必须被敌人占领
    "either_free": [9447, 9421],         # 「任意一点没有被占领」，见 either_free_mode
    "either_free_mode": "any",           # any = 至少一点空闲；all = 两点都必须空闲
    "must_be_empty": [9446],             # 必须不存在敌人
}

# ============================================================
# battleFinish 上报模板
# 数值取自 动作顺序/0066（铁血）与 0075（格里芬）的真实抓包，
# 会话相关的字段（spot_id / seed / 单位列表 / mvp / micalog）在运行时替换。
# ============================================================
SANGVIS_BATTLE_TEMPLATE = {
    "spot_id": 0,
    "if_enemy_die": True,
    "current_time": 0,
    "boss_hp": 0,
    "mvp": 0,
    "last_battle_info": "",
    "use_skill_squads": [],
    "use_skill_ally_spots": [],
    "use_skill_vehicle_spots": [],
    "sangvis_chip_skills": {},
    "sangvises": [],
    "user_rec": "",
    "1000": {
        "10": 104247, "11": 104247, "12": 104247, "13": 104247,
        "15": 11389, "16": 0, "17": 203, "33": 10004, "40": 70,
        "18": 0, "19": 54, "20": 15, "21": 0, "22": 60, "23": 930,
        "24": 17465, "25": 0, "26": 17465, "27": 7,
        "34": 6, "35": 19, "41": 249, "42": 0, "43": 0, "44": 0,
    },
    "1001": {},
    "1002": {},
    "1003": {},
    "1005": {},
    "1007": {},
    "1008": {},
    "1009": {},
    "battle_damage": {},
    "micalog": {"user_device": "", "user_ip": ""},
}

GRIFFIN_BATTLE_TEMPLATE = {
    "spot_id": 0,
    "if_enemy_die": True,
    "current_time": 0,
    "boss_hp": 0,
    "mvp": 0,
    "last_battle_info": "",
    "use_skill_squads": [],
    "use_skill_ally_spots": [],
    "use_skill_vehicle_spots": [],
    "guns": [],
    "user_rec": "",
    "1000": {
        "10": 51222, "11": 51222, "12": 51222, "13": 51222,
        "15": 9910, "16": 0, "17": 52, "33": 10005, "40": 72,
        "18": 0, "19": 0, "20": 0, "21": 0, "22": 0, "23": 0,
        "24": 11909, "25": 0, "26": 11909, "27": 3,
        "34": 38, "35": 38, "41": 165, "42": 0, "43": 0, "44": 0,
    },
    "1001": {},
    "1002": {},
    "1003": {},
    "1005": {},
    "1007": {},
    "1008": {},
    "1009": {},
    "battle_damage": {},
    "micalog": {"user_device": "", "user_ip": ""},
}

CONFIG_FILENAME = "deep_dive_config.json"


# ============================================================
# 工具函数
# ============================================================
def app_dir() -> str:
    """返回配置文件的存放目录（打包后在 exe 同级，源码运行在项目根目录）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def config_path() -> str:
    return os.path.join(app_dir(), CONFIG_FILENAME)


def load_config(path: Optional[str] = None) -> dict:
    path = path or config_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(data: dict, path: Optional[str] = None) -> bool:
    path = path or config_path()
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


def detect_server_url(url: str) -> Optional[str]:
    """从代理回调里的请求 URL 识别区服，返回 SERVERS 中的 base url。"""
    if not url or not isinstance(url, str):
        return None
    for base in SERVERS.values():
        if base and base in url:
            return base
    match = re.search(r"https?://[^/\s]+/index\.php/\d+", url)
    return match.group(0) if match else None


def spot_map(resp: dict) -> dict:
    """把 spot_act_info（list 或 dict）统一成 {int(spot_id): spot_dict}。"""
    spots = resp.get("spot_act_info") if isinstance(resp, dict) else None
    result = {}
    if isinstance(spots, list):
        for item in spots:
            if not isinstance(item, dict):
                continue
            try:
                result[int(item.get("spot_id"))] = item
            except (TypeError, ValueError):
                continue
    elif isinstance(spots, dict):
        for key, item in spots.items():
            if isinstance(item, dict):
                try:
                    result[int(key)] = item
                except (TypeError, ValueError):
                    continue
    return result


def has_enemy(spot: Optional[dict]) -> bool:
    if not spot:
        return False
    return str(spot.get("enemy_team_id", "0")) not in ("0", "", "None")


def is_occupied(spot: Optional[dict]) -> bool:
    """被敌人占领：belong = 2 且该点有敌人驻守。"""
    if not spot:
        return False
    return str(spot.get("belong")) == "2" and has_enemy(spot)


def enemy_label(spot: Optional[dict]) -> str:
    """用于日志：未出现在 spot_act_info 中的点按 README 视为「未被占领 / 无敌人」。"""
    if spot is None:
        return "未出现"
    if not has_enemy(spot):
        return "空"
    return "敌%s" % spot.get("enemy_team_id")


def spot_seed(resp: dict, spot_id: int) -> int:
    spot = spot_map(resp).get(int(spot_id))
    if not spot:
        return 0
    try:
        return int(spot.get("seed", 0))
    except (TypeError, ValueError):
        return 0


def find_supply_point(resp: dict, rules: Optional[dict] = None) -> Optional[dict]:
    """条件 1：startMission 的 new_spot_change 里是否刷出了指定补给点。"""
    rules = merge_rules(rules)
    change = resp.get("new_spot_change") if isinstance(resp, dict) else None
    if not isinstance(change, dict):
        return None
    info = change.get(str(rules["supply_spot"]))
    if not isinstance(info, dict):
        info = change.get(rules["supply_spot"])
    if not isinstance(info, dict):
        return None
    try:
        if int(info.get("type", -1)) != int(rules["supply_type"]):
            return None
    except (TypeError, ValueError):
        return None
    return info


def describe_supply(info: Optional[dict]) -> str:
    if not info:
        return "未刷出"
    return "spot %s type %s（%sT~%sT）" % (
        info.get("spot_id"), info.get("type"),
        info.get("start_turn", "?"), info.get("end_turn", "?"),
    )


def merge_rules(rules: Optional[dict]) -> dict:
    merged = copy.deepcopy(DEFAULT_RULES)
    if isinstance(rules, dict):
        for key, value in rules.items():
            if key in merged:
                merged[key] = value
    return merged


# ============================================================
# 条件 2 判定
# ============================================================
def evaluate_2t(resp: dict, rules: Optional[dict] = None) -> dict:
    """判定进入 2T 时的敌人分布，返回带明细的结果字典。"""
    rules = merge_rules(rules)
    spots = spot_map(resp)

    required = []
    for sid in rules["required_occupied"]:
        spot = spots.get(int(sid))
        ok = is_occupied(spot)
        required.append({
            "spot_id": int(sid),
            "ok": ok,
            "enemy": enemy_label(spot),
        })

    either = []
    for sid in rules["either_free"]:
        spot = spots.get(int(sid))
        either.append({
            "spot_id": int(sid),
            # README：不在 startTurn 的 spot_act_info 中表现 == 不被占领
            "free": spot is None or not has_enemy(spot),
            "enemy": enemy_label(spot),
            "missing": spot is None,
        })
    mode = str(rules.get("either_free_mode", "any")).lower()
    if mode == "all":
        either_ok = bool(either) and all(item["free"] for item in either)
    else:
        either_ok = any(item["free"] for item in either)

    empty = []
    for sid in rules["must_be_empty"]:
        spot = spots.get(int(sid))
        ok = spot is None or not has_enemy(spot)
        empty.append({
            "spot_id": int(sid),
            "ok": ok,
            "enemy": enemy_label(spot),
        })

    passed = all(item["ok"] for item in required) and either_ok and all(item["ok"] for item in empty)

    parts = ["%d%s(%s)" % (item["spot_id"], "✓" if item["ok"] else "✗", item["enemy"])
             for item in required]
    either_ids = "/".join(str(item["spot_id"]) for item in either)
    if either_ok:
        if mode == "all":
            parts.append("%s✓(均未占领)" % either_ids)
        else:
            free_desc = ",".join(
                "%d%s" % (item["spot_id"], "未出现" if item["missing"] else "空")
                for item in either if item["free"])
            parts.append("%s✓(%s)" % (either_ids, free_desc))
    else:
        blocked = ",".join(str(item["spot_id"]) for item in either if not item["free"])
        parts.append("%s✗(%s被占)" % (either_ids, blocked))
    parts.extend("%d%s(%s)" % (item["spot_id"], "✓" if item["ok"] else "✗", item["enemy"])
                 for item in empty)

    return {
        "pass": passed,
        "required": required,
        "either": either,
        "either_ok": either_ok,
        "empty": empty,
        "text": " ".join(parts),
    }

# ============================================================
# 阵容（从 Index/index 抓包中提取）
# ============================================================
def _iter_records(value):
    """兼容 list / dict 两种 Index 数据结构，统一产出 dict 记录。"""
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                yield item
    elif isinstance(value, dict):
        for item in value.values():
            if isinstance(item, dict):
                yield item


def extract_roster(index: dict, sangvis_team_id: int = 1, griffin_team_id: int = 2) -> dict:
    """从 S2C Index/index 数据里提取铁血队 / 格里芬队 / 妖精，用于拼 battleFinish。"""
    if not isinstance(index, dict):
        raise ValueError("Index/index 数据无效")

    guns = []
    for gun in _iter_records(index.get("gun_with_user_info")):
        if str(gun.get("team_id")) != str(griffin_team_id):
            continue
        try:
            guns.append({
                "id": int(gun["id"]),
                "life": int(gun.get("life", 0)),
                "_pos": int(gun.get("position", 0)),
            })
        except (KeyError, TypeError, ValueError):
            continue
    guns.sort(key=lambda item: item["_pos"])
    for gun in guns:
        gun.pop("_pos", None)

    lives = {}
    for unit in _iter_records(index.get("sangvis_with_user_info")):
        try:
            lives[str(unit["id"])] = int(unit.get("life", 0))
        except (KeyError, TypeError, ValueError):
            continue

    team = None
    for candidate in _iter_records(index.get("sangvis_team_with_user_info")):
        if str(candidate.get("team_id")) == str(sangvis_team_id):
            team = candidate
            break

    units = []
    mvp = None
    if team:
        members = []
        for slot, member in (team.get("info") or {}).items():
            if not isinstance(member, dict):
                continue
            try:
                unit_id = int(member.get("sangvis_with_user_id", 0))
            except (TypeError, ValueError):
                continue
            if unit_id <= 0:
                continue
            try:
                position = int(member.get("position", slot))
            except (TypeError, ValueError):
                position = 0
            members.append((position, unit_id))
        members.sort(key=lambda item: item[0])
        units = [{"id": unit_id, "life": lives.get(str(unit_id), 0)} for _, unit_id in members]
        leader = [unit_id for position, unit_id in members if position == 7]
        if leader:
            mvp = leader[0]
        elif units:
            mvp = units[0]["id"]

    fairy_id = None
    for fairy in _iter_records(index.get("fairy_with_user_info")):
        if str(fairy.get("team_id")) == str(griffin_team_id):
            try:
                fairy_id = int(fairy["id"])
            except (KeyError, TypeError, ValueError):
                fairy_id = None
            break

    return {
        "sangvis_team_id": int(sangvis_team_id),
        "griffin_team_id": int(griffin_team_id),
        "sangvis_units": units,
        "guns": guns,
        "fairy_id": fairy_id,
        "mvp_sangvis": mvp,
        "mvp_gun": guns[0]["id"] if guns else None,
    }


def normalize_roster(roster: Optional[dict]) -> dict:
    """把配置里的阵容补齐成标准结构（容忍字符串数字 / 缺字段）。"""
    roster = dict(roster or {})
    result = {
        "sangvis_team_id": _as_int(roster.get("sangvis_team_id"), 1),
        "griffin_team_id": _as_int(roster.get("griffin_team_id"), 2),
        "fairy_id": _as_int(roster.get("fairy_id"), None),
        "mvp_sangvis": _as_int(roster.get("mvp_sangvis"), None),
        "mvp_gun": _as_int(roster.get("mvp_gun"), None),
        "user_device": str(roster.get("user_device") or ""),
        "sangvis_units": [],
        "guns": [],
    }
    for unit in (roster.get("sangvis_units") or []):
        if not isinstance(unit, dict):
            continue
        unit_id = _as_int(unit.get("id"), None)
        if not unit_id:
            continue
        result["sangvis_units"].append({"id": unit_id, "life": _as_int(unit.get("life"), 0)})
    for gun in (roster.get("guns") or []):
        if not isinstance(gun, dict):
            continue
        gun_id = _as_int(gun.get("id"), None)
        if not gun_id:
            continue
        result["guns"].append({"id": gun_id, "life": _as_int(gun.get("life"), 0)})
    return result


def _as_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def validate_roster(roster: Optional[dict]) -> list:
    """返回阵容的问题列表，空列表表示可用。"""
    data = normalize_roster(roster)
    problems = []
    if not data["sangvis_units"]:
        problems.append("铁血梯队 %d 队没有单位数据" % data["sangvis_team_id"])
    if not data["guns"]:
        problems.append("格里芬梯队 %d 队没有枪娘数据" % data["griffin_team_id"])
    if data["sangvis_units"] and all(unit["life"] <= 0 for unit in data["sangvis_units"]):
        problems.append("铁血梯队单位生命值全部为 0")
    if data["guns"] and all(gun["life"] <= 0 for gun in data["guns"]):
        problems.append("格里芬梯队枪娘生命值全部为 0")
    return problems


def format_roster(roster: Optional[dict]) -> str:
    data = normalize_roster(roster)
    fairy = "妖精 %d" % data["fairy_id"] if data["fairy_id"] else "无妖精"
    device = "设备指纹已捕获" if data["user_device"] else "设备指纹未捕获"
    return "铁血 %d队 %d人 | 格里芬 %d队 %d人 | %s | %s" % (
        data["sangvis_team_id"], len(data["sangvis_units"]),
        data["griffin_team_id"], len(data["guns"]),
        fairy, device,
    )


# ============================================================
# 结果结构
# ============================================================
@dataclass
class AttemptResult:
    number: int
    cond1: bool = False
    cond2: Optional[bool] = None
    ok: bool = False
    detail: str = ""
    supply: Optional[dict] = None
    error: Optional[str] = None
    kept_mission: bool = False


class MissionError(Exception):
    """协议步骤返回 error / error_local 时抛出。"""


# ============================================================
# 刷开局主体
# ============================================================
class DeepDiveReroll:
    """虚数迷宫+ 开局重掷：一次 attempt = 一次 startMission + 1T 流程 + 2T 判定。"""

    def __init__(self, client: GFLClient, roster: dict, rules: Optional[dict] = None,
                 delay: float = 0.15, log: Optional[Callable[[str], None]] = None):
        self.client = client
        self.roster = normalize_roster(roster)
        self.rules = merge_rules(rules)
        self.delay = max(0.0, float(delay))
        self._log = log or (lambda msg: None)

    # ------------------------------------------------------------ 日志
    def log(self, msg: str):
        try:
            self._log(msg)
        except Exception:
            pass

    # ------------------------------------------------------------ 请求
    def _call(self, endpoint: str, payload: dict, step: str):
        """发一个请求。注意：部分接口（如 combinationInfo）正常就返回 []，
        所以只有「dict 且带 error / error_local」才算失败。"""
        resp = self.client.send_request(endpoint, payload)
        if isinstance(resp, dict) and ("error" in resp or "error_local" in resp):
            detail = resp.get("error") if "error" in resp else resp.get("error_local")
            if isinstance(detail, (dict, list)):
                detail = json.dumps(detail, ensure_ascii=False)
            raw = resp.get("raw")
            if raw and str(raw) not in str(detail):
                detail = "%s（原始返回 %r）" % (detail, raw)
            raise MissionError("%s：%s" % (step, detail))
        if self.delay:
            time.sleep(self.delay)
        return resp

    # ------------------------------------------------------------ 上报包
    def _start_payload(self) -> dict:
        return {
            "mission_id": MISSION_ID,
            "spots": [],
            "squad_spots": [],
            "sangvis_spots": [{
                "spot_id": START_SPOT,
                "sangvis_team_id": self.roster["sangvis_team_id"],
            }],
            "vehicle_spots": [],
            "ally_spots": [],
            "mission_ally_spots": [],
            "ally_id": int(time.time()),
        }

    def _sangvis_battle_payload(self, seed: int) -> dict:
        payload = copy.deepcopy(SANGVIS_BATTLE_TEMPLATE)
        units = self.roster["sangvis_units"]
        mvp = self.roster.get("mvp_sangvis") or (units[0]["id"] if units else 0)
        payload["spot_id"] = SANGVIS_MOVE_TO
        payload["current_time"] = int(time.time())
        payload["mvp"] = mvp
        payload["sangvises"] = [{"id": u["id"], "life": u["life"]} for u in units]
        payload["1007"] = {str(u["id"]): {"509": 0, "510": 0} for u in units}
        payload["user_rec"] = '{"seed":%d,"record":[]}' % int(seed)
        payload["micalog"] = {"user_device": self.roster["user_device"], "user_ip": ""}
        return payload

    def _griffin_battle_payload(self, seed: int) -> dict:
        payload = copy.deepcopy(GRIFFIN_BATTLE_TEMPLATE)
        guns = self.roster["guns"]
        mvp = self.roster.get("mvp_gun") or (guns[0]["id"] if guns else 0)
        payload["spot_id"] = GRIFFIN_MOVE_TO
        payload["current_time"] = int(time.time())
        payload["mvp"] = mvp
        payload["guns"] = [{"id": g["id"], "life": g["life"]} for g in guns]
        payload["1002"] = {str(g["id"]): {"47": 0} for g in guns}
        fairy_id = self.roster.get("fairy_id")
        payload["1003"] = ({str(fairy_id): {"9": 1, "68": 0}} if fairy_id else {})
        payload["user_rec"] = '{"seed":%d,"record":[]}' % int(seed)
        payload["micalog"] = {"user_device": self.roster["user_device"], "user_ip": ""}
        return payload

    # ------------------------------------------------------------ 1T
    def play_turn_one(self) -> dict:
        """按 动作顺序/ 执行 1T，返回 2T 的 startTurn 回包。"""
        team_sv = self.roster["sangvis_team_id"]
        team_gr = self.roster["griffin_team_id"]

        self._call(API_MISSION_SUPPLY, {
            "mission_id": MISSION_ID,
            "target_type": 8,
            "target_id": team_sv,
            "spot_id": START_SPOT,
        }, "supplyTeam(铁血)")

        move = self._call(API_MISSION_TEAM_MOVE, {
            "person_type": 2,
            "person_id": team_sv,
            "from_spot_id": START_SPOT,
            "to_spot_id": SANGVIS_MOVE_TO,
            "move_type": 1,
        }, "teamMove(铁血 %d→%d)" % (START_SPOT, SANGVIS_MOVE_TO))
        seed = spot_seed(move, SANGVIS_MOVE_TO)
        self._call(API_MISSION_SANGVIS_BATTLE_FINISH,
                   self._sangvis_battle_payload(seed), "sangvisBattleFinish")

        self._call(API_MISSION_COMBINFO, {"mission_id": MISSION_ID}, "combinationInfo")

        self._call(API_MISSION_REINFORCE, {
            "spot_id": START_SPOT,
            "team_id": team_gr,
        }, "reinforceTeam")

        self._call(API_MISSION_SUPPLY, {
            "mission_id": MISSION_ID,
            "target_type": 1,
            "target_id": team_gr,
            "spot_id": START_SPOT,
        }, "supplyTeam(格里芬)")

        move = self._call(API_MISSION_TEAM_MOVE, {
            "person_type": 1,
            "person_id": team_gr,
            "from_spot_id": START_SPOT,
            "to_spot_id": GRIFFIN_MOVE_TO,
            "move_type": 1,
        }, "teamMove(格里芬 %d→%d)" % (START_SPOT, GRIFFIN_MOVE_TO))
        seed = spot_seed(move, GRIFFIN_MOVE_TO)
        self._call(API_MISSION_BATTLE_FINISH,
                   self._griffin_battle_payload(seed), "battleFinish")

        self._call(API_MISSION_COMBINFO, {"mission_id": MISSION_ID}, "combinationInfo")
        self._call(API_MISSION_END_TURN, {}, "endTurn")
        self._call(API_MISSION_START_ENEMY_TURN, {}, "startEnemyTurn")
        self._call(API_MISSION_END_ENEMY_TURN, {}, "endEnemyTurn")
        turn2 = self._call(API_MISSION_START_TURN, {}, "startTurn")
        if not isinstance(turn2, dict):
            raise MissionError("startTurn：返回格式异常 %r" % (turn2,))
        return turn2

    # ------------------------------------------------------------ 中止
    def abort(self) -> bool:
        try:
            resp = self.client.send_request(API_MISSION_ABORT, {"mission_id": MISSION_ID})
        except Exception as exc:
            self.log("  [!] 中止任务异常: %r" % (exc,))
            return False
        if isinstance(resp, dict) and ("error" in resp or "error_local" in resp):
            detail = resp.get("raw") or resp.get("error_local") or resp.get("error")
            # 没有进行中的任务时服务端会回 error:3（明文），不算异常
            self.log("  [*] 中止任务未生效（%s），继续下一轮" % detail)
            return False
        self.log("  [*] 已中止任务，准备下一轮")
        return True

    def abort_quietly(self) -> None:
        try:
            self.client.send_request(API_MISSION_ABORT, {"mission_id": MISSION_ID})
        except Exception:
            pass

    # ------------------------------------------------------------ 单次尝试
    def attempt(self, number: int = 1, check_2t: bool = True, dry_run: bool = False) -> AttemptResult:
        result = AttemptResult(number=number)
        self.log("")
        self.log("[尝试 %d]" % number)
        try:
            self._call(API_MISSION_COMBINFO, {"mission_id": MISSION_ID}, "combinationInfo")
            start = self._call(API_MISSION_START, self._start_payload(), "startMission")
            if not isinstance(start, dict):
                raise MissionError("startMission：返回格式异常 %r" % (start,))

            supply = find_supply_point(start, self.rules)
            result.supply = supply
            result.cond1 = supply is not None
            if not supply:
                change = start.get("new_spot_change")
                if isinstance(change, dict) and change:
                    desc = "、".join(
                        "%s(type %s)" % (key, info.get("type"))
                        for key, info in change.items() if isinstance(info, dict))
                    self.log("  1T 补给点: 未刷出（本次 change: %s）→ 中止" % desc)
                else:
                    self.log("  1T 补给点: 未刷出（new_spot_change 为空）→ 中止")
                self.abort()
                result.detail = "1T 未刷出补给点 %d" % self.rules["supply_spot"]
                return result

            self.log("  1T 补给点: %s ✓" % describe_supply(supply))

            if not check_2t:
                result.ok = True
                if dry_run:
                    self.log("  [试跑] 条件满足，已中止该局（试跑不保留）")
                    self.abort()
                else:
                    result.kept_mission = True
                    result.detail = "1T 补给点已刷出（仅校验 1T）"
                    self.log("  [+] 条件满足，已保留该局（任务停留在 1T）")
                return result

            self.log("  执行 1T 行动流程（按 动作顺序/ 的 15 个请求）…")
            turn2 = self.play_turn_one()

            evaluation = evaluate_2t(turn2, self.rules)
            result.cond2 = evaluation["pass"]
            result.detail = evaluation["text"]
            self.log("  2T 判定: %s → %s" % (
                evaluation["text"], "通过 ✓" if evaluation["pass"] else "未通过 ✗"))

            if evaluation["pass"]:
                result.ok = True
                if dry_run:
                    self.log("  [试跑] 条件满足，已中止该局（试跑不保留）")
                    self.abort()
                else:
                    result.kept_mission = True
                    self.log("  [+] 全部条件满足，已保留该局（任务停留在 2T）")
                return result

            self.abort()
            return result

        except MissionError as exc:
            result.error = str(exc)
            result.detail = "协议错误: %s" % exc
            self.log("  [!] %s" % result.detail)
            self.abort()
            return result
        except Exception as exc:  # noqa: BLE001 - 兜底，避免线程直接挂掉
            result.error = repr(exc)
            result.detail = "异常: %r" % (exc,)
            self.log("  [!] %s" % result.detail)
            self.abort()
            return result

    # ------------------------------------------------------------ 循环
    def run(self, *, check_2t: bool = True, max_attempts: int = 0,
            should_stop: Optional[Callable[[], bool]] = None,
            on_result: Optional[Callable[[AttemptResult], None]] = None,
            dry_run: bool = False, retry_delay: float = 0.1,
            max_consecutive_errors: int = 6) -> int:
        attempt_no = 0
        consecutive_errors = 0
        while True:
            if should_stop and should_stop():
                self.log("[*] 已停止重掷")
                break
            if max_attempts and attempt_no >= max_attempts:
                self.log("[*] 已达到最大尝试次数 %d" % max_attempts)
                break

            attempt_no += 1
            result = self.attempt(attempt_no, check_2t=check_2t, dry_run=dry_run)
            if on_result:
                try:
                    on_result(result)
                except Exception:
                    pass
            if result.ok and not dry_run:
                self.log("[+] 第 %d 次尝试成功，脚本停止。" % attempt_no)
                break
            if result.error:
                consecutive_errors += 1
                time.sleep(max(1.0, retry_delay))
                if max_consecutive_errors and consecutive_errors >= max_consecutive_errors:
                    self.log("[!] 连续 %d 次请求出错，已停止。" % consecutive_errors)
                    self.log("    请检查：区服是否选对、Sign Key 是否已过期、账号能否进入该关卡。")
                    break
            else:
                consecutive_errors = 0
                time.sleep(retry_delay)
        return attempt_no


# ============================================================
# 抓包收集器（登录时自动获取 UID / SIGN / Index / 设备指纹）
# ============================================================
class CaptureCollector:
    """GFLProxy 回调的轻量包装：收集密钥、区服、Index/index、micalog.user_device。"""

    def __init__(self, on_event: Optional[Callable[[str], None]] = None):
        self.uid = None
        self.sign = None
        self.index = None
        self.user_device = ""
        self.server_url = None
        self._on_event = on_event

    def reset(self):
        self.uid = None
        self.sign = None
        self.index = None
        self.user_device = ""
        self.server_url = None
        self._notify("reset")

    def _notify(self, event: str):
        if self._on_event:
            try:
                self._on_event(event)
            except Exception:
                pass

    @property
    def has_keys(self) -> bool:
        return bool(self.uid and self.sign)

    def handle(self, event_type: str, url: str, data):
        detected = detect_server_url(url)
        if detected and detected != self.server_url:
            self.server_url = detected
            self._notify("server")

        event_type = (event_type or "").upper()
        if event_type == "SYS_KEY_UPGRADE":
            if isinstance(data, dict) and data.get("uid") and data.get("sign"):
                changed = (self.uid, self.sign) != (str(data["uid"]), str(data["sign"]))
                self.uid = str(data["uid"])
                self.sign = str(data["sign"])
                if changed:
                    self._notify("keys")
            return

        if event_type == "S2C" and "Index/index" in (url or ""):
            if isinstance(data, dict) and data:
                self.index = data
                self._notify("index")
            return

        if event_type == "C2S" and isinstance(data, dict):
            micalog = data.get("micalog")
            if isinstance(micalog, dict):
                device = micalog.get("user_device")
                if device and device != self.user_device:
                    self.user_device = str(device)
                    self._notify("device")
