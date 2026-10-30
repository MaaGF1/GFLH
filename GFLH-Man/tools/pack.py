# tools/pack.py
#
# Extract the "recipe" from its private source and encrypt it into a container.
#
#   source (local dev): Secret/value_modify/debuff_field.js + Secret/value_modify/map.json
#   source (CI):        environment variables GFLM_RECIPE_JSON and GFLM_MAP_JSON
#   output:             dist/recipe.enc
#
# Symbol names live only in the private map file, so nothing in this file (or in any
# other public file) reveals which functions or fields are involved.
#
# Two encryption modes:
#   default     fingerprint container (GFLM2) - key derived from the target module's PE
#               fingerprint, so no passphrase is prompted at run time
#   --password  passphrase container (GFLM1) - kept for compatibility, prompts every launch
#
# Usage:
#   python tools/pack.py --dll "C:\...\GameAssembly.dll"     # fingerprint mode (recommended)
#   python tools/pack.py --fp <hex>                          # fingerprint mode, known hex
#   python tools/pack.py --password <passphrase>             # passphrase mode
#   python tools/pack.py --print-json                        # print the recipe JSON only
#   python tools/pack.py --print-fp --dll ...                # print the fingerprint hex only

import argparse
import getpass
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crypto_box import seal, seal_keyed, derive_key, pe_fingerprint_file, pe_size_of_image_file

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")


def _find_private(rel_parts, env_name):
    """Locate a private input file, falling back to an environment variable."""
    for base in ("Secret", "secret", ""):
        p = os.path.join(ROOT, base, *rel_parts) if base else os.path.join(ROOT, *rel_parts)
        if os.path.exists(p):
            return p
    return os.path.join(ROOT, "Secret", *rel_parts)


SRC = _find_private(("value_modify", "debuff_field.js"), "GFLM_RECIPE_SOURCE")

MAP_PATH = _find_private(("value_modify", "map.json"), "GFLM_MAP_JSON")


