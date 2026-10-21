# sandbox.py
# 静默沙盘 · 隐藏点刷怪监视 —— 共享核心（数据 + 解析 + 分类）
#
# 供 GFLH-Sandbox 控制台与 GUI 复用。
#
# 数据来源：README.md 与 隐藏点.et（已转出 CSV 核对）。
# 玩法：击杀敌人获得其「基础效能」10% 的分数，因此分数上限取决于刷新敌人的效能。
# 隐藏点每个回合都会显示「该回合结束时将会出现的敌人」：
#   1T 的隐藏点数据在 S2C Mission/startMission 里，
#   2T~7T 的在 S2C Mission/startTurn 里（fairy_skill_return.allyteam_summoner）。
#
# 隐藏点共 17 个（spot 88895 + 88896~88915）。本文件把
#   spot_id -> 区域 -> (回合窗口 -> 怪组) -> 基础效能
# 全部固化，见 REGIONS / TEAM_TABLE。

# ============================================================
# 区域与隐藏点
# ============================================================
# spot_id -> 区域名
SPOT_REGION = {
    # 地图内圈
    "88896": "内圈左下区",
    "88897": "内圈左下区",
    "88898": "内圈左下区",
    "88899": "内圈右下区",
    "88900": "内圈右下区",
    "88901": "内圈右下区",
    "88902": "内圈左上区",
    "88903": "内圈左上区",
    "88904": "内圈左上区",
    "88905": "内圈右上区",
    "88906": "内圈右上区",
    "88907": "内圈右上区",
    # 地图边缘
    "88912": "边缘正左/正下",
    "88913": "边缘正左/正下",
    "88914": "边缘正右/正上",
    "88915": "边缘正右/正上",
    # 右上顶点 (10,10)：4T 才有，怪组 770061 拉普拉斯妖×1，效能 150000
    "88895": "右上顶点",
}

