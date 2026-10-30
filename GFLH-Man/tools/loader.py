
# tools/loader.py
#
# CLI entry point. Reads the encrypted recipe, decrypts it, renders template.js and
# injects the result into the running game.
#
# Two container formats are supported and detected by magic bytes:
#   GFLM2  fingerprint mode - the key is derived from the live GameAssembly.dll PE
#          fingerprint, so no passphrase is prompted. The fingerprint is read by a
#          throw-away bootstrap script that only reads the module header and then unloads.
#   GFLM1  passphrase mode  - the passphrase is prompted (up to 3 attempts).
#
# Usage:
#   python tools/loader.py [--dry-run] [--dll <GameAssembly.dll>] [<process>]

import getpass
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crypto_box import open_sealed, open_keyed, derive_key, pe_fingerprint_file, MAGIC, MAGIC_FP

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = "GameAssembly.dll"


BOOTSTRAP_JS = r"""
(function () {
  var m = Process.findModuleByName("%s");
  if (!m) { send({ type: "err", msg: "module not found" }); return; }
  function hex(a) {
    var s = "";
    for (var i = 0; i < a.length; i++) {
      var h = a[i].toString(16);
      s += h.length < 2 ? "0" + h : h;
    }
    return s;
  }
  try {
    var head = new Uint8Array(m.base.readByteArray(0x40));
    var e = head[0x3C] + head[0x3D] * 256 + head[0x3E] * 65536 + head[0x3F] * 16777216;
    var coff = new Uint8Array(m.base.add(e + 4).readByteArray(20));
    send({ type: "pe", head: hex(head), coff: hex(coff), size: m.size });
  } catch (err) {
    send({ type: "err", msg: String(err) });
  }
})();
""" % MODULE


def find_file(name):
    cands = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        cands.append(meipass)
    cands += [HERE, os.getcwd(), os.path.dirname(sys.executable)]
    for d in cands:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return None


def render(recipe, template):
    js = template
    required = {
        "__E__": json.dumps(recipe["e"]),
        "__O__": json.dumps(recipe["o"]),
        "__R__": json.dumps(recipe.get("r") or []),
        "__NE__": str(recipe["ne"]),
        "__F__": repr(float(recipe["f"])),
        "__MS__": str(recipe.get("ms", 0)),
        "__LIMIT__": str(recipe.get("limit", 5000)),
        "__CD__": str(recipe.get("cd", 16)),
    }
    optional = {
        "__DG__": json.dumps(recipe.get("dg") or []),
        "__TD__": json.dumps(recipe.get("td") or []),
        "__UD__": json.dumps(recipe.get("ud") or []),
    }
    for k, v in required.items():
        if k not in js:
            raise SystemExit("template is missing placeholder: %s" % k)
        js = js.replace(k, v)
    for k, v in optional.items():
        js = js.replace(k, v)
    for k in required:
        if k in js:
            raise SystemExit("template still has an unreplaced placeholder: %s" % k)
    return js


def attach(process, tries=5):
    import frida
    for i in range(tries):
        try:
            return frida.attach(process)
        except Exception as e:
            print("[*] attach retry %d/%d: %s" % (i + 1, tries, e))
            time.sleep(1)
    return None


def grab_fingerprint(session):
    box = {}
    done = threading.Event()

    def on_msg(message, data):
        if message.get("type") != "send":
            return
        p = message.get("payload") or {}
        if p.get("type") == "pe":
            box["fp"] = bytes.fromhex(p["head"]) + bytes.fromhex(p["coff"])
            box["size"] = p.get("size")
        elif p.get("type") == "err":
            box["err"] = p.get("msg")
        done.set()

    script = session.create_script(BOOTSTRAP_JS)
    script.on("message", on_msg)
    script.load()
    done.wait(timeout=15)
    try:
        script.unload()
    except Exception:
        pass
    if "fp" not in box:
        raise RuntimeError(box.get("err") or "Timeout waiting for fingerprint")
    return box["fp"], box.get("size")


