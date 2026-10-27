#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把地图工具打包成 exe。

产物结构（onedir，和 GFLH 其他工具一致）：
    dist/GFLH-SlowShockMap/
    ├── GFLH-SlowShockMap.exe
    ├── _internal/              # Python 运行时（PyInstaller 生成）
    ├── gflmaps/                # 前端 + 图片 + 刷怪数据
    ├── GFLData/                # 离线数据（可 --no-data 跳过，跳过则运行时走 GitHub）
    └── 使用说明.txt

用法：
    python mk/build_map.py                     # 默认输出到 <repo>/dist
    python mk/build_map.py --no-data           # 不带 GFLData（体积小，需要联网）
    python mk/build_map.py --out "D:\\Github\\GFLH\\GFLH-SlowShock\\dist"
"""

import argparse
import os
import shutil
import subprocess
import sys

# GitHub Actions 的 Windows runner 默认用 cp1252 当 stdout 编码，
# 下面的中文 print 会直接抛 UnicodeEncodeError，这里统一改成 utf-8。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

MK_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(MK_DIR)
APP_NAME = "GFLH-SlowShockMap"

# map.js 里实际用到的 stc 表
STC_FILES = [
    "ally_team.json", "auto_mission.json", "building.json", "commander_uniform.json",
    "daily_mission_group.json", "enemy_character_type.json", "enemy_in_team.json",
    "enemy_standard_attribute.json", "enemy_team.json", "equip.json", "fairy.json",
    "furniture.json", "gift_item.json", "gun.json", "gun_in_ally.json", "item.json",
    "mission.json", "mission_event.json", "mission_targettrain_enemy.json",
    "mission_win_type_config.json", "normal_activity.json", "prize.json", "sangvis.json",
    "sangvis_in_ally.json", "skin.json", "spot.json", "team_ai.json", "theater_area.json",
]

TEXT_FILES = [
    "ally_team.json", "building.json", "commander_uniform.json", "enemy_character_type.json",
    "equip.json", "fairy.json", "furniture.json", "gift_item.json", "gun.json", "item.json",
    "mission.json", "mission_win_type_config.json", "mission_targettrain_enemy.json",
    "sangvis.json", "skin.json", "special_spot_config.json", "team_ai.json",
]

CATCH_FILES = ["equip_in_ally_info.json", "mission_event_prize_info.json", "trial_info.json"]

README_TEXT = """GFLH-SlowShockMap
=================

双击 GFLH-SlowShockMap.exe：程序将在后台唤起本地服务，而后使用 WebView2
（pywebview）打开地图窗口。关闭窗口，程序将自动退出。

如果 WebView2 窗口因环境原因不兼容，程序将自动退回「Edge/Chrome 应用窗口」，
仍然无效则使用默认浏览器打开 http://127.0.0.1:8081/ ，服务本身不受影响。

窗口右下角为「监控」面板：开始 / 停止 / 退出。
（用普通静态服务器打开页面时不会出现该面板）

抓包说明
--------
点击「开始」将启动（127.0.0.1:8080）并设置系统代理，
首次使用需要在游戏里重新登录一次，代理才能获取Sign Key。
停止或退出时会自动还原系统代理。
同一时间只能有一个工具占用 8080 端口。

数据
----
优先读取本目录下的 GFLData\\ch（离线）；若无则从 GitHub 拉取。
若需要离线使用，将完整的 GFLData 文件夹放到本目录即可。

其他地图
--------
程序默认打开 #campaign=3058&mission=11403（慢休克-自画像-厚涂），
在页面顶部的「战役/地图」下拉里可以直接切换。
"""


def copy_file(src, dst_dir):
    os.makedirs(dst_dir, exist_ok=True)
    shutil.copy2(src, os.path.join(dst_dir, os.path.basename(src)))


def stage_assets(app_dir, with_data):
    """把前端和（可选的）离线数据放到 exe 旁边。"""
    src_maps = os.path.join(ROOT_DIR, "gflmaps")
    dst_maps = os.path.join(app_dir, "gflmaps")
    if os.path.exists(dst_maps):
        shutil.rmtree(dst_maps)
    shutil.copytree(src_maps, dst_maps)

    if with_data:
        data_root = os.path.join(ROOT_DIR, "GFLData", "ch")
        dst_root = os.path.join(app_dir, "GFLData", "ch")
        for name in STC_FILES:
            copy_file(os.path.join(data_root, "stc", name), os.path.join(dst_root, "stc"))
        for name in TEXT_FILES:
            copy_file(os.path.join(data_root, "text", "table", name), os.path.join(dst_root, "text", "table"))
        for name in CATCH_FILES:
            copy_file(os.path.join(data_root, "catchdata", name), os.path.join(dst_root, "catchdata"))

    with open(os.path.join(app_dir, "使用说明.txt"), "w", encoding="utf-8") as handle:
        handle.write(README_TEXT)


def build(with_data, out_dir, keep_build, console=False):
    build_dir = os.path.join(ROOT_DIR, "build")
    spec_file = os.path.join(MK_DIR, "map.spec")
    if not os.path.exists(spec_file):
        raise SystemExit("找不到 mk/map.spec")

    if not keep_build and os.path.exists(build_dir):
        shutil.rmtree(build_dir)
    app_dir = os.path.join(out_dir, APP_NAME)
    if os.path.exists(app_dir):
        shutil.rmtree(app_dir)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--clean", "--noconfirm",
        "--workpath", build_dir,
        "--distpath", out_dir,
        spec_file,
    ]
    print("[build]", " ".join(cmd))
    env = dict(os.environ)
    env["GFM_CONSOLE"] = "1" if console else "0"
    subprocess.run(cmd, cwd=ROOT_DIR, check=True, env=env)

    print("[stage] 拷贝前端资源…")
    stage_assets(app_dir, with_data)

    total = 0
    for base, _, files in os.walk(app_dir):
        for name in files:
            total += os.path.getsize(os.path.join(base, name))
    print("[done] {}  ({:.1f} MB)".format(app_dir, total / 1024 / 1024))
    print("[done] exe: {}".format(os.path.join(app_dir, APP_NAME + ".exe")))


def main():
    parser = argparse.ArgumentParser(description="打包地图工具为 exe")
    parser.add_argument("--out", default=os.path.join(ROOT_DIR, "dist"), help="输出目录")
    parser.add_argument("--no-data", action="store_true", help="不打包 GFLData（运行时联网取数据）")
    parser.add_argument("--keep-build", action="store_true", help="保留 PyInstaller 的 build 目录")
    parser.add_argument("--console", action="store_true", help="保留控制台窗口（调试打包问题时使用）")
    args = parser.parse_args()

    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)
    build(not args.no_data, out_dir, args.keep_build, args.console)


if __name__ == "__main__":
    main()
