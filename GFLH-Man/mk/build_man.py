# GFLH-Man/mk/build_man.py
#
# Build the shareable exe.
#
#   A. fingerprint mode (recommended, no passphrase at run time)
#        python mk/build_man.py --local --dll "C:\...\GameAssembly.dll"
#        python mk/build_man.py --local --fp <hex>
#
#   B. passphrase mode (prompted on every launch)
#        python mk/build_man.py --local
#
#   C. CI build (recipe comes from repository secrets)
#        env: GFLM_RECIPE_JSON / GFLM_FP (or GFLM_RECIPE_PASSWORD)
#
# Output: dist/GFLH-Man/ (GFLH-Man.exe + _internal/)
# Sharing: zip the whole directory. In fingerprint mode the other side just double-clicks.

import argparse
import getpass
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # GFLH-Man/
TOOLS = os.path.join(ROOT, "tools")
SRC_DIR = os.path.join(ROOT, "src")
DIST = os.path.join(ROOT, "dist")
BUILD = os.path.join(ROOT, "build")
STAGE = os.path.join(BUILD, "stage")
NAME = "GFLH-Man"

sys.path.insert(0, TOOLS)
from crypto_box import (seal, seal_keyed, derive_key,                    # noqa: E402
                        pe_fingerprint_file, pe_size_of_image_file)
from pack import validate, build_recipe_from_js, load_map, resolve_dll, SRC   # noqa: E402


def fail(msg):
    print("[error] " + msg)
    sys.exit(1)


