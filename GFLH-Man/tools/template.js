// Runtime-injected script. Every placeholder (__X__) is filled in by loader.render()
// from the decrypted recipe, so this file itself carries no addresses or coefficients.
//
// E     entry offsets; E[0] is the damage entry, which is the only hook we install
// O     target field offsets (the values combat actually reads)
// R     base field offsets  (weapon + equipment, i.e. the "panel" value)
// NE    offset of the faction byte, used to skip anything that is not friendly
// F     scale factor, must be < 1 (this is a debuff, never a buff)
// MS    expected module size, used as a version check
// CD    offset of the per-unit data pointer inside the skill implementation object
// DG    optional diagnostic [offset, label] pairs (empty unless built with --diag)

var E = __E__;
var O = __O__;
var R = __R__;
var NE = __NE__;
var F = __F__;
var MS = __MS__;
var LIMIT = __LIMIT__;
var CD = __CD__;
var DG = __DG__;

if (!(F > 0.05 && F < 1)) throw new Error("bad factor");

var mod = Process.findModuleByName("GameAssembly.dll");
if (!mod) throw new Error("module not found");
if (MS && mod.size !== MS) throw new Error("module size mismatch");

var base = mod.base;
var objs = {};       // object pointer -> true (friendly units seen so far)
var wrote = {};      // "<ptr>#<field index>" -> raw value we last wrote
var klasses = {};    // whitelist of klass pointers that belong to battle character data
var n = 0;
var halted = false;
var lastBeat = 0;

function s(p) { try { return p.toString(); } catch (e) { return null; } }

// First field of an Il2Cpp object is its klass pointer.
function klassOf(p) {
  try { return p.readPointer().toString(); } catch (e) { return null; }
}

// Remember an object only if its klass looks valid. Classes are learned from objects
// handed to us by the game itself, so a recycled pointer from another type is rejected.
function remember(p) {
  var k = s(p);
  if (!k) return null;
  var c = klassOf(p);
  if (!c) return null;
  klasses[c] = 1;
  objs[k] = true;
  return k;
}

function alive(p) {
  var c = klassOf(p);
  return c !== null && klasses[c] === 1;
}

// Fixed-point (32.32) field -> double, for diagnostics only.
function fpOf(p, off) {
  try { return Number(p.add(off).readU64().toString()) / 4294967296; } catch (e) { return null; }
}

var diagDone = {};
var diagLeft = 8;

// Diagnostic dump: prints the candidate "base value" fields once per object.
// DG entries are [offset, label] pairs supplied by the encrypted recipe.
function diagnose(p, k) {
  if (DG.length === 0) return;
  if (diagLeft <= 0 || diagDone[k]) return;
  diagDone[k] = 1;
  diagLeft--;
  var out = [];
  for (var i = 0; i < DG.length; i++) {
    var item = DG[i];
    var off = (item instanceof Array) ? item[0] : item;
    var label = (item instanceof Array && item[1]) ? item[1] : ("f" + i);
    var v = fpOf(p, off);
    out.push(label + "=" + (v === null ? "?" : v.toFixed(2)));
  }
  send({ type: "diag", text: out.join("  ") });
}

function apply() {
  var cnt = 0;
  for (var k in objs) {
    var p = ptr(k);
    if (!alive(p)) { delete objs[k]; continue; }

    var side;
    try { side = p.add(NE).readU8(); } catch (e) { delete objs[k]; continue; }
    if (side !== 0) continue;   // enemies are left untouched

    diagnose(p, k);

    for (var i = 0; i < O.length; i++) {
      var addr = p.add(O[i]);
      var raw;
      try { raw = Number(addr.readU64().toString()); } catch (e) { continue; }
      if (!(raw > 0 && raw < 1.1e15)) continue;

      var kk = k + "#" + i;
      if (wrote[kk] === String(raw)) continue;   // unchanged since our last write, skip

      // Disaster only reduces the base value; flat bonuses added by skills stay intact:
      //   new = current - (1 - F) * base
      // If the base value is unavailable, fall back to scaling the whole value.
      var out = 0;
      var baseVal = null;
      if (i < R.length) {
        try { baseVal = Number(p.add(R[i]).readU64().toString()); } catch (e) { baseVal = null; }
      }
      if (baseVal !== null && baseVal > 0 && baseVal < 1.1e15 && baseVal <= raw) {
        out = raw - Math.floor(baseVal * (1 - F));
      } else {
        out = Math.floor(raw * F);
      }
      if (!(out > 0) || out >= raw) continue;    // never increase a value

      try { addr.writeU64(out); } catch (e) { continue; }
      wrote[kk] = String(out);
      cnt++;
    }
  }
  n += cnt;
  return cnt;
}

// The only hook we install: the damage entry, i.e. the moment a shot is fired.
// At this instant the attacker and the target are guaranteed to be alive, so we never
// touch memory while the game is tearing a battle down.
Interceptor.attach(base.add(E[0]), {
  onEnter: function (args) {
    if (halted) return;
    lastBeat = Date.now();
    try {
      var impl = this.context.rcx;
      var atk = impl.add(CD).readPointer();   // the unit data behind this skill object
      if (!atk.isNull()) remember(atk);
    } catch (e) { }
    try { remember(this.context.rdx); } catch (e) { }   // target
    try { apply(); } catch (e) { }
  }
});

// The host sends this before detaching, so no callback runs during teardown.
recv("control", function (msg) {
  try {
    if (msg && msg.halt) {
      halted = true;
      objs = {};
      wrote = {};
      send({ type: "halted" });
    }
  } catch (e) { }
});

send({ type: "ready", objects: 0, writes: n });

// Status reporting only; the timer never reads or writes game memory.
setInterval(function () {
  try {
    if (halted) return;
    send({ type: "tick", objects: Object.keys(objs).length, round: 0, total: n });
  } catch (e) { }
}, LIMIT);
