#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从离线 GFLData 中提取单张地图的表格数据。

用到的文件（相对 <GFLData>/<server>/）：
  stc/mission.json, spot.json, enemy_team.json, enemy_in_team.json,
  enemy_character_type.json, enemy_standard_attribute.json, team_ai.json,
  building.json, ally_team.json, gun.json, gun_in_ally.json, equip.json,
  auto_mission.json, mission_win_type_config.json
  text/table/mission.json, building.json, team_ai.json, enemy_character_type.json,
  ally_team.json, gun.json, equip.json, special_spot_config.json,
  mission_win_type_config.json

输出：data/mission-<id>.json + 更新 data/index.json（供页面切换地图）。

用法：
    python extract.py                          # 默认 慢休克-自画像-厚涂 (11403)
    python extract.py --mission 11403 11402    # 一次导出多张
    python extract.py --data-root ..\\GFLData --server ch --turn 1
"""

import argparse
import json
import math
import os
import re
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_ROOT = os.path.normpath(os.path.join(HERE, "..", "GFLData"))
DEFAULT_OUT = os.path.join(HERE, "data")
DEFAULT_MISSION = 11403  # 慢休克 - 自画像 - 厚涂

# 节点类型：1/2/3/4/7 由图标的英文标注核对过（COMMAND POST / NORMAL / HELIPORT /
# RADAR / HEAVY HELIPORT），其余类型只显示编号，不做猜测。
SPOT_TYPE_LABEL = {1: "指挥部", 2: "普通点", 3: "机场", 4: "雷达", 7: "重装机场"}

BELONG_LABEL = {0: "中立", 1: "我方", 2: "敌方", 3: "第三方", 99: "视野外"}

BUILDING_DESTROY_LABEL = {
    "0": "不可破坏",
    "1": "重装部队可破坏",
    "2": "踩点破坏",
}


# --------------------------------------------------------------------------- #
# 读取
# --------------------------------------------------------------------------- #
def load_json(data_root, rel_path):
    path = os.path.join(data_root, rel_path)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class TextTables:
    """text/table/*.json 都是 {"<前缀>-<id>": "文本"} 形式的字典。"""

    def __init__(self, data_root):
        self.root = data_root
        self._cache = {}

    def get(self, name, key, default=None):
        if name not in self._cache:
            try:
                self._cache[name] = load_json(self.root, os.path.join("text", "table", name + ".json"))
            except FileNotFoundError:
                self._cache[name] = {}
        return self._cache[name].get(key, default)

    def by_id(self, name, prefix, value_id, default=None):
        return self.get(name, "{}-{}".format(prefix, value_id), default)


# --------------------------------------------------------------------------- #
# 数值：与 gflmaps/main.js 的 ceiling / bround / enemyattribute 保持一致
# --------------------------------------------------------------------------- #
def ceiling(a):
    """JS: (a%1) ? (a-a%1+1) : a —— 正数即向上取整。"""
    if a != a:  # NaN
        return a
    return math.ceil(a)


def bround(a):
    """JS 的 bround：.5 走银行家舍入，其余四舍五入。Python round 行为一致。"""
    if a != a:
        return a
    return round(a)


def build_level_factors(std_attr):
    """enemy_standard_attribute: [{level, maxlife, pow, ...}] -> {level: row}"""
    return {int(row["level"]): row for row in std_attr}


def enemy_attribute(char_type, attr, level, factors):
    """按等级把图鉴基准属性换算到实际等级；maxlife 保留小数，其余取整。"""
    normal = float(char_type[attr])
    normal_level = float(char_type["level"])
    if not attr in next(iter(factors.values())):
        return bround(normal)
    this_factor = factors.get(int(level), {}).get(attr)
    normal_factor = factors.get(int(normal_level), {}).get(attr)
    if this_factor is None or not normal_factor:
        return bround(normal)
    value = normal * float(this_factor) / float(normal_factor)
    return value if attr == "maxlife" else bround(value)


def parse_correction_turn(raw):
    """correction_turn 形如 "2:10,3:20"，返回 {回合: 等级偏移}。"""
    result = {}
    for part in str(raw or "").split(","):
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        try:
            result[int(key)] = int(value)
        except ValueError:
            continue
    return result


def team_combat_power(units, char_types, factors, armor_coef):
    """单个梯队的效能合计；公式取自 gflmaps/main.js 的 efectcal()。"""
    total = 0.0
    detail = {}
    for unit in units:
        char_type = char_types.get(unit["charTypeId"])
        if not char_type:
            continue
        level = unit["level"]
        number = float(unit["number"])
        pow_ = enemy_attribute(char_type, "pow", level, factors)
        def_break = enemy_attribute(char_type, "def_break", level, factors)
        rate = enemy_attribute(char_type, "rate", level, factors)
        hit = enemy_attribute(char_type, "hit", level, factors)
        max_life = enemy_attribute(char_type, "maxlife", level, factors)
        dodge = enemy_attribute(char_type, "dodge", level, factors)
        armor = enemy_attribute(char_type, "armor", level, factors)
        defence = enemy_attribute(char_type, "def", level, factors)
        tenacity = enemy_attribute(char_type, "tenacity", level, factors)
        def_percent = float(unit["defPercent"])

        attack = ceiling(22 * number * (
            (pow_ + def_break * 0.85) * rate / 50 * hit / (hit + 35) + 2
        ))
        denom_armor = armor_coef - armor
        if denom_armor == 0:
            denom_armor = 1e-9
        guard = (
            0.25
            * (bround(number * max_life)
               * (35 + dodge) / 35
               * armor_coef / denom_armor
               * (math.trunc(tenacity / 100) + 1.0 - 0.6 / 100)
               + 100)
            * (defence * 2 - defence * def_percent / 100 + 1200 * 2)
            / (defence - defence * def_percent / 100 + 1200)
            / 2
        )
        individual = ceiling(float(char_type.get("effect_ratio") or 0) * (attack + ceiling(guard)))
        detail[unit["rowId"]] = individual
        total += individual
    return total, detail


# --------------------------------------------------------------------------- #
# 名称解析
# --------------------------------------------------------------------------- #
def resolve_enemy_char_name(char_type, text):
    if not char_type:
        return "?"
    return text.get("enemy_character_type", char_type.get("name", ""), char_type.get("code") or "?")


def resolve_ally_name(ally, text):
    name_key = ally.get("name", "")
    name = text.get("ally_team", name_key)
    if name:
        return name
    match = re.search(r"team-(\d+)", name_key)
    return "[team-{}]".format(match.group(1)) if match else "[{}]".format(name_key)


def resolve_gun_name(gun_id, guns, text):
    gun = guns.get(int(gun_id))
    if not gun:
        return "[gun-{}]".format(gun_id)
    return text.get("gun", gun.get("name", ""), "[{}]".format(gun_id))


def resolve_equip_name(equip_id, equips, text):
    equip = equips.get(int(equip_id))
    if not equip:
        return "[equip-{}]".format(equip_id)
    return text.get("equip", equip.get("name", ""), "[{}]".format(equip_id))


# --------------------------------------------------------------------------- #
# 主提取
# --------------------------------------------------------------------------- #
def extract(data_root, server, mission_id, turn):
    root = os.path.join(data_root, server)
    text = TextTables(root)

    missions = load_json(root, os.path.join("stc", "mission.json"))
    mission = next((m for m in missions if int(m["id"]) == int(mission_id)), None)
    if mission is None:
        raise SystemExit("mission {} 不存在于 {}".format(mission_id, root))

    spots_all = load_json(root, os.path.join("stc", "spot.json"))
    spots = [s for s in spots_all if int(s["mission_id"]) == int(mission_id)]
    if not spots:
        raise SystemExit("mission {} 没有点位数据".format(mission_id))

    enemy_teams = {int(t["id"]): t for t in load_json(root, os.path.join("stc", "enemy_team.json"))}
    enemy_in_team = load_json(root, os.path.join("stc", "enemy_in_team.json"))
    char_types = {int(c["id"]): c for c in load_json(root, os.path.join("stc", "enemy_character_type.json"))}
    std_attr = load_json(root, os.path.join("stc", "enemy_standard_attribute.json"))
    factors = build_level_factors(std_attr)
    team_ais = load_json(root, os.path.join("stc", "team_ai.json"))
    buildings = {int(b["id"]): b for b in load_json(root, os.path.join("stc", "building.json"))}
    allies = {int(a["id"]): a for a in load_json(root, os.path.join("stc", "ally_team.json"))}
    guns = {int(g["id"]): g for g in load_json(root, os.path.join("stc", "gun.json"))}
    gun_in_ally = {int(g["id"]): g for g in load_json(root, os.path.join("stc", "gun_in_ally.json"))}
    equips = {int(e["id"]): e for e in load_json(root, os.path.join("stc", "equip.json"))}
    auto_missions = {int(a["mission_id"]): a for a in load_json(root, os.path.join("stc", "auto_mission.json"))}
    win_cfg = {int(w["id"]): w for w in load_json(root, os.path.join("stc", "mission_win_type_config.json"))}

    units_by_team = {}
    for row in enemy_in_team:
        units_by_team.setdefault(int(row["enemy_team_id"]), []).append(row)

    def ai_name(team):
        if not team:
            return "?"
        if int(team.get("if_stay") or 0):
            ai_type, force_id = 999, 1
        elif int(team.get("ai") or 0) == 0:
            ai_type, force_id = int(mission.get("enemy_ai_type") or 0), 1
        else:
            ai_type, force_id = int(team["ai"]), 2
        for row in team_ais:
            if int(row["force_id"]) == force_id and int(row["ai_type"]) == ai_type:
                return text.get("team_ai", row.get("name", ""), row.get("name"))
        return "?"

    def make_units(team_id, level_offset=0):
        units = []
        for row in units_by_team.get(int(team_id), []):
            char_type = char_types.get(int(row["enemy_character_type_id"]))
            level = int(row["level"]) + level_offset
            if not char_type:
                continue
            values = {
                "hp": bround(enemy_attribute(char_type, "maxlife", level, factors)),
                "pow": enemy_attribute(char_type, "pow", level, factors),
                "rate": enemy_attribute(char_type, "rate", level, factors),
                "hit": enemy_attribute(char_type, "hit", level, factors),
                "dodge": enemy_attribute(char_type, "dodge", level, factors),
                "range": enemy_attribute(char_type, "range", level, factors),
                "speed": enemy_attribute(char_type, "speed", level, factors),
                "armorPiercing": enemy_attribute(char_type, "armor_piercing", level, factors),
                "armor": enemy_attribute(char_type, "armor", level, factors),
                "tenacity": char_type.get("tenacity"),
                "debuffResistance": char_type.get("debuff_resistance"),
                "shield": enemy_attribute(char_type, "shield", level, factors),
                "def": enemy_attribute(char_type, "def", level, factors),
            }
            units.append({
                "rowId": row["id"],
                "name": resolve_enemy_char_name(char_type, text),
                "code": char_type.get("code", ""),
                "charTypeId": int(row["enemy_character_type_id"]),
                "number": int(row["number"]),
                "level": level % 1000,
                "levelRaw": level,
                "defPercent": int(row["def_percent"]),
                "x": int(row["coordinator_x"]),
                "y": int(row["coordinator_y"]),
                "stats": values,
            })
        return units

    def team_ce(team_id, armor_coef=600, level_offset=0):
        units = make_units(team_id, level_offset)
        if not units:
            return 0, {}
        total, detail = team_combat_power(units, char_types, factors, armor_coef)
        return int(total), detail

    # ------------------------------------------------------------------ 关卡
    mission_name = text.get("mission", mission.get("name", ""), "[{}]".format(mission.get("name")))
    mission_desc = text.get("mission", mission.get("mission_describe", ""), "")
    auto_mission = auto_missions.get(int(mission_id))

    # 活动名：normal_activity 按 campaign_id 索引；子活动/章节：mission_event。
    activity_name = None
    for row in load_json(root, os.path.join("stc", "normal_activity.json")):
        if str(row.get("campaign_id")) == str(mission.get("campaign")):
            activity_name = text.get("normal_activity", row.get("name", ""), None)
            break
    sub_event_name = None
    for row in load_json(root, os.path.join("stc", "mission_event.json")):
        campaigns = [c.strip() for c in str(row.get("mission_campaign") or "").split(",")]
        if str(mission.get("campaign")) in campaigns:
            sub_event_name = text.get("mission_event", row.get("event_name", ""), None)
            break
    chapter, _, title = mission_name.partition("-")
    if not title:
        chapter, title = None, mission_name

    limit_team = str(mission.get("limit_team") or "")
    gk_limit, total_limit = (limit_team.split(",") + ["0"])[:2] if "," in limit_team else (limit_team, "0")

    def limit_text(value):
        value = int(value) if str(value).lstrip("-").isdigit() else 0
        if value == 0:
            return "不限"
        if value == -1:
            return "禁止"
        return str(value)

    win_conditions = []
    if int(mission.get("win_turn") or 0) != 0:
        win_conditions.append("坚守至第 {} 回合".format(mission["win_turn"]))
    elif str(mission.get("win_spot_id") or "0") not in ("0", ""):
        win_conditions.append("占领节点 {}".format(mission["win_spot_id"]))
    for win_id in [x for x in re.split(r"[|,]", str(mission.get("win_type") or "")) if x]:
        label = None
        try:
            cfg = win_cfg.get(int(win_id))
        except ValueError:
            cfg = None
        if cfg:
            extra = cfg.get("extra_language") or ""
            if extra:
                label = text.get("mission_win_type_config", extra)
        if not label:
            label = text.get("mission_win_type_config", "mission_win_type_config-1{}".format(win_id))
        win_conditions.append(label or "条件 {}".format(win_id))

    rewards = []
    try:
        prize_rows = load_json(root, os.path.join("catchdata", "mission_event_prize_info.json"))
        prize_table = prize_rows.get("mission_event_prize_info", []) if isinstance(prize_rows, dict) else []
        prize_link = next((p for p in prize_table if str(p.get("mission_id")) == str(mission_id)), None)
        if prize_link:
            prizes = {int(p["id"]): p for p in load_json(root, os.path.join("stc", "prize.json"))}
            prize = prizes.get(int(prize_link["prize_id"]))
            if prize:
                for key, label_text in (("mp", "资源"), ("core", "核心"), ("gem", "钻石")):
                    if prize.get(key) and str(prize[key]) != "0":
                        rewards.append("{} x{}".format(label_text, prize[key]))
    except FileNotFoundError:
        pass

    mission_info = {
        "id": int(mission["id"]),
        "name": mission_name,
        "title": title,
        "chapter": chapter,
        "activity": activity_name,
        "subEvent": sub_event_name,
        "description": mission_desc,
        "campaign": int(mission.get("campaign") or 0),
        "sub": int(mission.get("sub") or 0),
        "group": int(mission.get("mission_group_id") or 0),
        "night": int(mission.get("special_type") or 0) > 0,
        "endless": int(mission.get("endless_mode") or 0) > 0,
        "difficulty": int(mission.get("difficulty") or 0),
        "recommendLevel": int(mission.get("recommend_gun_level") or 0),
        "turnLimit": int(mission.get("turn_limit") or 0),
        "baseExp": int(mission.get("exp_parameter") or 0) * 10,
        "levelPenalty": (int(auto_mission["expect_gun_level"]) + 10) if auto_mission else None,
        "limits": {
            "gk": limit_text(gk_limit),
            "hoc": limit_text(mission.get("limit_squad")),
            "coalition": limit_text(mission.get("limit_sangvis")),
            "vehicle": limit_text(mission.get("limit_vehicle")),
            "total": ("{}（不含重装）".format(str(total_limit).lstrip("*"))
                      if "*" in str(total_limit) else limit_text(total_limit)),
        },
        "winConditions": win_conditions,
        "rewards": rewards,
        "mapRes": mission.get("map_res_name", ""),
        "mapInfo": mission.get("map_information", ""),
    }

    # ------------------------------------------------------------------ 点位
    building_rows = []
    seen_buildings = set()
    for spot in spots:
        bid = int(spot.get("building_id") or 0)
        if not bid or bid in seen_buildings:
            continue
        seen_buildings.add(bid)
        building = buildings.get(bid, {})
        notes = []
        working = str(building.get("working_special_spot") or "")
        for token in [t for t in re.split(r"[|;]", working) if t]:
            key = "special_spot_config-1{:07d}".format(int(token))
            label = text.get("special_spot_config", key) or text.get(
                "special_spot_config", "special_spot_config-2{:07d}".format(int(token)))
            if label:
                notes.append(label)
        building_rows.append({
            "spotId": int(spot["id"]),
            "id": bid,
            "name": text.get("building", building.get("name", ""), "[{}]".format(building.get("name", bid))),
            "code": building.get("code", ""),
            "type": building.get("type"),
            "defender": building.get("defender"),
            "destroy": BUILDING_DESTROY_LABEL.get(str(building.get("is_destroy")), building.get("is_destroy")),
            "assistRange": building.get("battle_assist_range"),
            "notes": "；".join(dict.fromkeys(notes)),
        })

    spot_rows = []
    for spot in sorted(spots, key=lambda s: int(s["id"])):
        spot_type = int(spot.get("type") or 0)
        spot_rows.append({
            "id": int(spot["id"]),
            "type": spot_type,
            "typeLabel": SPOT_TYPE_LABEL.get(spot_type, "类型 {}".format(spot_type)),
            "belong": int(spot.get("belong") or 0),
            "belongLabel": BELONG_LABEL.get(int(spot.get("belong") or 0), str(spot.get("belong"))),
            "x": int(spot.get("coordinator_x") or 0),
            "y": int(spot.get("coordinator_y") or 0),
            "route": [int(x) for x in str(spot.get("route") or "").split(",") if x],
            "enemyTeamId": int(spot.get("enemy_team_id") or 0),
            "allyTeamId": int(spot.get("ally_team_id") or 0),
            "buildingId": int(spot.get("building_id") or 0),
            "activeCycle": spot.get("active_cycle") or "",
            "randomGet": spot.get("random_get") or "0",
            "specialEft": int(spot.get("special_eft") or 0),
            "hostage": spot.get("hostage_info") or "",
        })

    # ------------------------------------------------------------------ 梯队
    teams = {}
    enemy_rows = []
    for spot in sorted(spots, key=lambda s: int(s["id"])):
        team_id = int(spot.get("enemy_team_id") or 0)
        ally_id = int(spot.get("ally_team_id") or 0)
        if not team_id and not ally_id:
            continue

        if team_id:
            team = enemy_teams.get(team_id, {})
            offset = parse_correction_turn(team.get("correction_turn")).get(int(turn), 0)
            units = make_units(team_id, offset)
            ce600, detail = team_ce(team_id, 600, offset)
            ce300, _ = team_ce(team_id, 300, offset)
            fake = int(team.get("effect_ext") or 0)
            leader_type = char_types.get(int(team.get("enemy_leader") or 0))
            composition = {}
            for unit in units:
                composition[unit["name"]] = composition.get(unit["name"], 0) + unit["number"]
            drops = [resolve_gun_name(g, guns, text) for g in str(team.get("limit_guns") or "").split(",") if g and g != "0"]
            drops += [resolve_equip_name(e, equips, text) for e in str(team.get("limit_equips") or "").split(",") if e and e != "0"]
            teams[team_id] = {
                "id": team_id,
                "leader": resolve_enemy_char_name(leader_type, text),
                "ce": abs(fake) if fake else ce600,
                "ce600": ce600,
                "ce300": ce300,
                "fakeCe": bool(fake),
                "units": units,
                "unitCe": detail,
            }
            enemy_rows.append({
                "spotId": int(spot["id"]),
                "teamId": team_id,
                "kind": "enemy",
                "alignment": "敌方",
                "ai": ai_name(team),
                "composition": ["{} x{}".format(name, count) for name, count in composition.items()],
                "drops": drops,
            })
        else:
            ally = allies.get(ally_id, {})
            if int(ally.get("initial_type") or 0) == 1:
                squad = [gun_in_ally[int(g)] for g in str(ally.get("guns") or "").split(",")
                         if g.isdigit() and int(g) in gun_in_ally]
                names = [resolve_gun_name(row["gun_id"], guns, text) for row in squad]
                leader_row = next((row for row in squad if int(row.get("location") or 0) == 1), squad[0] if squad else None)
                teams[ally_id] = {
                    "id": ally_id,
                    "leader": resolve_gun_name(leader_row["gun_id"], guns, text) if leader_row else "?",
                    "ce": None,
                    "ce600": None,
                    "ce300": None,
                    "fakeCe": False,
                    "units": [],
                    "unitCe": {},
                }
                enemy_rows.append({
                    "spotId": int(spot["id"]),
                    "teamId": ally_id,
                    "kind": "ally",
                    "alignment": "可控友军",
                    "ai": "可控",
                    "composition": names,
                    "drops": [],
                })
            else:
                # 第三方阵营：数据里挂在 ally_team 上，但实际按敌方梯队结算。
                team = enemy_teams.get(ally_id, {})
                offset = parse_correction_turn(team.get("correction_turn")).get(int(turn), 0)
                units = make_units(ally_id, offset)
                ce600, detail = team_ce(ally_id, 600, offset)
                ce300, _ = team_ce(ally_id, 300, offset)
                fake = int(team.get("effect_ext") or 0)
                composition = {}
                for unit in units:
                    composition[unit["name"]] = composition.get(unit["name"], 0) + unit["number"]
                teams[ally_id] = {
                    "id": ally_id,
                    "leader": resolve_enemy_char_name(char_types.get(int(team.get("enemy_leader") or 0)), text),
                    "ce": abs(fake) if fake else ce600,
                    "ce600": ce600,
                    "ce300": ce300,
                    "fakeCe": bool(fake),
                    "units": units,
                    "unitCe": detail,
                }
                enemy_rows.append({
                    "spotId": int(spot["id"]),
                    "teamId": ally_id,
                    "kind": "third",
                    "alignment": resolve_ally_name(ally, text),
                    "ai": ai_name(team),
                    "composition": ["{} x{}".format(name, count) for name, count in composition.items()],
                    "drops": [],
                })

    # ------------------------------------------------------------------ 传送
    portals = []
    for spot in spots:
        raw = str(spot.get("auto_teleport") or "")
        if not raw:
            continue
        match = re.match(r"^(\d+):0$", raw) or re.match(r"^(\d+)\|(\d*)\|1:", raw)
        if not match:
            continue
        portals.append({
            "from": int(spot["id"]),
            "to": int(match.group(1)),
            "buildingId": int(match.group(2)) if match.lastindex and match.lastindex >= 2 and match.group(2) else 0,
        })

    return {
        "generatedAt": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "server": server,
        "turn": int(turn),
        "mission": mission_info,
        "spots": spot_rows,
        "enemyRows": enemy_rows,
        "teams": list(teams.values()),
        "buildings": building_rows,
        "portals": portals,
        "stats": {
            "spots": len(spot_rows),
            "enemyTeams": len({r["teamId"] for r in enemy_rows if r["kind"] != "ally"}),
            "enemySpots": len([r for r in enemy_rows if r["kind"] != "ally"]),
            "allySpots": len([r for r in enemy_rows if r["kind"] == "ally"]),
            "buildings": len(building_rows),
            "portals": len(portals),
            "units": sum(len(t["units"]) for t in teams.values()),
        },
    }


def update_index(out_dir, mission_id, mission_name):
    index_path = os.path.join(out_dir, "index.json")
    entries = []
    if os.path.exists(index_path):
        try:
            with open(index_path, encoding="utf-8") as f:
                entries = json.load(f)
        except (json.JSONDecodeError, OSError):
            entries = []
    entries = [e for e in entries if int(e.get("missionId", -1)) != int(mission_id)]
    entries.append({"missionId": int(mission_id), "name": mission_name, "file": "mission-{}.json".format(mission_id)})
    # 新图在前：任务 ID 越大通常越新，页面默认打开第一张
    entries.sort(key=lambda e: e["missionId"], reverse=True)
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def main(argv=None):
    parser = argparse.ArgumentParser(description="提取单张 GFL 地图的表格数据")
    parser.add_argument("--mission", nargs="+", type=int, default=[DEFAULT_MISSION], help="任务 ID（可多个）")
    parser.add_argument("--data-root", default=DEFAULT_DATA_ROOT, help="GFLData 目录")
    parser.add_argument("--server", default="ch", help="数据服：ch/en/jp/kr/tw")
    parser.add_argument("--turn", type=int, default=1, help="用于计算 correction_turn 等级偏移的回合数")
    parser.add_argument("--out", default=DEFAULT_OUT, help="输出目录")
    args = parser.parse_args(argv)

    if not os.path.isdir(os.path.join(args.data_root, args.server)):
        raise SystemExit("找不到数据目录：{}".format(os.path.join(args.data_root, args.server)))

    os.makedirs(args.out, exist_ok=True)
    for mission_id in args.mission:
        sys.stdout.write("extract mission {} ... ".format(mission_id))
        sys.stdout.flush()
        result = extract(args.data_root, args.server, mission_id, args.turn)
        out_path = os.path.join(args.out, "mission-{}.json".format(mission_id))
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        update_index(args.out, mission_id, result["mission"]["name"])
        stats = result["stats"]
        try:
            shown_path = os.path.relpath(out_path, HERE)
        except ValueError:  # --out 在另一个盘符上
            shown_path = out_path
        print("ok  {} 节点 / {} 梯队 / {} 建筑 -> {}".format(
            stats["spots"], stats["enemyTeams"], stats["buildings"], shown_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