# ============================================================
# 怪组表：区域 -> 回合窗口 -> {team_id: (基础效能, 配置说明)}
#
# 之所以以「区域 + 窗口」为第一层（而不是以 team_id 为键），是因为同一个怪组
# 可能同时出现在多个区域：770048/770049/770050 就同时是
#   「边缘正右/正上 5-7T」和「右上顶点 5-7T」的怪组。
# 区域由隐藏点 spot_id 决定（见 SPOT_REGION），怪组只负责提供效能与配置。
# ============================================================
REGION_TEAMS = {
    # 内圈左下区（1～7T 两组轮换）
    "内圈左下区": {
        "1-7": {
            "770021": (14984, "加尔姆×5 警备士×10 射击士×15"),
            "770022": (15077, "独眼巨人_SG×15 独眼巨人_MG×10 独眼巨人_AR×5"),
        },
    },
    # 内圈左上区
    "内圈左上区": {
        "1-4": {
            "770026": (35135, "重锤士×15 拔摩之笔×1 重炮士×15"),
            "770027": (35073, "特洛伊×2 拉冬×1 掷弹士×1 机巧士×2 加尔姆×5"),
            "770028": (35071, "加尔姆×10 圣歌风琴×4 机巧士×1"),
        },
        "5-7": {
            "770039": (60490, "欧特鲁斯×10 光炮士×3 灵蛇权杖×10 捍卫者×1"),
            "770040": (60402, "防卫者×15 圣歌风琴×4 肯陶罗斯×5"),
            "770041": (59909, "欧特鲁斯×5 圣歌风琴×1 加尔姆×10 重炮士×20"),
        },
    },
    # 内圈右下区
    "内圈右下区": {
        "1-4": {
            "770023": (35007, "角斗士×2 侦察士×1 掷弹士×4"),
            "770024": (35306, "巨剑士×6 加尔姆×15 剑盾士×8"),
            "770025": (35469, "汉尼拔×3 指挥士×1 重炮士×15"),
        },
        "5-7": {
            "770036": (60211, "拉冬×1 圣歌风琴×2 机巧士×2 莱卡翁×1 加尔姆×10"),
            "770037": (60300, "雷金×10 特洛伊×2 进阶侦察士×2 进阶巨剑士×3 重锤士×5"),
            "770038": (60387, "赫瑞德玛×2 指挥士×1 进阶剑盾士×8 进阶重炮士×15"),
        },
    },
    # 内圈右上区
    "内圈右上区": {
        "1-4": {
            "770029": (55221, "欧特鲁斯×10 圣歌风琴×2 机巧士×1 加尔姆×5 肯陶罗斯×10"),
            "770030": (55261, "弥诺陶洛斯×2 汉尼拔×1 掷弹士×3 埃奎斯×2"),
            "770031": (55350, "重锤士×10 指挥士×1 雷金×10 欧特×20"),
        },
        "5-7": {
            "770042": (90263, "弥诺陶洛斯×2 拔摩之笔×1 汉尼拔×1 角斗士×2 阿拉克涅×1 掷弹士×2"),
            "770043": (89958, "安德瓦利×8 指挥士×1 圣歌风琴×6"),
            "770044": (90294, "帕拉丁×2 掷弹士×2 光炮士×2 灵蛇权杖×10 捍卫者×1"),
            "770045": (90450, "拉冬×1 九头蛇×4 特洛伊×2 进阶侦察士×1 埃奎斯×2 机巧士×2"),
        },
    },
    # 地图边缘 正左/正下
    "边缘正左/正下": {
        "1-4": {
            "770032": (34944, "赫瑞德玛×2 卫戍军-AR×15 卫戍军-RF×10"),
            "770033": (35032, "九头蛇×16 欧特鲁斯×15"),
        },
        "5-7": {
            "770046": (65026, "雷金×10 巨剑士×6 进阶巨剑士×6 欧特×10"),
            "770047": (65131, "欧特鲁斯×10 剑盾士×8 进阶剑盾士×8 进阶重炮士×10"),
        },
    },
    # 地图边缘 正右/正上
    "边缘正右/正上": {
        "1-4": {
            "770034": (60283, "帕拉丁×2 机巧士×2 莱卡翁×3 捍卫者×1"),
            "770035": (60039, "圣盾_GA_SWAP×10 奎乌×2 圣歌风琴×3 加尔姆×5"),
        },
        "5-7": {
            "770048": (100466, "涅托辅翼×1 涅托怒锤×15 涅托巡卫×15 涅托鹰眼×12"),
            "770049": (99981, "涅托怒锤×20 涅托辅翼×1 涅托鹰眼×20"),
            "770050": (100196, "涅托巡卫×20 涅托辅翼×1 涅托鹰眼×20"),
        },
    },
    # 右上顶点 (10,10)：4T 刷拉普拉斯妖，5-7T 刷涅托组（与边缘正右/正上同怪组编号）
    "右上顶点": {
        "4": {
            "770061": (150000, "拉普拉斯妖×1"),
        },
        "5-7": {
            "770048": (100466, "涅托辅翼×1 涅托怒锤×15 涅托巡卫×15 涅托鹰眼×12"),
            "770049": (99981, "涅托怒锤×20 涅托辅翼×1 涅托鹰眼×20"),
            "770050": (100196, "涅托巡卫×20 涅托辅翼×1 涅托鹰眼×20"),
        },
    },
}

# 兼容用的扁平表：team_id -> (首个出现区域, 窗口, 效能, 配置)。
# 同一怪组出现在多个区域时（770048~770050），仅作反查参考，
# 实际解析一律以 REGION_TEAMS[区域] 为准。
TEAM_TABLE = {}
for _region, _windows in REGION_TEAMS.items():
    for _window, _teams in _windows.items():
        for _tid, (_power, _comp) in _teams.items():
            TEAM_TABLE.setdefault(_tid, (_region, _window, _power, _comp))
del _region, _windows, _window, _teams, _tid, _power, _comp

# 分数 = 效能 × 10%（击杀一个怪获得的分数），判定按「分数」而非原始效能。
SCORE_RATE = 0.1


def score_of(power):
    """基础效能 -> 击杀可得分数（效能 × 10%，向下取整）。"""
    if power is None:
        return None
    return int(power * SCORE_RATE)


# README 提示：地图内圈左上区 5-7T 的中效能敌人与高效能敌人「分差仅有 9 分」，
# 也可计为高 —— 这里的「分」是击杀分数（效能 × 10%）：
#   高效能 60490 -> 6049 分，中效能 60402 -> 6040 分，相差 9 分。
# 故在 5-7 窗口内，把「与最高分数差 <= 10 分」的中效能一并计入高。
# 仅作用于 5-7 窗口，避免误伤 1-4 窗口的正常高/中/低分档。
CLOSE_TO_HIGH_REGIONS = {"内圈左上区": ("5-7", 10)}  # 区域 -> (窗口, 允许的分数差)


