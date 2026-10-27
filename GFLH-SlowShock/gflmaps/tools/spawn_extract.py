#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 S2C_Mission_teamMove / S2C_Mission_startTurn 抓包转成地图提示用的刷怪数据。

要点：
  * enemy_instance_info 的 key 就是初始敌方 1..28 的【行动优先级】，渲染时直接当编号用。
  * ally_instance_info 里 ally_type == "2" 且不在静态点位里的，是本回合从传送点刷出来的敌人，
    它们的点位写在 ai_para 里，形如 "@67672,99"。
  * 夜战里 spot_act_info 只包含视野内的点位，所以初始敌人不能只靠它定位，优先用 ai_para，
    其次 night_enemy 的 from_spot_id，最后才按"同怪组按点位 id 升序"回填。

用法：
    python spawn_extract.py --mission 11403 ^
        --team-move "D:\\Github\\GFLH\\GFLH-SlowShock\\0039_S2C_4000_Mission_teamMove_1792629961.json" ^
        --start-turn "D:\\Github\\GFLH\\GFLH-SlowShock\\0189_S2C_5000_Mission_startTurn_1793005345.json"

输出：<repo>/gflmaps/data/spawn/mission-<id>.json
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
GFLMAPS = os.path.dirname(HERE)
DEFAULT_OUT = os.path.join(GFLMAPS, "data", "spawn")
DEFAULT_DATA_ROOT = os.path.normpath(os.path.join(HERE, "..", "..", "GFLData"))

SPOT_RE = re.compile(r"@(\d+)")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def parse_spot(ai_para):
    """从 '@67672,99' 里取出 67672。"""
    if not ai_para:
        return None
    match = SPOT_RE.search(str(ai_para))
    return int(match.group(1)) if match else None


def load_static_spots(data_root, server, mission_id):
    spots = load(os.path.join(data_root, server, "stc", "spot.json"))
    return [s for s in spots if int(s["mission_id"]) == int(mission_id)]


def build_capture_index(capture):
    """把一个抓包里跟定位相关的数据整理成查找表。"""
    night_enemy = {}
    for row in capture.get("night_enemy") or []:
        try:
            night_enemy[int(row["enemy_instance_id"])] = int(row["from_spot_id"])
        except (KeyError, TypeError, ValueError):
            continue

    visible_by_team = {}
    for row in capture.get("spot_act_info") or []:
        try:
            team_id = int(row.get("enemy_team_id") or 0)
            spot_id = int(row.get("spot_id") or 0)
        except (TypeError, ValueError):
            continue
        if team_id and spot_id:
            visible_by_team.setdefault(team_id, set()).add(spot_id)

    return {"nightEnemy": night_enemy, "visibleByTeam": visible_by_team}


def resolve_initial(capture, static_spots, index):
    """enemy_instance_info -> 带点位的初始敌人列表（按编号排序）。"""
    # 静态点位里每个怪组占的点（升序），用于给没有 ai_para 的实例回填
    spots_by_team = {}
    for spot in static_spots:
        team_id = int(spot.get("enemy_team_id") or 0)
        if team_id:
            spots_by_team.setdefault(team_id, []).append(int(spot["id"]))
    for team_id in spots_by_team:
        spots_by_team[team_id].sort()

    by_team = {}
    for key, row in (capture.get("enemy_instance_info") or {}).items():
        try:
            instance_id = int(key)
            team_id = int(row.get("enemy_team_id") or 0)
        except (TypeError, ValueError):
            continue
        by_team.setdefault(team_id, []).append((instance_id, row))

    result = []
    used = set()
    for team_id, entries in by_team.items():
        entries.sort(key=lambda item: item[0])
        candidates = [s for s in spots_by_team.get(team_id, []) if s not in used]
        for instance_id, row in entries:
            ai_para = row.get("enemy_ai_para") or ""
            spot_id = parse_spot(ai_para)
            how = "ai_para"

            if spot_id is None:
                spot_id = index["nightEnemy"].get(instance_id)
                how = "night_enemy"

            if spot_id is None:
                visible = [s for s in index["visibleByTeam"].get(team_id, []) if s not in used]
                if len(visible) == 1:
                    spot_id, how = visible[0], "spot_act_info"

            if spot_id is None and candidates:
                spot_id, how = candidates[0], "team_order"

            if spot_id is not None:
                used.add(spot_id)
                candidates = [s for s in candidates if s != spot_id]

            result.append({
                "instanceId": instance_id,
                "teamId": team_id,
                "spotId": spot_id,
                "birthTurn": int(row.get("enemy_birth_turn") or 0),
                "ai": int(row.get("enemy_ai") or 0),
                "aiPara": ai_para,
                "hpPercent": row.get("enemy_hp_percent", 1),
                "bossHp": row.get("boss_hp", "0"),
                "resolvedBy": how if spot_id is not None else "unplaced",
            })

    result.sort(key=lambda item: item["instanceId"])
    return result


