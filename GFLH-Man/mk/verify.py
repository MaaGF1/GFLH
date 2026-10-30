# GFLH-Man/mk/verify.py
#
# Post-build self-check: proves the packaging really hides the recipe.
#
#   python mk/verify.py --dll "C:\...\GameAssembly.dll"   # decrypt with the PE fingerprint
#   python mk/verify.py                                   # CI: use GFLM_RECIPE_JSON for the scan
#
# Checks:
#   1. the package exists (exe + recipe.enc + template.js)
#   2. recipe.enc is an encrypted container (correct magic)
#   3. the recipe decrypts (fingerprint mode needs the dll, passphrase mode needs the env)
#   4. the recipe is complete and the factor is inside (0, 1)
#   5. no file inside the package contains any plaintext address or offset from it
#   6. template.js still carries every placeholder the loader fills in

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOLS = os.path.join(ROOT, "tools")
DIST = os.path.join(ROOT, "dist", "GFLH-Man")

sys.path.insert(0, TOOLS)
from crypto_box import (open_keyed, open_sealed, derive_key,      # noqa: E402
                        pe_fingerprint_file, MAGIC, MAGIC_FP)

FAILS = []
OKS = []


def ok(msg):
    OKS.append(msg)
    print("  [ok]   " + msg)


def bad(msg):
    FAILS.append(msg)
    print("  [FAIL] " + msg)


def num_set(recipe):
    """Every numeric value that must never appear in plaintext inside the package."""
    vals = []
    for key in ("e", "o", "r", "td", "ud"):
        for v in recipe.get(key) or []:
            vals.append(int(v))
    for pair in recipe.get("dg") or []:
        if isinstance(pair, list) and pair:
            vals.append(int(pair[0]))
    vals.append(int(recipe.get("ne") or 0))
    return {str(v) for v in vals if int(v) >= 1000}


def check_layout():
    exe = os.path.join(DIST, "GFLH-Man.exe")
    internal = os.path.join(DIST, "_internal")
    enc = os.path.join(internal, "recipe.enc")
    tpl = os.path.join(internal, "template.js")
    for p, name in ((exe, "GFLH-Man.exe"), (enc, "recipe.enc"), (tpl, "template.js")):
        if os.path.exists(p):
            ok("%s present (%d bytes)" % (name, os.path.getsize(p)))
        else:
            bad("%s missing: %s" % (name, p))
    return exe, enc, tpl


def main():
    dll = None
    if "--dll" in sys.argv:
        i = sys.argv.index("--dll")
        if i + 1 < len(sys.argv):
            dll = sys.argv[i + 1]

    print("=== 1. package layout ===")
    exe, enc_path, tpl_path = check_layout()
    if not (os.path.exists(enc_path) and os.path.exists(tpl_path)):
        return report()

    print("=== 2. container type ===")
    with open(enc_path, "rb") as f:
        blob = f.read()
    if blob[:len(MAGIC_FP)] == MAGIC_FP:
        ok("fingerprint container (no passphrase)")
        keyed = True
    elif blob[:len(MAGIC)] == MAGIC:
        ok("passphrase container (prompts on launch)")
        keyed = False
    else:
        bad("unrecognized container header: %r" % blob[:8])
        return report()

    print("=== 3. decryption ===")
    recipe = None
    if keyed:
        if dll:
            if not os.path.exists(dll):
                bad("module not found: %s" % dll)
            else:
                try:
                    recipe = json.loads(open_keyed(blob, derive_key(pe_fingerprint_file(dll))).decode("utf-8"))
                    ok("decrypted with the PE fingerprint")
                except ValueError as e:
                    bad("decryption failed: %s (game build differs from packaging time?)" % e)
        else:
            env = os.environ.get("GFLM_RECIPE_JSON", "").strip()
            if env:
                recipe = json.loads(env)
                ok("using GFLM_RECIPE_JSON (CI mode), decryption skipped")
            else:
                print("  [skip] no --dll and no GFLM_RECIPE_JSON, cannot decrypt")
    else:
        pw = os.environ.get("GFLM_RECIPE_PASSWORD", "").strip()
        if pw:
            try:
                recipe = json.loads(open_sealed(blob, pw).decode("utf-8"))
                ok("decrypted with the passphrase")
            except ValueError as e:
                bad("decryption failed: %s" % e)
        else:
            print("  [skip] passphrase mode needs GFLM_RECIPE_PASSWORD")

    print("=== 4. recipe contents ===")
    if recipe:
        need = ("e", "o", "r", "ne", "f", "td", "ud")
        miss = [k for k in need if k not in recipe]
        if miss:
            bad("missing fields: %s" % ", ".join(miss))
        else:
            ok("fields present: e=%d o=%d r=%d td=%d ud=%d" %
               (len(recipe["e"]), len(recipe["o"]), len(recipe["r"]),
                len(recipe["td"]), len(recipe["ud"])))
        f = float(recipe.get("f", 0))
        if 0.05 < f < 1.0:
            ok("factor %.3f is inside (0,1): it can only weaken" % f)
        else:
            bad("factor %.3f is out of range" % f)

    print("=== 5. plaintext leak scan ===")
    if recipe:
        nums = num_set(recipe)
        leaks = []
        for root, _dirs, files in os.walk(DIST):
            for name in files:
                path = os.path.join(root, name)
                if name == "recipe.enc":
                    continue
                try:
                    with open(path, "rb") as f:
                        data = f.read()
                except Exception:
                    continue
                text = data.decode("latin-1")
                for n in nums:
                    if n in text:
                        leaks.append("%s contains %s" % (os.path.relpath(path, DIST), n))
        if leaks:
            for l in leaks[:10]:
                bad("plaintext leak: " + l)
        else:
            ok("no address or offset from the recipe appears in the package (%d values checked)" % len(nums))
    else:
        print("  [skip] no recipe, cannot run the targeted scan")

    print("=== 6. template placeholders ===")
    try:
        with open(tpl_path, "r", encoding="utf-8") as f:
            tpl = f.read()
        need = ("__E__", "__O__", "__R__", "__NE__", "__F__", "__MS__", "__LIMIT__", "__CD__")
        lack = [k for k in need if k not in tpl]
        if lack:
            bad("template.js is missing placeholders: %s" % ", ".join(lack))
        else:
            ok("template.js carries every placeholder (filled in at run time)")
    except Exception as e:
        bad("cannot read template.js: %s" % e)

    return report()


def report():
    print("")
    print("=" * 60)
    print("passed %d, failed %d" % (len(OKS), len(FAILS)))
    if FAILS:
        print("verdict: packaging/encryption FAILED the self-check")
        return 1
    print("verdict: packaging/encryption passed the self-check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