def _tier(region, window, power):
    """
    在同一「区域 + 回合窗口」内比较效能得出档位：
      最高=高，最低=低，其余=中；CLOSE_TO_HIGH_REGIONS 允许把接近最高的中升为高。
    """
    teams = REGION_TEAMS.get(region, {}).get(window, {})
    powers = [v[0] for v in teams.values()]
    if not powers:
        return "高"
    hi = max(powers)
    lo = min(powers)
    if power == hi:
        return "高"
    if power == lo:
        return "低"
    rule = CLOSE_TO_HIGH_REGIONS.get(region)
    if rule is not None:
        rule_window, score_gap_max = rule
        # 按分数（效能 ×10%）比较，而不是原始效能
        if rule_window == window and (score_of(hi) - score_of(power)) <= score_gap_max:
            return "高"
    return "中"


def classify(team_id, region=None):
    """
    返回 (区域, 回合窗口, 效能, 配置, 档位) 或 None。

    region 指定时，只在该区域内按窗口查找 —— 这是正确用法，因为同一个怪组可能
    同时属于多个区域（770048~770050 既是「边缘正右/正上 5-7T」也是「右上顶点 5-7T」）。
    region 为 None 时退化为按 TEAM_TABLE 全局反查（多区域取首个），仅供单独查询怪组用。
    """
    if region is not None:
        for window, teams in REGION_TEAMS.get(region, {}).items():
            if team_id in teams:
                power, comp = teams[team_id]
                return region, window, power, comp, _tier(region, window, power)
        return None
    if team_id not in TEAM_TABLE:
        return None
    r, window, power, comp = TEAM_TABLE[team_id]
    return r, window, power, comp, _tier(r, window, power)


def window_of_turn(turn):
    """把具体回合映射到刷怪窗口。1~4 -> '1-4'，5~7 -> '5-7'。"""
    try:
        t = int(turn)
    except (TypeError, ValueError):
        return None
    return "5-7" if t >= 5 else "1-4"


def detect_turn(data):
    """
    从 S2C 响应推断当前回合。数据里最可靠的是 fairy_skill_on_spot 的 start_turn 最大值：
      1T 的 start_turn 全是 1，2T 出现 2，以此类推。
    返回 int（1~7），拿不准返回 None。
    """
    if not isinstance(data, dict):
        return None
    turns = []
    fos = data.get("fairy_skill_on_spot", {})
    if isinstance(fos, dict):
        for inner in fos.values():
            if not isinstance(inner, dict):
                continue
            for rec in inner.values():
                if isinstance(rec, dict):
                    try:
                        turns.append(int(rec.get("start_turn")))
                    except (TypeError, ValueError):
                        pass
    if not turns:
        return None
    return max(turns)


def parse_hidden_spots(data):
    """
    从 S2C 响应里抽出隐藏点敌人。
    返回 [{"spot_id": str, "team_id": str, "region": str, "turn": int|None,
           "window": str|None, "power": int|None, "tier": str, "comp": str}, ...]
    """
    if not isinstance(data, dict):
        return []
    ally = data.get("fairy_skill_return", {})
    if not isinstance(ally, dict):
        return []
    summoner = ally.get("allyteam_summoner", [])
    if not isinstance(summoner, list):
        return []

    turn = detect_turn(data)
    out = []
    for entry in summoner:
        if not isinstance(entry, dict):
            continue
        spot_id = str(entry.get("spot_id", ""))
        info = entry.get("ally_instance_info", {}) or {}
        team_id = str(info.get("ally_enemy", ""))
        # 区域以隐藏点 spot_id 为准：同一个怪组可能出现在多个区域
        # （770048~770050 既是边缘正右/正上 5-7T，也是右上顶点 5-7T）。
        region = SPOT_REGION.get(spot_id, "未知区域")
        cls = classify(team_id, region)
        if cls is None:
            # 该区域里没有这个怪组（数据异常/未收录），退回全局反查兜底
            cls = classify(team_id)
        if cls is not None:
            t_region, t_window, power, comp, tier = cls
            # 若 spot 已知区域，仍以 spot 的区域为准
            if region == "未知区域":
                region = t_region
            window = t_window
        else:
            power = None
            comp = ""
            window = None
            tier = "?"
        out.append({
            "spot_id": spot_id,
            "team_id": team_id,
            "region": region,
            "turn": turn,
            "window": window,
            "power": power,
            "score": score_of(power),
            "tier": tier,
            "comp": comp,
        })
    return out


def summarize(spots):
    """统计每回合窗口内的高/中/低数量，以及按区域分组的明细。"""
    tier_count = {"高": 0, "中": 0, "低": 0, "?": 0}
    by_region = {}
    for s in spots:
        tier_count[s["tier"]] = tier_count.get(s["tier"], 0) + 1
        by_region.setdefault(s["region"], {"高": 0, "中": 0, "低": 0, "?": 0})
        by_region[s["region"]][s["tier"]] = by_region[s["region"]].get(s["tier"], 0) + 1
    return tier_count, by_region