def resolve_spawns(capture, static_ally_ids):
    """ally_instance_info 里从传送点刷出来的敌人（ally_type == 2）。"""
    result = []
    for key, row in (capture.get("ally_instance_info") or {}).items():
        if str(row.get("ally_type")) != "2":
            continue
        try:
            ally_id = int(row.get("ally_instance_id") or key)
            team_id = int(row.get("ally_team_id") or 0)
            enemy_id = int(row.get("ally_enemy") or 0)
        except (TypeError, ValueError):
            continue
        if not team_id or enemy_id != team_id:
            continue
        # 静态点位上的第三方梯队（归在 ally_team 表里）不算刷怪
        if team_id in static_ally_ids:
            continue
        spot_id = parse_spot(row.get("ai_para"))
        if spot_id is None:
            continue
        result.append({
            "instanceId": int(key),
            "allyInstanceId": ally_id,
            "teamId": team_id,
            "spotId": spot_id,
            "birthTurn": 0,
            "ai": int(row.get("ai") or 0),
            "aiPara": row.get("ai_para") or "",
            "resolvedBy": "ai_para",
        })
    result.sort(key=lambda item: item["instanceId"])
    return result


def resolve_third_party(capture, static_ally_ids):
    """开局就在静态点位上的第三方梯队（特洛伊这类）。

    它们不算“传送点刷新”，但确实在 ally_instance_info 里、也确实占着一个点位，
    所以单独归一类，让地图上同样有标记和悬停信息。
    """
    result = []
    for key, row in (capture.get("ally_instance_info") or {}).items():
        if str(row.get("ally_type")) != "2":
            continue
        try:
            ally_id = int(row.get("ally_instance_id") or key)
            team_id = int(row.get("ally_team_id") or 0)
            enemy_id = int(row.get("ally_enemy") or 0)
        except (TypeError, ValueError):
            continue
        if not team_id or team_id != enemy_id or team_id not in static_ally_ids:
            continue
        spot_id = parse_spot(row.get("ai_para"))
        if spot_id is None:
            continue
        result.append({
            "instanceId": int(key),
            "allyInstanceId": ally_id,
            "teamId": team_id,
            "spotId": spot_id,
            "birthTurn": 0,
            "ai": int(row.get("ai") or 0),
            "aiPara": row.get("ai_para") or "",
            "resolvedBy": "ai_para",
        })
    result.sort(key=lambda item: item["instanceId"])
    return result


def diff_start_turn(spawns, capture, static_ally_ids):
    """2T 的 startTurn 只用来核对：同一批传送点上换了一批怪组，不参与 1T 渲染。"""
    current = {(s["teamId"], s["spotId"]) for s in spawns}
    later = set()
    for row in (capture.get("ally_instance_info") or {}).values():
        if str(row.get("ally_type")) != "2":
            continue
        try:
            team_id = int(row.get("ally_team_id") or 0)
        except (TypeError, ValueError):
            continue
        if not team_id or team_id in static_ally_ids:
            continue
        spot_id = parse_spot(row.get("ai_para"))
        if spot_id is not None:
            later.add((team_id, spot_id))
    return {
        "laterTurnOnly": sorted({t for t, _ in later - current}),
        "sameSpotsDifferentTeam": sorted({s for _, s in later - current}),
        "stillThere": len(later & current),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="生成地图刷怪数据")
    parser.add_argument("--mission", type=int, required=True)
    parser.add_argument("--team-move", required=True, help="S2C_Mission_teamMove 抓包")
    parser.add_argument("--start-turn", default=None, help="S2C_Mission_startTurn 抓包（可选）")
    parser.add_argument("--data-root", default=DEFAULT_DATA_ROOT)
    parser.add_argument("--server", default="ch")
    parser.add_argument("--out", default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    capture = load(args.team_move)
    static_spots = load_static_spots(args.data_root, args.server, args.mission)
    if not static_spots:
        raise SystemExit("任务 {} 在 {} 下没有静态点位".format(args.mission, args.data_root))

    static_ally_ids = {int(s.get("ally_team_id") or 0) for s in static_spots} - {0}

    index = build_capture_index(capture)
    initial = resolve_initial(capture, static_spots, index)
    spawns = resolve_spawns(capture, static_ally_ids)
    third_party = resolve_third_party(capture, static_ally_ids)

    sources = [os.path.basename(args.team_move)]
    later_note = None
    if args.start_turn:
        extra = load(args.start_turn)
        later_note = diff_start_turn(spawns, extra, static_ally_ids)
        sources.append(os.path.basename(args.start_turn))

    spots_json = {int(s["id"]): s for s in static_spots}
    unknown_spots = [e["spotId"] for e in initial + spawns + third_party
                     if e["spotId"] is not None and e["spotId"] not in spots_json]
    unplaced = [e for e in initial if e["spotId"] is None]

    payload = {
        "missionId": args.mission,
        "turn": 1,
        "generatedAt": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "sources": sources,
        "initial": [e for e in initial if e["spotId"] is not None],
        "spawns": spawns,
        "third": third_party,
        "unplaced": [
            {"instanceId": e["instanceId"], "teamId": e["teamId"], "reason": "no spot id in packet or static data"}
            for e in unplaced
        ],
        "laterTurn": later_note,
        "stats": {
            "initial": len([e for e in initial if e["spotId"] is not None]),
            "spawns": len(spawns),
            "third": len(third_party),
            "unplaced": len(unplaced),
        },
    }

    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, "mission-{}.json".format(args.mission))
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    print("initial: {initial}  spawns: {spawns}  third: {third}  unplaced: {unplaced}".format(**payload["stats"]))
    if unplaced:
        print("unplaced instances: {}".format(", ".join(str(e["instanceId"]) for e in unplaced)))
    if unknown_spots:
        print("!! spots not in mission {}: {}".format(args.mission, sorted(set(unknown_spots))))
    print("->", os.path.relpath(out_path, GFLMAPS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
