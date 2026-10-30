# tools/man_core.py
#
# Injection controller shared by the GUI and the CLI.
# It only uses the generic decrypt/render helpers from loader.py, so this file contains
# no addresses, offsets or coefficients.

import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from loader import decrypt, render, find_file   # noqa: E402


class Controller:
    """One injection session: start() blocks until stop() or until the game exits."""

    def __init__(self, process="GrilsFrontLine.exe", log=None):
        self.process = process
        self._log = log or (lambda msg: None)
        self._stop = threading.Event()
        self._session = None
        self._script = None
        self._thread = None
        self._stopping = False
        self.running = False
        self.objects = 0
        self.total_writes = 0
        self.last_error = None

    # ------------------------------------------------------------ helpers
    def log(self, msg):
        try:
            self._log(msg)
        except Exception:
            pass

    def _on_message(self, message, data):
        if message.get("type") == "error":
            self.log("[x] %s" % message.get("description"))
            return
        if message.get("type") != "send":
            return
        p = message.get("payload") or {}
        t = p.get("type")
        if t == "ready":
            self.objects = p.get("objects") or 0
            self.log("[*] ready: %s objects registered" % self.objects)
        elif t == "tick":
            self.objects = p.get("objects")
            self.total_writes = p.get("total") or self.total_writes
            flag = ""
            if p.get("block"):
                flag = " (halted, no writes)"
            elif p.get("busy"):
                flag = " (tearing down)"
            if self.objects is not None and int(self.objects) >= 0:
                self.log("objects %s / writes this round %s / total %s%s"
                         % (p.get("objects"), p.get("round"), p.get("total"), flag))
        elif t == "teardown":
            self.objects = 0
            self.log("[*] battle ended, cleared %s objects (entry %s)"
                     % (p.get("cleared", "?"), p.get("rva")))
        elif t == "halted":
            self.log("[*] script halted")
        elif t == "diag":
            self.log("[diag] %s" % p.get("text"))
        else:
            self.log("[%s] %r" % (t, p))

    # ------------------------------------------------------------ lifecycle
    def attach(self):
        import frida
        for i in range(5):
            try:
                return frida.attach(self.process)
            except Exception as e:
                self.log("[*] attach retry %d/5: %s" % (i + 1, e))
                time.sleep(1)
        return None

    def start(self):
        """Block until stop() or until the game exits. Returns True on a clean exit."""
        if self.running:
            return False
        self._stop.clear()
        self.running = True
        try:
            enc = find_file("recipe.enc")
            tpl = find_file("template.js")
            if not enc or not tpl:
                raise RuntimeError("recipe.enc or template.js not found")

            with open(enc, "rb") as f:
                blob = f.read()
            with open(tpl, "r", encoding="utf-8") as f:
                template = f.read()

            session = self.attach()
            if session is None:
                raise RuntimeError("attach failed: the game is not running, or administrator rights are required")
            self._session = session

            recipe = decrypt(blob, session, None)
            js = render(recipe, template)
            self.log("[*] recipe loaded (%d entries / %d fields)" % (len(recipe["e"]), len(recipe["o"])))

            script = session.create_script(js)
            script.on("message", self._on_message)
            script.load()
            self._script = script

            def on_detach(*a):
                if self._stopping:
                    self.log("[*] stopped")
                else:
                    self.log("[!] game process detached (tool stopped automatically)")
                self._stop.set()

            try:
                session.on("detached", on_detach)
            except Exception:
                pass

            self.log("[*] injected. Enter a battle to take effect.")
            while not self._stop.is_set():
                time.sleep(0.2)
            return True
        except Exception as e:
            self.last_error = str(e)
            self.log("[error] %s" % e)
            return False
        finally:
            self._teardown()
            self.running = False

    def _teardown(self):
        """Ask the script to stand down first, then remove the hooks.

        Unloading straight away races with the game tearing battle objects down, which
        used to crash the client. The 400 ms window lets the agent stop its timer and
        clear its object table before the hooks disappear.
        """
        self._stopping = True
        try:
            if self._script is not None:
                self._script.post({"type": "control", "payload": {"halt": True}})
                time.sleep(0.4)
        except Exception:
            pass
        try:
            if self._script is not None:
                self._script.unload()
        except Exception:
            pass
        time.sleep(0.1)
        try:
            if self._session is not None:
                self._session.detach()
        except Exception:
            pass
        self._script = None
        self._session = None

    def start_async(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self.start, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                self.log("[!] stop timed out, still finishing up")