def decrypt(blob, session, dll):
    if blob[:len(MAGIC_FP)] == MAGIC_FP:
        if dll:
            fp = pe_fingerprint_file(dll)
            print("[*] fingerprint from file: %s" % dll)
        elif session is not None:
            fp, size = grab_fingerprint(session)
            print("[*] fingerprint from running %s (%s bytes)" % (MODULE, size))
        else:
            raise SystemExit("[x] The package is encrypted with module fingerprints, and the game needs to be running (or use --dll to specify GameAssembly.dll)")
        return json.loads(open_keyed(blob, derive_key(fp)).decode("utf-8"))
    if blob[:len(MAGIC)] == MAGIC:
        for _ in range(3):
            try:
                return json.loads(open_sealed(blob, getpass.getpass("Password:")).decode("utf-8"))
            except ValueError as e:
                print("[x] %s" % e)
        raise SystemExit("[x] Password incorrect too many times")
    raise SystemExit("[x] Unrecognized container format")


def main():
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    dll = None
    if "--dll" in sys.argv:
        i = sys.argv.index("--dll")
        if i + 1 < len(sys.argv):
            dll = sys.argv[i + 1]
            argv = [a for a in argv if a != dll]
    process = argv[0] if argv else "GrilsFrontLine.exe"

    enc_path = find_file("recipe.enc")
    tpl_path = find_file("template.js")
    if not enc_path:
        print("[error] Not found: recipe.enc")
        return 1
    if not tpl_path:
        print("[error] Not found: template.js")
        return 1

    with open(enc_path, "rb") as f:
        blob = f.read()
    with open(tpl_path, "r", encoding="utf-8") as f:
        template = f.read()

    keyed = blob[:len(MAGIC_FP)] == MAGIC_FP

    if dry:
        session = None if (dll or not keyed) else attach(process)
        if keyed and session is None and not dll:
            print("[error] dry-run requires the game to be running, or use --dll to specify the file")
            return 1
        recipe = decrypt(blob, session, dll)
        if session is not None:
            try:
                session.detach()
            except Exception:
                pass
        js = render(recipe, template)
        print("[*] Recipe decrypted (%d entries / %d fields), template rendered %d bytes"
              % (len(recipe["e"]), len(recipe["o"]), len(js)))
        print("[*] dry-run: not injecting")
        return 0

    session = attach(process)
    if session is None:
        print("[error] attach failed")
        return 1

    try:
        recipe = decrypt(blob, session, dll)
    except ValueError as e:
        print("[x] %s" % e)
        print("    Game version is inconsistent with the packing time. Re-package:")
        print("    python mk/build_man.py --local --dll \"C:\\...\\GameAssembly.dll\"")
        return 1
    except SystemExit as e:
        print(e)
        return 1

    js = render(recipe, template)

    def on_message(message, data):
        if message.get("type") == "error":
            print("[x] %s" % message.get("description"))
            return
        if message.get("type") != "send":
            return
        p = message.get("payload") or {}
        t = p.get("type")
        if t == "ready":
            print("[*] Ready: %s objects registered" % p.get("objects"))
        elif t == "tick":
            print("[*] Object %s / Round write %s / Total %s"
                  % (p.get("objects"), p.get("round"), p.get("total")))
        else:
            print("[%s] %r" % (t, p))

    script = session.create_script(js)
    script.on("message", on_message)
    script.load()

    exited = threading.Event()
    stopping = {"v": False}

    def on_detach(*a):
        if stopping["v"]:
            print("[*] stopped.")
        else:
            print("[!] game process detached (tool stopped automatically).")
        exited.set()

    try:
        session.on("detached", on_detach)
    except Exception:
        pass

    print("[*] Game injected. Ctrl+C to exit.")
    try:
        while not exited.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[*] Stopping.")
    finally:
        stopping["v"] = True
        try:
            script.post({"type": "control", "payload": {"halt": True}})
            time.sleep(0.4)
        except Exception:
            pass
        try:
            script.unload()
        except Exception:
            pass
        time.sleep(0.1)
        try:
            session.detach()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
