/* =========================================================
   本地抓包控制面板（由 map.py 提供的 /api/* 接口驱动）
   - 用普通静态服务器托管时（没有 /api/status），面板不会出现
   - 实时包通过 /api/stream (SSE) 推过来，再转给页面的 updateLiveMap/updateSpawnLive
   ========================================================= */
(function () {
  "use strict";

  var STARTED = false;

  function api(path, method) {
    return fetch(path, { method: method || "GET", cache: "no-store" }).then(function (response) {
      if (!response.ok) throw new Error(String(response.status));
      return response.json();
    });
  }

  function addStyle(css) {
    var style = document.createElement("style");
    style.textContent = css;
    document.head.appendChild(style);
  }

  function buildPanel() {
    if (document.getElementById("gflh-control")) return;

    addStyle(
      "#gflh-control{position:fixed;right:14px;bottom:14px;z-index:99999;width:236px;padding:10px 12px;" +
      "border-radius:8px;background:#111111f2;border:1px solid #f4c43099;box-shadow:0 8px 24px #00000099;" +
      "color:#eaeaea;font:13px/1.5 'Microsoft YaHei','Noto Sans SC',sans-serif;user-select:none}" +
      "#gflh-control .row{display:flex;align-items:center;gap:8px}" +
      "#gflh-control .dot{width:8px;height:8px;border-radius:50%;background:#777}" +
      "#gflh-control .dot.on{background:#4ade80;box-shadow:0 0 6px #4ade80}" +
      "#gflh-control .state{margin-left:auto;color:#9a9a9a;font-size:12px}" +
      "#gflh-control .buttons{margin-top:8px;gap:6px}" +
      "#gflh-control button{flex:1;padding:5px 0;cursor:pointer;font:inherit;font-size:12px;" +
      "color:#eaeaea;background:#1d1d1d;border:1px solid #3a3a3a;border-radius:5px}" +
      "#gflh-control button:hover{border-color:#f4c430;color:#f4c430}" +
      "#gflh-control button:disabled{opacity:.45;cursor:default}" +
      "#gflh-control .hint{margin-top:7px;color:#8a8a8a;font-size:11px;line-height:1.45;min-height:30px}" +
      "#gflh-control .stats{margin-top:6px;padding-top:6px;border-top:1px solid #2a2a2a;" +
      "color:#9a9a9a;font-size:11px;line-height:1.55}" +
      "#gflh-control .stats b{color:#eaeaea;font-weight:600}" +
      "#gflh-control .stats .ok{color:#4ade80}" +
      "#gflh-control .stats .warn{color:#f4c430;font-weight:600}"
    );

    var box = document.createElement("div");
    box.id = "gflh-control";
    box.innerHTML =
      '<div class="row"><span class="dot" id="gflh-dot"></span><b>抓包监控</b><span class="state" id="gflh-state">未启动</span></div>' +
      '<div class="row buttons">' +
        '<button id="gflh-start">开始</button>' +
        '<button id="gflh-stop">停止</button>' +
        '<button id="gflh-quit">退出</button>' +
      '</div>' +
      '<div class="hint" id="gflh-hint">点「开始」后会设置系统代理；请在游戏里重新登录一次以捕获密钥。</div>' +
      '<div class="stats" id="gflh-stats">未开始监控</div>';
    document.body.appendChild(box);

    function setState(text, running) {
      document.getElementById("gflh-state").textContent = text;
      document.getElementById("gflh-dot").className = "dot" + (running ? " on" : "");
      document.getElementById("gflh-start").disabled = !!running;
      document.getElementById("gflh-stop").disabled = !running;
    }

    function say(message) {
      document.getElementById("gflh-hint").textContent = message;
    }

    document.getElementById("gflh-start").onclick = function () {
      setState("启动中…", false);
      api("/api/start").then(function (result) {
        setState(result.running ? "运行中" : "未启动", result.running);
        say(result.message || "");
      }).catch(function (error) { say("调用失败：" + error.message); });
    };

    document.getElementById("gflh-stop").onclick = function () {
      api("/api/stop").then(function (result) {
        setState("未启动", false);
        say(result.message || "");
      }).catch(function (error) { say("调用失败：" + error.message); });
    };

    document.getElementById("gflh-quit").onclick = function () {
      api("/api/quit").catch(function () { window.close(); });
    };

    function renderStats(status) {
      var el = document.getElementById("gflh-stats");
      if (!status.running) {
        el.innerHTML = '<span class="warn">未开始监控</span>';
        return;
      }
      var packets = status.packets || {};
      var total = packets.s2c || 0;
      if (!total) {
        el.innerHTML = '<span class="warn">还没收到数据包</span><br>' +
          "请在游戏里重新登录一次（代理要重新协商密钥）";
        return;
      }
      var when = status.lastPacketAt
        ? new Date(status.lastPacketAt * 1000).toLocaleTimeString("zh-CN", { hour12: false })
        : "-";
      var gotMap = (packets.map || 0) > 0;
      var gotSpawn = (packets.spawn || 0) > 0;
      el.innerHTML =
        '<span class="' + (gotMap ? "ok" : "warn") + '">' + (gotMap ? "✓" : "…") + "</span> 点位包 <b>" + (packets.map || 0) + "</b>　" +
        '<span class="' + (gotSpawn ? "ok" : "warn") + '">' + (gotSpawn ? "✓" : "…") + "</span> 刷怪包 <b>" + (packets.spawn || 0) + "</b>　" +
        "阵亡 <b>" + (packets.death || 0) + "</b>" +
        "<br>共 <b>" + total + "</b> 个 S2C，最近 " + when +
        (status.clients ? "" : "<br><span class=\"warn\">页面未连上实时通道</span>");
    }

    function refresh() {
      api("/api/status").then(function (status) {
        setState(status.running ? "运行中 :" + status.port : "未启动", status.running);
        renderStats(status);
      }).catch(function () {});
    }

    refresh();
    setInterval(refresh, 3000);
    connectStream(say);
  }

  function connectStream(say) {
    if (typeof EventSource === "undefined") return;
    var source = new EventSource("/api/stream");

    source.addEventListener("gfl", function (event) {
      var message;
      try {
        message = JSON.parse(event.data);
      } catch (error) {
        return;
      }
      var handler = message && message.handler;
      if (!handler || typeof window[handler] !== "function") return;
      try {
        window[handler](message.payload);
      } catch (error) {
        if (say) say("渲染出错：" + error.message);
      }
    });

    source.onerror = function () {
      /* 断线由 EventSource 自动重连，这里不打断 */
    };
  }

  function boot() {
    if (STARTED) return;
    STARTED = true;
    api("/api/status").then(function () {
      buildPanel();
    }).catch(function () {
      /* 没有 /api/status：说明只是静态托管，不显示控制面板 */
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
