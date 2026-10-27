# gflmaps 数据转换脚本

## spawn_extract.py

把 `S2C_Mission_teamMove` / `S2C_Mission_startTurn` 抓包转成地图刷怪图层用的
`../data/spawn/mission-<id>.json`。

```bash
python spawn_extract.py --mission 11403 \
  --team-move "D:\Github\GFLH\GFLH-SlowShock\0039_S2C_4000_Mission_teamMove_1792629961.json" \
  --start-turn "D:\Github\GFLH\GFLH-SlowShock\0189_S2C_5000_Mission_startTurn_1793005345.json"
```

参数：

| 参数 | 说明 |
| --- | --- |
| `--mission` | 任务 ID（`mission.json` 里的 `id`，不是 `mission-10011403` 这个文本 key） |
| `--team-move` | 必填，1T 的队伍移动包，初始怪组和传送点刷怪都以它为准 |
| `--start-turn` | 可选，只用来对比 2T 的分布差异，不参与渲染 |
| `--data-root` | 默认 `../../GFLData` |
| `--server` | 默认 `ch` |
| `--out` | 默认 `../data/spawn` |

输出结构：

```json
{
  "missionId": 11403,
  "turn": 1,
  "initial": [{"instanceId": 1, "teamId": 6589201, "spotId": 67554,
               "birthTurn": 1, "ai": 102, "aiPara": "@67554,5", "resolvedBy": "ai_para"}],
  "spawns":  [{"instanceId": 15, "teamId": 6589234, "spotId": 67672,
               "birthTurn": 0, "ai": 102, "aiPara": "@67672,99"}],
  "third":   [{"instanceId": 4, "teamId": 6589208, "spotId": 67693,
               "birthTurn": 0, "ai": 102, "aiPara": "@67693,99"}],
  "unplaced": [{"instanceId": 27, "teamId": 6589999, "reason": "..."}],
  "laterTurn": {"laterTurnOnly": [...], "sameSpotsDifferentTeam": [...]},
  "stats": {"initial": 27, "spawns": 18, "third": 5, "unplaced": 1}
}
```

页面侧：

* `initial` 画成带编号的圆点（编号 = `enemy_instance_info` 的行动优先级 1–28）；
* `spawns` 画成橙色“刷”圆点，并补画一只队长小人；
* `third` 画成蓝色“三”圆点（静态点位上的第三方梯队，小人本来就有，不再重复画）；
* 三者悬停都会显示组成 / 效能 / 生成回合 / 行动逻辑。

前端用同一套规则（`normalizeSpawnPayload`）处理实时包，所以 `map.py` 转发
`S2C_Mission_teamMove` 时不需要先生成 json。

## 图标

刷怪小人按 `enemy_character_type.code` 去找 `../images/map_chibis/<code>_wait0.gif`。
`GFLH-SlowShock/images/map-chibis` 里的 20 个图标与这里的同名文件逐字节相同，不需要再拷贝。