def load_map():
    """The private mapping: symbol names -> RVAs/offsets. Never part of the package."""
    env = os.environ.get("GFLM_MAP_JSON", "").strip()
    if env:
        return json.loads(env)
    if not os.path.exists(MAP_PATH):
        raise SystemExit("private map not found: %s\n"
                         "        create it next to the recipe source, or set GFLM_MAP_JSON" % MAP_PATH)
    with open(MAP_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_block(text, var_name):
    m = re.search(r"var\s+" + var_name + r"\s*=\s*\{(.*?)\};", text, re.S)
    if not m:
        raise SystemExit("cannot find block %s in %s" % (var_name, SRC))
    out = {}
    for k, v in re.findall(r"(\w+)\s*:\s*(0x[0-9a-fA-F]+|\d+)", m.group(1)):
        out[k] = int(v, 0)
    return out


def build_recipe_from_js(js, m=None):
    m = m or load_map()
    rva = parse_block(js, "RVA")
    off = parse_block(js, "OFF")

    def pick(block, name):
        if name not in block:
            raise SystemExit("name %r is missing from the source tables" % name)
        return block[name]

    entries = [pick(rva, k) for k in m["entries"]]
    fields = [pick(off, k) for k in m["fields"]]
    bases = [pick(off, k) for k in m["base"]]

    fm = re.search(r"FACTOR\s*:\s*\{\s*num\s*:\s*(\d+)\s*,\s*den\s*:\s*(\d+)", js)
    factor = (int(fm.group(1)) / int(fm.group(2))) if fm else 0.6

    return {
        "e": entries,
        "o": fields,
        "r": bases,
        "ne": pick(off, m["enemy"]),
        "f": round(factor, 6),
        "ms": 0,
        "limit": 5000,
        "cd": int(m.get("character_data", 16)),
        "dg": [],                       # diagnostics off by default; --diag enables them
        "td": list(m.get("teardown") or []),
        "ud": list(m.get("unit_destroy") or []),
    }


def validate(recipe):
    for k in ("e", "o", "r", "ne", "f"):
        if k not in recipe:
            raise SystemExit("recipe is missing field: %s" % k)
    if len(recipe["o"]) != len(recipe["r"]) or not recipe["o"]:
        raise SystemExit("recipe tables do not line up")
    f = float(recipe["f"])
    if not (0.05 < f < 1.0):
        raise SystemExit("factor must be inside (0, 1), otherwise this 'debuff' could be used as a buff")
    recipe.setdefault("cd", 16)
    if not recipe.get("td"):
        raise SystemExit("recipe has no teardown entries")
    return recipe


def fingerprint(args):
    if args.fp:
        try:
            return bytes.fromhex(args.fp)
        except ValueError:
            raise SystemExit("--fp must be hexadecimal")
    if args.dll:
        if not os.path.exists(args.dll):
            raise SystemExit("not found: %s" % args.dll)
        return pe_fingerprint_file(args.dll)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--password", default=None, help="encrypt with a passphrase (legacy mode)")
    ap.add_argument("--dll", default=None, help="path to the target module; its PE fingerprint becomes the key")
    ap.add_argument("--fp", default=None, help="fingerprint hex (when you would rather not pass the dll)")
    ap.add_argument("--factor", type=float, default=None)
    ap.add_argument("--limit", type=int, default=5000)
    ap.add_argument("--print-json", action="store_true")
    ap.add_argument("--print-fp", action="store_true")
    ap.add_argument("--from-env", action="store_true")
    ap.add_argument("--diag", action="store_true",
                    help="enable diagnostic output (prints candidate fields on each shot)")
    args = ap.parse_args()

    fps = fingerprint(args)
    if args.print_fp:
        if not fps:
            raise SystemExit("--print-fp requires --dll or --fp")
        print(fps.hex())
        return

    env_json = os.environ.get("GFLM_RECIPE_JSON")
    if args.from_env or env_json:
        if not env_json:
            raise SystemExit("environment variable GFLM_RECIPE_JSON is empty")
        recipe = json.loads(env_json)
    else:
        with open(SRC, "r", encoding="utf-8") as f:
            recipe = build_recipe_from_js(f.read())

    if args.factor is not None:
        recipe["f"] = round(args.factor, 6)
    recipe.setdefault("ms", 0)
    recipe.setdefault("limit", args.limit)
    recipe["dg"] = list(load_map().get("diag") or []) if args.diag else []

    validate(recipe)

    payload = json.dumps(recipe, separators=(",", ":")).encode("utf-8")

    if fps:
        if args.dll:
            recipe["ms"] = pe_size_of_image_file(args.dll)   # mapped module size
            payload = json.dumps(recipe, separators=(",", ":")).encode("utf-8")
        if args.print_json:
            print(payload.decode("utf-8"))
            return
        blob = seal_keyed(payload, derive_key(fps))
        mode = "fingerprint container (no passphrase)"
    else:
        if args.print_json:
            print(payload.decode("utf-8"))
            return
        pw = args.password or os.environ.get("GFLM_RECIPE_PASSWORD")
        if not pw:
            pw = getpass.getpass("Passphrase: ")
            if pw != getpass.getpass("Repeat passphrase: "):
                raise SystemExit("the two passphrases do not match")
        blob = seal(payload, pw)
        mode = "passphrase container (prompted every launch)"

    os.makedirs(DIST, exist_ok=True)
    out = os.path.join(DIST, "recipe.enc")
    with open(out, "wb") as f:
        f.write(blob)

    print("written: %s (%d bytes)" % (out, len(blob)))
    print("mode: %s" % mode)
    print("entries: %d entry points / %d fields" % (len(recipe["e"]), len(recipe["o"])))
    print("checksum: %s" % hashlib.sha256(blob).hexdigest()[:16])


if __name__ == "__main__":
    main()