# ============================================================
# 建议关注区域（README「需要注意的事」第 3 条）
# ============================================================
# 1-4T 重点：地图内圈右下区、地图边缘正右/正上
FOCUS_EARLY = ["内圈右下区", "边缘正右/正上"]
# 5-7T 重点：地图内圈左上区、地图内圈右上区、地图边缘正右/正上/右上顶点
FOCUS_LATE = ["内圈左上区", "内圈右上区", "边缘正右/正上", "右上顶点"]


def focus_regions(turn):
    """按回合返回需要重点关注的区域列表（保持优先级顺序）。"""
    window = window_of_turn(turn)
    if window == "1-4":
        return list(FOCUS_EARLY)
    if window == "5-7":
        return list(FOCUS_LATE)
    return []


def order_regions(regions, turn):
    """
    把区域名按「建议关注优先」排序：关注区域按 FOCUS 顺序排在前面，
    其余区域按名称排在后面。返回 (关注区域列表, 其它区域列表)。
    """
    focus = [r for r in focus_regions(turn) if r in regions]
    others = sorted(r for r in regions if r not in focus)
    return focus, others


def order_spots(spots, turn):
    """隐藏点明细按「建议关注区域优先」排序，其余保持按 spot_id 升序。"""
    focus = {r: i for i, r in enumerate(focus_regions(turn))}

    def key(s):
        idx = focus.get(s["region"])
        return (0, idx, int(s["spot_id"])) if idx is not None \
            else (1, 0, int(s["spot_id"]))

    return sorted(spots, key=key)


def focus_high_count(spots, turn):
    """建议关注区域内的「高」档怪组数量。"""
    focus = set(focus_regions(turn))
    return sum(1 for s in spots if s["tier"] == "高" and s["region"] in focus)


# ============================================================
# 控制台监视（与 GUI 共用上面的核心）
# ============================================================
if __name__ == "__main__":
    import sys
    from gflzirc import GFLProxy, set_windows_proxy, STATIC_KEY

    PROXY_PORT = 8080
    proxy_instance = None
    stop_flag = False

    def on_traffic(event_type, url, data):
        if event_type.upper() != "S2C":
            return
        if "startMission" not in url and "startTurn" not in url \
                and "Mission_startTurn" not in url:
            return
        if not isinstance(data, dict):
            return
        spots = parse_hidden_spots(data)
        if not spots:
            return
        counts, by_region = summarize(spots)
        turn = detect_turn(data)
        focus, others = order_regions(by_region.keys(), turn)
        print("\n" + "=" * 60)
        print("回合 %s | 隐藏点 %d | 高 %d / 中 %d / 低 %d"
              % (turn, len(spots), counts["高"], counts["中"], counts["低"]))
        print("建议关注区域高效能: %d" % focus_high_count(spots, turn))
        for region in focus:  # 只显示建议关注区域，且排在前面
            c = by_region[region]
            print("  [重点] %-12s 高=%d 中=%d 低=%d" % (region, c["高"], c["中"], c["低"]))
        for region in others:
            c = by_region[region]
            print("         %-12s 高=%d 中=%d 低=%d" % (region, c["高"], c["中"], c["低"]))
        for s in order_spots(spots, turn):
            print("    %s %s 效能=%-6s %s" % (s["spot_id"], s["team_id"], s["power"], s["tier"]))
        print("=" * 60)

    print("GFLH-Sandbox 控制台监视")
    print(" -c 开始监视 | -q 停止 | -E 退出")
    while True:
        cmd = input("SAND> ").strip()
        if cmd == "-c":
            if proxy_instance:
                print("[!] 已在监视")
                continue
            proxy_instance = GFLProxy(PROXY_PORT, STATIC_KEY, on_traffic)
            proxy_instance.start()
            set_windows_proxy(True, "127.0.0.1:%d" % PROXY_PORT)
            print("[*] 监视启动，端口 %d，进入游戏查看隐藏点刷怪" % PROXY_PORT)
        elif cmd == "-q":
            if proxy_instance:
                proxy_instance.stop()
                set_windows_proxy(False)
                proxy_instance = None
                print("[*] 已停止")
        elif cmd == "-E":
            if proxy_instance:
                proxy_instance.stop()
                set_windows_proxy(False)
            print("[*] 退出")
            sys.exit(0)

