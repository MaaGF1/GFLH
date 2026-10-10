# GFLH-FriendPraise

每日好友互动工具，tkinter GUI：**访问 / 点赞 / 载具访问 / 载具维护**。

由原控制台脚本 `FriendPraise.py` 移植而来。**原脚本流程本身可用，因此完全照搬，不做任何
改动**；界面上只留三项 + 一个按钮：UID / Sign Key / 服务器 → 「开始点赞」。

## 界面

| 控件 | 说明 |
|---|---|
| UID | **默认留空**，由「自动捕获密钥」填入 |
| Sign Key | **默认留空**，由「自动捕获密钥」填入 |
| 服务器 | 下拉选择，默认 `SERVERS["AR15"]`（与原脚本一致） |
| user_id | 只读显示，由 UID 自动得出（`Friend/teamAndPraisePrize` 要用） |
| 自动捕获密钥 / 停止捕获 | 启停捕获代理（端口 `8081`，与原脚本一致） |
| **开始点赞** | 开始执行；运行中可「停止」 |

另有统计区（好友总数 / 进度 / 四项操作的 OK 与 FAIL 计数）与日志区。

`UID` 与 `Sign Key` **不写入配置文件**（会话密钥，且会被服务器轮换）；配置文件只记
服务器与语言，所以界面上这两栏每次都是空的。

## 流程（与原脚本逐行一致）

```
捕获到 uid / sign 后：
  1) Friend/mallByType9           空包            ← 取本账号好友状态
  2) Friend/teamAndPraisePrize    {"user_id": 自己UID}   ← 取点赞相关状态/奖励
  3) Friend/list                  取好友列表 resp["list"]
  4) 逐个好友（每次请求间隔 SLEEP_INTERVAL = 0.01s）：
       Friend/visit       {"f_userid": …, "f_zoneid": …}
       Friend/praise      {"f_userid": …, "f_zoneid": …}
       Vehicle/visit      {"to_user_id": …, "to_zone_id": …}
       Vehicle/maintain   {"to_user_id": …, "to_zone_id": …}
  5) 打印统计（好友总数、耗时、四项的成功/失败数）
```

「开始点赞」会先停掉捕获代理并重置统计，与原脚本 `-r` 命令的行为一致。运行中点「停止」
会在当前请求结束后中止（原脚本 `-s` 的行为）。

## 目录结构

```
GFLH-FriendPraise/
├── src/friend_praise_gui.py        # 主程序（原脚本逻辑 + GUI）
├── FriendPraise.py                 # 原控制台脚本（存档）
├── tests/
│   ├── smoke_test.py               # 离线自测（不需要游戏、不联网）
│   └── original_friend_ops.py      # 上面那份存档的冻结副本，仅作一致性基线
└── mk/                             # PyInstaller 打包
    ├── build_friendpraise.py
    ├── friendpraise.spec
    ├── requirements.txt
    └── icon.ico
```

## 使用

1. `pip install -r mk/requirements.txt`（Python 3.11+，需要 `gflzirc`）；
2. 运行 `python src/friend_praise_gui.py`；
3. 点「自动捕获密钥」→ 登录游戏，UID / Sign Key 自动填入；
4. 点「开始点赞」。

## 与原脚本的差异

**只有这些**

- 协议路径、payload、请求顺序、`SLEEP_INTERVAL` 间隔完全一致。
- 原脚本用 `-c` / `-r` / `-s` / `-stats` / `-E` 命令行控制；GUI 换成按钮。
- `print` 改为日志回调，措辞保持原样（例如 `[-] friendVisit Server Error: …`）。
- 原脚本 `USER_UID` 初值是占位符 `"_InputYourID_"`；GUI 改为空串，判断条件相应改成
  「空则不执行」。
- `UID` / `Sign Key` 不写入配置文件。
- 界面增加只读的 `user_id` 显示与统计/日志区。
- 原脚本的 `-stats` 命令（随时打印统计）由实时统计区取代。

## 自测

不需要游戏、不联网、不会打开真实窗口：

```bash
python tests/smoke_test.py
```

「与原始脚本的一致性」一节会解析 `tests/original_friend_ops.py`，逐个比对 7 个 API 路径、
`SLEEP_INTERVAL` / `PROXY_PORT` / `BASE_URL`、以及各请求的 payload 键是否与原文一致。
其余覆盖：完整请求顺序（两个前置包 → 好友列表 → 每个好友四个操作）、payload 内容、
四项成功/失败计数、无好友时的处理、停止标志、以及 GUI（UID/Sign 初始为空、捕获后回填、
统计渲染、配置文件不含 UID/Sign）。
