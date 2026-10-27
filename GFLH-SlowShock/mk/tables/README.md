# 单图表格提取与渲染

把 `../GFLData`（MaaGF1/GFLData 的离线快照）里**一张地图**的表格数据抽出来，单独渲染成一个页面：
关卡信息、敌方梯队 / 站位、单位明细、节点列表、建筑、传送、节点拓扑示意。

不依赖 `gflmaps` 的 jQuery 与 canvas，也不启动 proxy/WebView，纯静态页 + 两个 Python 脚本。

![总览](preview/desktop.png)

![梯队单位明细](preview/team.png)

## 快速开始

```bash
cd src/demo/map/tables

python extract.py       # 读 ../GFLData，生成 data/mission-11403.json
python serve.py         # 打开 http://127.0.0.1:8093/
```

页面用 `fetch` 读 `data/*.json`，所以必须走 http，直接双击 `index.html` 会被浏览器的 file:// 限制拦住（页面会给出提示）。

## 目录

```
tables/
├── extract.py          # 提取器：GFLData -> data/mission-<id>.json
├── serve.py            # 本地静态服务器（8093）
├── index.html          # 页面骨架
├── app.js              # 渲染逻辑
├── style.css           # 深色 + 队黄配色
├── data/               # 生成物：mission-<id>.json、index.json
└── preview/            # 截图
```

## 提取器

```bash
python extract.py --mission 11403 11402     # 一次多张
python extract.py --mission 11404 --turn 3  # 指定回合（影响 correction_turn 的等级偏移）
python extract.py --server jp               # 换数据服
python extract.py --data-root D:\path\GFLData
```

数据来源（都在 `<GFLData>/<server>/` 下）：

| 用途 | 文件 |
| --- | --- |
| 关卡 | `stc/mission.json`、`stc/mission_win_type_config.json`、`stc/auto_mission.json` |
| 点位 | `stc/spot.json` |
| 敌方 | `stc/enemy_team.json`、`stc/enemy_in_team.json`、`stc/enemy_character_type.json`、`stc/enemy_standard_attribute.json`、`stc/team_ai.json` |
| 友军 / 建筑 | `stc/ally_team.json`、`stc/gun.json`、`stc/gun_in_ally.json`、`stc/building.json` |
| 活动 / 子活动 | `stc/normal_activity.json`、`stc/mission_event.json` |
| 文本 | `text/table/*.json`（mission、building、team_ai、enemy_character_type、normal_activity、mission_event、special_spot_config…） |

### 怎么找另一张图的任务 ID

1. 在 `GFLData/ch/text/table/mission.json` 里搜地图名，得到类似
   `"mission-10011403": "自画像-厚涂"`；
2. 去掉 `mission-1` 前缀 → `11403`，就是 `--mission` 要的值；
3. 跑一次 `extract.py`，它会更新 `data/index.json`，页面下拉里就会多出这张图。

`mission.json` 里同一个数字还带着 `campaign`、`mission_group_id`、`map_res_name`、`turn_limit`、`win_type` 等字段，正是这些字段把"活动 → 子活动 → 地图"串起来的。

## 表格口径

- **效能**：优先用梯队数据里的 `effect_ext`（游戏内实际展示值，很多图是"效能欺诈"）；为 0 时按公式计算。
  公式取自 `gflmaps/main.js` 的 `efectcal()`，同时给出护甲系数 600（2.08 之后）与 300（2.08 之前）两套结果，
  单位明细表里还有每个单位的单兵效能。鼠标悬停在效能格上能看到公式值。
- **等级**：原始数据是 `60150` 这种编码，页面显示 `60150 % 1000 = 150`。
- **correction_turn**：按 `--turn`（默认 1）取该梯队的等级偏移，再叠加到每个单位上。
- **归属**：0 中立 / 1 我方 / 2 敌方 / 3 第三方 / 99 视野外。
- **节点类型**：只标注能由图标准确确认的 1 指挥部、2 普通点、3 机场、4 雷达、7 重装机场；
  其余类型（5/6/8）显示 `类型 N`，不猜。
- **通关条件**：取 `mission_win_type_config` 的 `extra_language` 文本；取不到时回退 `条件 <id>`。
- **建筑备注**：`working_special_spot` → `special_spot_config` 文本，多个用"；"连接。

## 数据结构（data/mission-<id>.json）

```
mission     关卡信息（名称/活动/子活动/昼夜/回合/限制/通关条件/奖励/地图资源）
spots[]     节点：id、type、belong、x/y、route[]、enemyTeamId、allyTeamId、buildingId、activeCycle…
enemyRows[] 站位：spotId、teamId、kind(enemy/third/ally)、alignment、ai、composition[]、drops[]
teams[]     梯队：leader、ce / ce600 / ce300 / fakeCe、units[]（含逐项属性与单兵效能）
buildings[] 建筑：spotId、id、name、code、type、耐久、破坏方式、支援范围、备注
portals[]   传送：from / to / buildingId
stats       计数，页面顶部卡片直接用
```

## 已知限制

- 第三方梯队（数据里只有一个 `ally_team` 壳、没有 `enemy_team` 记录）名字会显示成 `[team-6589209]`，这是数据本身缺名。
- 传送表只解析 `spot.auto_teleport`；"自画像-厚涂"这张图没有传送点，所以是空的。
- 本地 GFLData 是快照，换版本数值（尤其等级、效能）会变。
- 只覆盖"一张图 = 一个 mission"的常规结构；演习（theater）、靶机专训、防御演练等特殊 campaign 的数据不在这套流程里。
