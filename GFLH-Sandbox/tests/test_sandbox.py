"""smoke tests for GFLH-Sandbox core (sandbox.py), against the two captured packets."""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import sandbox as sb  # noqa: E402

FAILURES = []


def check(label, cond, detail=""):
    print("  %s  %s%s" % ("PASS" if cond else "FAIL", label, (" " + str(detail)) if detail else ""))
    if not cond:
        FAILURES.append(label)


def load(name):
    return json.load(io.open(os.path.join(ROOT, name), encoding="utf-8"))


# ------------------------------------------------------------------ data integrity
print("[1] 数据表完整性")
check("17 个隐藏点都映射到区域", len(sb.SPOT_REGION) == 17, len(sb.SPOT_REGION))
EXPECTED_SPOTS = [str(s) for s in
                  [88895] + list(range(88896, 88908)) + list(range(88912, 88916))]
check("SPOT_REGION 覆盖 17 个隐藏点",
      sorted(sb.SPOT_REGION) == sorted(EXPECTED_SPOTS),
      sorted(sb.SPOT_REGION))
check("怪组表无缺漏（31 个怪组）", len(sb.TEAM_TABLE) == 31, len(sb.TEAM_TABLE))

# 效能与 README 表格一致
spot_checks = {
    "770021": 14984, "770022": 15077,
    "770026": 35135, "770027": 35073, "770028": 35071,
    "770039": 60490, "770040": 60402, "770041": 59909,
    "770023": 35007, "770024": 35306, "770025": 35469,
    "770036": 60211, "770037": 60300, "770038": 60387,
    "770029": 55221, "770030": 55261, "770031": 55350,
    "770042": 90263, "770043": 89958, "770044": 90294, "770045": 90450,
    "770032": 34944, "770033": 35032,
    "770046": 65026, "770047": 65131,
    "770034": 60283, "770035": 60039,
    "770048": 100466, "770049": 99981, "770050": 100196,
    "770061": 150000,
}
for tid, power in spot_checks.items():
    check("怪组 %s 效能 %d" % (tid, power),
          tid in sb.TEAM_TABLE and sb.TEAM_TABLE[tid][2] == power,
          sb.TEAM_TABLE.get(tid))

# ------------------------------------------------------------------ classify
print("[2] 档位分类")
check("左下区 770021=低 770022=高",
      sb.classify("770021")[4] == "低" and sb.classify("770022")[4] == "高")
check("右下区 1-4 770023=低 770025=高 770024=中",
      sb.classify("770023")[4] == "低" and sb.classify("770025")[4] == "高"
      and sb.classify("770024")[4] == "中")
check("左上区 1-4 770026=高 770028=低 770027=中",
      sb.classify("770026")[4] == "高" and sb.classify("770028")[4] == "低"
      and sb.classify("770027")[4] == "中")
check("左上区 5-7 770039=高 770040=高(分差9分) 770041=低",
      sb.classify("770039")[4] == "高" and sb.classify("770040")[4] == "高"
      and sb.classify("770041")[4] == "低")
# README 的「9 分」是击杀分数（效能×10%）差，不是效能差
check("60490 与 60402 的击杀分数相差 9 分",
      sb.score_of(60490) == 6049 and sb.score_of(60402) == 6040
      and sb.score_of(60490) - sb.score_of(60402) == 9,
      (sb.score_of(60490), sb.score_of(60402)))
check("分数 = 效能 × 10%（向下取整）",
      sb.score_of(150000) == 15000 and sb.score_of(14984) == 1498
      and sb.score_of(None) is None)
check("右上区 5-7 770045=高 770043=低 770044=中",
      sb.classify("770045")[4] == "高" and sb.classify("770043")[4] == "低"
      and sb.classify("770044")[4] == "中")
check("右上顶点 770061=高(150000)", sb.classify("770061")[4] == "高")
check("未知怪组返回 None", sb.classify("999999") is None)

# ------------------------------------------------------------------ turn detect
print("[3] 回合检测")
d1 = load("1T结束_S2C_4000_Mission_startMission_1792545701.json")
d2 = load("2T结束_S2C_4000_Mission_startTurn_1792545992.json")
check("1T 包检测为 1", sb.detect_turn(d1) == 1, sb.detect_turn(d1))
check("2T 包检测为 2", sb.detect_turn(d2) == 2, sb.detect_turn(d2))
check("空数据返回 None", sb.detect_turn({}) is None)
check("窗口映射 1-4 / 5-7",
      sb.window_of_turn(1) == "1-4" and sb.window_of_turn(4) == "1-4"
      and sb.window_of_turn(5) == "5-7" and sb.window_of_turn(7) == "5-7")

# ------------------------------------------------------------------ parse
print("[4] 隐藏点解析")
s1 = sb.parse_hidden_spots(d1)
s2 = sb.parse_hidden_spots(d2)
check("1T 解析出 16 个隐藏点", len(s1) == 16, len(s1))
check("2T 解析出 16 个隐藏点", len(s2) == 16, len(s2))
check("解析结果包含 spot/team/region/power/tier",
      all(all(k in s for k in ("spot_id", "team_id", "region", "power", "tier"))
          for s in s1 + s2))

# 1T 特定点校验
by_spot = {s["spot_id"]: s for s in s1}
check("1T spot 88899 team=770024 效能=35306",
      by_spot["88899"]["team_id"] == "770024" and by_spot["88899"]["power"] == 35306)