def load_recipe(local, mode="subtract"):
    if local:
        if not os.path.exists(SRC):
            fail("recipe source not found: %s\n"
                 "        expected under Secret/value_modify/" % SRC)
        with open(SRC, "r", encoding="utf-8") as f:
            recipe = build_recipe_from_js(f.read(), mode=mode)
        print("[*] recipe source: %s (local, private)" % os.path.relpath(SRC, ROOT))
    else:
        raw = os.environ.get("GFLM_RECIPE_JSON", "").strip()
        if not raw:
            fail("GFLM_RECIPE_JSON is missing or empty.\n"
                 "        A CI build gets it from the repository secret of the same name.\n"
                 "        Checklist:\n"
                 "          - Settings > Secrets and variables > Actions > New repository secret\n"
                 "          - the name must be exactly GFLM_RECIPE_JSON (case sensitive)\n"
                 "          - add it to the fork that runs the workflow, not the upstream repo\n"
                 "          - secrets are NOT passed to pull requests opened from a fork\n"
                 "        For a local build add --local instead.")
        try:
            recipe = json.loads(raw)
        except json.JSONDecodeError as e:
            fail("GFLM_RECIPE_JSON is not valid JSON: %s" % e)
        print("[*] recipe source: GFLM_RECIPE_JSON (CI secret)")
    return validate(recipe)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true", help="read the recipe from the private folder")
    ap.add_argument("--dll", default=None, help="path to the target module (fingerprint mode)")
    ap.add_argument("--fp", default=None, help="fingerprint hex (fingerprint mode)")
    ap.add_argument("--password", default=None, help="force passphrase mode")
    ap.add_argument("--diag", action="store_true", help="build with diagnostic output enabled")
    ap.add_argument("--mode", default="subtract", choices=("subtract", "base", "base-pow"),
                    help="subtract: adjust the value (default). base: scale the base value and let "
                         "the game recompute (exact with percentage buffs). base-pow: staged test")
    args = ap.parse_args()

    recipe = load_recipe(args.local, args.mode)

    fp = None
    if args.fp:
        try:
            fp = bytes.fromhex(args.fp)
        except ValueError:
            fail("--fp must be hexadecimal")
    elif args.dll:
        dll = resolve_dll(args.dll)
        fp = pe_fingerprint_file(dll)
        recipe["ms"] = pe_size_of_image_file(dll)   # mapped module size

    if fp is None and not args.password:
        env_fp = os.environ.get("GFLM_FP", "").strip()
        if env_fp:
            try:
                fp = bytes.fromhex(env_fp)
            except ValueError:
                fail("GFLM_FP must be hexadecimal")

    recipe["dg"] = list(load_map().get("diag") or []) if args.diag else []
    payload = json.dumps(recipe, separators=(",", ":")).encode("utf-8")

    if fp:
        blob = seal_keyed(payload, derive_key(fp))
        mode = "fingerprint mode (no passphrase)"
    else:
        pw = args.password or os.environ.get("GFLM_RECIPE_PASSWORD", "").strip()
        if not pw:
            if os.environ.get("GITHUB_ACTIONS") or os.environ.get("CI"):
                fail("running in CI but neither GFLM_FP nor GFLM_RECIPE_PASSWORD is set.\n"
                     "        Add the GFLM_FP repository secret (fingerprint mode, recommended),\n"
                     "        or set GFLM_RECIPE_PASSWORD if you really want passphrase mode.")
            if not sys.stdin or not sys.stdin.isatty():
                fail("no passphrase source in a non-interactive run.\n"
                     "        Set the GFLM_FP secret (fingerprint mode, recommended) or\n"
                     "        GFLM_RECIPE_PASSWORD, or pass --password on the command line.")
            pw = getpass.getpass("Passphrase: ")
            if pw != getpass.getpass("Repeat passphrase: "):
                fail("the two passphrases do not match")
        blob = seal(payload, pw)
        mode = "passphrase mode (prompted every launch)"

    shutil.rmtree(BUILD, ignore_errors=True)
    os.makedirs(STAGE, exist_ok=True)
    os.makedirs(DIST, exist_ok=True)

    with open(os.path.join(STAGE, "recipe.enc"), "wb") as f:
        f.write(blob)
    shutil.copy2(os.path.join(TOOLS, "template.js"), os.path.join(STAGE, "template.js"))

    entry = os.path.join(ROOT, "man.py")
    if not os.path.exists(entry):
        fail("not found: %s" % entry)

    sep = os.pathsep   # ';' on Windows
    cmd = [
        sys.executable, "-m", "PyInstaller",
        entry,
        "--name", NAME,
        "--noconfirm", "--clean",
        "--noconsole",
        "--distpath", DIST,
        "--workpath", os.path.join(BUILD, "work"),
        "--specpath", BUILD,
        "--paths", TOOLS,
        "--paths", SRC_DIR,
        "--collect-all", "frida",
        "--add-data", os.path.join(STAGE, "template.js") + sep + ".",
        "--add-data", os.path.join(STAGE, "recipe.enc") + sep + ".",
    ]

    icon = os.path.join(ROOT, "mk", "icon.ico")
    if os.path.exists(icon):
        cmd += ["--icon", icon, "--add-data", icon + sep + "mk"]
    icon_png = os.path.join(ROOT, "mk", "icon_256.png")
    if os.path.exists(icon_png):
        cmd += ["--add-data", icon_png + sep + "mk"]

    print("[*] encryption: %s" % mode)
    print("[*] running PyInstaller (about 1-2 minutes)...")
    try:
        subprocess.check_call(cmd, cwd=ROOT)
    except subprocess.CalledProcessError:
        print("")
        print("[error] build failed. The usual cause: a previous GFLH-Man.exe is still")
        print("        running and holds dist/GFLH-Man/_internal/frida/_frida.pyd.")
        print("        Close the GFLH-Man window (or end the process) and retry.")
        sys.exit(1)

    out_dir = os.path.join(DIST, NAME)
    exe = os.path.join(out_dir, NAME + ".exe")
    if not os.path.exists(exe):
        fail("build finished but %s is missing" % exe)

    print("")
    print("[ok] %s" % exe)
    print("[ok] share it by zipping the whole directory %s" % os.path.relpath(out_dir, ROOT))
    if fp:
        print("[ok] the other side just double-clicks; the game build must match this package")
    else:
        print("[!] pass the passphrase out of band, never in release notes or public chat")


if __name__ == "__main__":
    main()