check("1T spot 88914 team=770035 区域=边缘正右/正上",
      by_spot["88914"]["team_id"] == "770035"
      and by_spot["88914"]["region"] == "边缘正右/正上")

c1, r1 = sb.summarize(s1)
c2, r2 = sb.summarize(s2)
check("1T 高=4 中=4 低=8", (c1["高"], c1["中"], c1["低"]) == (4, 4, 8), c1)
check("2T 高=11 中=2 低=3", (c2["高"], c2["中"], c2["低"]) == (11, 2, 3), c2)

# 非 mission 数据不产出结果
check("无 allyteam_summoner 时返回空", sb.parse_hidden_spots({}) == [])

# ------------------------------------------------------------------ 建议关注区域
print("[5] 建议关注区域")
check("1-4T 关注区域 = 右下区 / 边缘正右正上",
      sb.focus_regions(1) == ["内圈右下区", "边缘正右/正上"]
      and sb.focus_regions(4) == ["内圈右下区", "边缘正右/正上"])
check("5-7T 关注区域含左上/右上/边缘/顶点",
      sb.focus_regions(5) == ["内圈左上区", "内圈右上区", "边缘正右/正上", "右上顶点"])
check("未知回合无关注区域", sb.focus_regions(None) == [])

# order_regions：关注区域按优先级在前，其它在后
c1, r1 = sb.summarize(s1)
focus, others = sb.order_regions(r1.keys(), 1)
check("order_regions 关注区域排在前面且顺序正确",
      focus == ["内圈右下区", "边缘正右/正上"], focus)
check("order_regions 其它区域不丢失",
      sorted(focus + others) == sorted(r1.keys()), (focus, others))

# order_spots：关注区域的隐藏点排在最前
ordered = sb.order_spots(s1, 1)
regions_first = [s["region"] for s in ordered]
first_two = set(regions_first[:len([s for s in s1 if s["region"] in
                                    ("内圈右下区", "边缘正右/正上")])])
check("order_spots 关注区域的点排在最前",
      first_two == {"内圈右下区", "边缘正右/正上"}, regions_first)
check("order_spots 不丢点", len(ordered) == len(s1))

# focus_high_count：只数关注区域里的「高」
# 1T 关注区 = 内圈右下区(高1) + 边缘正右/正上(高0) = 1
check("1T 建议关注区域高效能数 = 1",
      sb.focus_high_count(s1, 1) == 1, sb.focus_high_count(s1, 1))
# 2T 关注区 = 内圈右下区(高2) + 边缘正右/正上(高2) = 4
check("2T 建议关注区域高效能数 = 4",
      sb.focus_high_count(s2, 2) == 4, sb.focus_high_count(s2, 2))
check("关注区域高效能数不超过全部高效能数",
      sb.focus_high_count(s1, 1) <= c1["高"] and sb.focus_high_count(s2, 2) <= c2["高"])

# 已移除的两个分数合计不应再存在
check("已移除 total_score / high_score",
      not hasattr(sb, "total_score") and not hasattr(sb, "high_score"))

# ------------------------------------------------------------------ 右上顶点
print("[6] 右上顶点（与其他区域共用怪组编号）")


def fake_packet(spot_id, team_id, turn):
    return {
        "fairy_skill_on_spot": {spot_id: {"1": {"start_turn": turn}}},
        "fairy_skill_return": {"allyteam_summoner": [
            {"spot_id": int(spot_id), "ally_instance_info": {"ally_enemy": team_id}},
        ]},
    }


v4 = sb.parse_hidden_spots(fake_packet("88895", "770061", 4))[0]
check("4T 右上顶点 = 770061 拉普拉斯妖 150000 分档高",
      v4["region"] == "右上顶点" and v4["window"] == "4"
      and v4["power"] == 150000 and v4["score"] == 15000 and v4["tier"] == "高", v4)

v6 = sb.parse_hidden_spots(fake_packet("88895", "770048", 6))[0]
check("5-7T 右上顶点的 770048 归到右上顶点（不被边缘正右/正上抢走）",
      v6["region"] == "右上顶点" and v6["window"] == "5-7", v6)
check("右上顶点 5-7T 三只涅托组按本区域分档",
      sb.classify("770048", "右上顶点")[4] == "高"
      and sb.classify("770049", "右上顶点")[4] == "低"
      and sb.classify("770050", "右上顶点")[4] == "中")

edge = sb.parse_hidden_spots(fake_packet("88914", "770048", 6))[0]
check("88914 的 770048 仍归到边缘正右/正上",
      edge["region"] == "边缘正右/正上" and edge["window"] == "5-7", edge)
check("同一怪组在两个区域都能查到效能",
      sb.classify("770048", "右上顶点")[2] == 100466
      and sb.classify("770048", "边缘正右/正上")[2] == 100466)
check("区域里没有的怪组返回 None",
      sb.classify("770061", "边缘正右/正上") is None)

# 当前口径：右上顶点只列入 5-7T 关注（README 原话），4T 不列入
check("4T 关注区域不含右上顶点（按 README 口径）",
      "右上顶点" not in sb.focus_regions(4), sb.focus_regions(4))

print()
print("=" * 60)
if FAILURES:
    print("FAILED %d: %s" % (len(FAILURES), ", ".join(FAILURES)))
    sys.exit(1)
print("ALL CHECKS PASSED")
