"use strict";

const STATE = {
  index: [],
  data: null,
  filter: "",
  selectedTeamId: null,
};

const BELONG_CLASS = { 0: "b0", 1: "b1", 2: "b2", 3: "b3", 99: "b99" };

const $ = (id) => document.getElementById(id);

/* ------------------------------------------------------------------ utils */
function esc(value) {
  if (value === null || value === undefined) return "";
  return String(value).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

function fmtInt(value) {
  if (value === null || value === undefined || value === "") return "—";
  const num = Number(value);
  return Number.isNaN(num) ? esc(value) : num.toLocaleString("zh-CN");
}

function dash(value) {
  return value === null || value === undefined || value === "" ? "—" : esc(value);
}

async function fetchJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`${url} 返回 HTTP ${response.status}`);
  return response.json();
}

/* ------------------------------------------------------------------ boot */
async function boot() {
  try {
    let index;
    try {
      index = await fetchJson("data/index.json");
    } catch (error) {
      index = [{ missionId: 11403, name: "自画像-厚涂", file: "mission-11403.json" }];
    }
    if (!Array.isArray(index) || !index.length) throw new Error("data/index.json 为空");
    STATE.index = index;

    const select = $("mission-select");
    select.innerHTML = index
      .map((item) => `<option value="${item.missionId}">${esc(item.name || item.missionId)}</option>`)
      .join("");
    select.addEventListener("change", () => loadMission(Number(select.value)));

    $("filter").addEventListener("input", (event) => {
      STATE.filter = event.target.value.trim().toLowerCase();
      renderEnemyTable();
      renderNodeTable();
    });

    if (location.protocol === "file:") {
      throw new Error(
        "浏览器禁止 file:// 页面读取本地 JSON。\n请在 tables 目录下运行：python serve.py\n然后访问它打印出的地址（例如 http://127.0.0.1:8093/）。"
      );
    }

    const fromHash = new URLSearchParams(location.hash.slice(1)).get("m");
    const wanted = Number(fromHash) || Number(index[0].missionId);
    await loadMission(wanted);
  } catch (error) {
    $("loading").hidden = true;
    const box = $("error");
    box.hidden = false;
    box.textContent = `无法加载数据：${error.message}`;
    console.error(error);
  }
}

async function loadMission(missionId) {
  const meta = STATE.index.find((item) => Number(item.missionId) === Number(missionId));
  const file = (meta && meta.file) || `mission-${missionId}.json`;

  $("loading").hidden = false;
  $("error").hidden = true;
  $("content").hidden = true;

  const data = await fetchJson(`data/${file}`);
  STATE.data = data;
  STATE.selectedTeamId = null;
  STATE.filter = "";
  $("filter").value = "";

  const select = $("mission-select");
  if (select.value !== String(missionId)) select.value = String(missionId);

  // 支持 #m=11403&team=6589201 直接定位到某支梯队
  const params = new URLSearchParams(location.hash.slice(1));
  const wantedTeam = Number(params.get("team") || 0);
  if (wantedTeam && data.teams.some((team) => Number(team.id) === wantedTeam)) {
    STATE.selectedTeamId = wantedTeam;
  }

  render();
  syncHash();
  $("loading").hidden = true;
  $("content").hidden = false;
}

function syncHash() {
  const params = new URLSearchParams();
  params.set("m", STATE.data.mission.id);
  if (STATE.selectedTeamId) params.set("team", STATE.selectedTeamId);
  history.replaceState(null, "", `#${params.toString()}`);
}

/* ------------------------------------------------------------------ render */
function render() {
  const data = STATE.data;
  renderHero(data);
  renderCards(data);
  renderInfo(data);
  renderTopology(data);
  renderEnemyTable();
  renderNodeTable();
  renderBuildings(data);
  renderPortals(data);

  $("meta").textContent =
    `任务 ${data.mission.id} · 数据服 ${data.server} · 回合 ${data.turn} · 生成于 ${data.generatedAt}`;
}

function renderHero(data) {
  const mission = data.mission;
  const crumbs = [mission.activity, mission.subEvent || mission.chapter, mission.title]
    .filter(Boolean)
    .filter((part, i, arr) => arr.indexOf(part) === i);

  $("crumbs").innerHTML = crumbs
    .map((part, i) => (i ? `<span class="sep">›</span>${esc(part)}` : esc(part)))
    .join("");

  $("title").textContent = mission.title || mission.name;

  const chips = [];
  chips.push(`<span class="chip gold">任务 ${mission.id}</span>`);
  chips.push(`<span class="chip ${mission.night ? "night" : ""}">${mission.night ? "夜战" : "昼战"}</span>`);
  if (mission.endless) chips.push(`<span class="chip">积分模式</span>`);
  chips.push(`<span class="chip">难度 ${fmtInt(mission.difficulty)}</span>`);
  chips.push(`<span class="chip">推荐等级 ${mission.recommendLevel}</span>`);
  chips.push(`<span class="chip">回合上限 ${mission.turnLimit}</span>`);
  $("chips").innerHTML = chips.join("");

  const desc = $("desc");
  if (mission.description) {
    desc.textContent = mission.description;
    desc.hidden = false;
  } else {
    desc.hidden = true;
  }
}

function renderCards(data) {
  const stats = data.stats;
  const cards = [
    ["节点", stats.spots, ""],
    ["敌方梯队", stats.enemyTeams, "支"],
    ["敌方站位", stats.enemySpots, "处"],
    ["建筑", stats.buildings, "个"],
    ["传送", stats.portals, "处"],
    ["敌方单位", stats.units, "个"],
  ];
  $("cards").innerHTML = cards
    .map(([label, value, unit]) => `
      <div class="card">
        <div class="label">${label}</div>
        <div class="value">${fmtInt(value)}${unit ? `<small>${unit}</small>` : ""}</div>
      </div>`)
    .join("");
}

function renderInfo(data) {
  const m = data.mission;
  const limits = m.limits;
  const rows = [
    ["推荐等级", `${m.recommendLevel}${m.levelPenalty !== null ? `<span class="sub">等级惩罚 ${m.levelPenalty}</span>` : ""}`],
    ["回合上限", `${m.turnLimit} 回合`],
    ["基础经验", fmtInt(m.baseExp)],
    ["梯队限制", `格里芬 ${limits.gk} · 重装 ${limits.hoc} · 联合 ${limits.coalition} · 机甲 ${limits.vehicle}`],
    ["梯队总数", limits.total],
    ["通关条件", m.winConditions.length ? m.winConditions.map(esc).join("；") : "—"],
    ["通关奖励", m.rewards.length ? m.rewards.map(esc).join("，") : "未配置"],
    ["地图资源", `${esc(m.mapRes)}<span class="sub">${esc(m.mapInfo)}</span>`],
  ];

  $("info").innerHTML = `
    <dl class="info-list">
      ${rows.map(([key, value]) => `<dt>${key}</dt><dd>${value}</dd>`).join("")}
    </dl>
    ${renderBelongBar(data.spots)}`;
}

function renderBelongBar(spots) {
  const order = [1, 2, 3, 99, 0];
  const color = { 1: "#4da3ff", 2: "#ff5d5d", 3: "#ffb347", 99: "#4a4a4a", 0: "#8a8a8a" };
  const label = { 1: "我方", 2: "敌方", 3: "第三方", 99: "视野外", 0: "中立" };
  const total = spots.length || 1;
  const counts = order.map((key) => [key, spots.filter((spot) => spot.belong === key).length])
    .filter(([, count]) => count > 0);

  return `
    <div class="belong-bar" title="节点归属分布">
      ${counts.map(([key, count]) =>
        `<span style="width:${(count / total * 100).toFixed(2)}%;background:${color[key]}"></span>`).join("")}
    </div>
    <div class="belong-legend">
      ${counts.map(([key, count]) =>
        `<span><i style="background:${color[key]}"></i>${label[key]} ${count}</span>`).join("")}
    </div>`;
}

/* ------------------------------------------------------------------ 拓扑 */
function renderTopology(data) {
  const spots = data.spots;
  if (!spots.length) {
    $("topology").innerHTML = '<div class="empty">没有节点</div>';
    return;
  }

  const width = 900;
  const height = 560;
  const pad = 26;
  const xs = spots.map((s) => s.x);
  const ys = spots.map((s) => s.y);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const scale = Math.min((width - pad * 2) / Math.max(maxX - minX, 1), (height - pad * 2) / Math.max(maxY - minY, 1));
  const offsetX = (width - (maxX - minX) * scale) / 2;
  const offsetY = (height - (maxY - minY) * scale) / 2;
  const project = (x, y) => [offsetX + (x - minX) * scale, height - offsetY - (y - minY) * scale];

  const byId = new Map(spots.map((s) => [s.id, s]));
  const teamBySpot = new Map(data.enemyRows.map((row) => [row.spotId, row.teamId]));
  const teamById = new Map(data.teams.map((team) => [team.id, team]));
  const selected = STATE.selectedTeamId;

  const edges = [];
  const seen = new Set();
  for (const spot of spots) {
    for (const target of spot.route) {
      if (!byId.has(target)) continue;
      const key = spot.id < target ? `${spot.id}-${target}` : `${target}-${spot.id}`;
      if (seen.has(key)) continue;
      seen.add(key);
      const [x1, y1] = project(spot.x, spot.y);
      const [x2, y2] = project(byId.get(target).x, byId.get(target).y);
      edges.push(`<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" />`);
    }
  }

  const nodes = spots.map((spot) => {
    const [cx, cy] = project(spot.x, spot.y);
    const radius = spot.type === 1 ? 7 : spot.type === 7 ? 6 : 4.5;
    const teamId = teamBySpot.get(spot.id);
    const team = teamId ? teamById.get(teamId) : null;
    const tip = [
      `#${spot.id}`,
      spot.typeLabel,
      spot.belongLabel,
      team ? `梯队 ${teamId} ${team.leader || ""}` : "",
    ].filter(Boolean).join(" · ");
    const highlight = teamId && selected && Number(teamId) === Number(selected)
      ? `<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${radius + 5}" fill="none" stroke="#f4c430" stroke-width="2" />`
      : "";
    return `<g class="node ${BELONG_CLASS[spot.belong] || ""}">
      ${highlight}
      <circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${radius}" />
      <title>${esc(tip)}</title>
    </g>`;
  });

  $("topology").innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="节点拓扑示意图">
      <g class="edges">${edges.join("")}</g>
      <g class="nodes">${nodes.join("")}</g>
    </svg>
    <style>
      #topology .edges line { stroke: #5a5a5a; stroke-width: 1.1; opacity: .55; }
      #topology .nodes circle { stroke: #0c0c0c; stroke-width: 1; }
      #topology .b1 circle { fill: #4da3ff; }
      #topology .b2 circle { fill: #ff5d5d; }
      #topology .b3 circle { fill: #ffb347; }
      #topology .b99 circle { fill: #4a4a4a; }
      #topology .b0 circle { fill: #8a8a8a; }
    </style>`;

  $("legend").innerHTML = [
    ["#4da3ff", "我方"],
    ["#ff5d5d", "敌方"],
    ["#ffb347", "第三方"],
    ["#4a4a4a", "视野外"],
    ["#f4c430", "当前选中梯队"],
  ].map(([color, label]) => `<span><i style="background:${color}"></i>${label}</span>`).join("");
}

/* ------------------------------------------------------------------ 敌方梯队 */
function matchesFilter(text) {
  return !STATE.filter || String(text).toLowerCase().includes(STATE.filter);
}

function renderEnemyTable() {
  const data = STATE.data;
  if (!data) return;
  const teamById = new Map(data.teams.map((team) => [team.id, team]));

  const rows = data.enemyRows.filter((row) => {
    const team = teamById.get(row.teamId);
    return matchesFilter([row.spotId, row.teamId, row.alignment, row.ai, team && team.leader]
      .concat(row.composition).join(" "));
  });

  $("enemy-count").textContent = `${rows.length} / ${data.enemyRows.length}`;

  if (!rows.length) {
    $("enemy-table").innerHTML = '<div class="empty">没有匹配的梯队</div>';
    return;
  }

  const body = rows.map((row) => {
    const team = teamById.get(row.teamId) || {};
    const selected = Number(STATE.selectedTeamId) === Number(row.teamId) ? " selected" : "";
    const ceTitle = team.fakeCe ? `游戏内展示值；按公式计算：600 系数 ${fmtInt(team.ce600)}，300 系数 ${fmtInt(team.ce300)}` : "";
    return `
      <tr class="team-row${selected}" data-team="${row.teamId}" data-spot="${row.spotId}">
        <td class="mono">${row.spotId}</td>
        <td class="mono">${row.teamId}</td>
        <td>${dash(team.leader)}</td>
        <td class="${row.kind !== "enemy" ? "kind-" + row.kind : ""}">${esc(row.alignment)}</td>
        <td>${dash(row.ai)}</td>
        <td class="num" title="${esc(ceTitle)}">${team.ce === null ? "—" : fmtInt(team.ce)}</td>
        <td class="wrap">${row.composition.length ? row.composition.map(esc).join("、") : "—"}</td>
        <td class="wrap">${row.drops.length ? row.drops.map(esc).join("、") : "—"}</td>
        <td class="num">${team.units ? team.units.length : 0}</td>
      </tr>`;
  }).join("");

  $("enemy-table").innerHTML = `
    <table>
      <thead>
        <tr>
          <th>节点</th><th>梯队</th><th>队长</th><th>阵营</th><th>行动逻辑</th>
          <th class="num">效能</th><th>编成</th><th>掉落</th><th class="num">单位</th>
        </tr>
      </thead>
      <tbody>${body}</tbody>
    </table>`;

  $("enemy-table").querySelectorAll(".team-row").forEach((tr) => {
    tr.addEventListener("click", () => {
      const teamId = Number(tr.dataset.team);
      STATE.selectedTeamId = STATE.selectedTeamId === teamId ? null : teamId;
      syncHash();
      renderEnemyTable();
      renderUnitDetail();
      renderTopology(STATE.data);
    });
  });

  renderUnitDetail();
}

function renderUnitDetail() {
  const data = STATE.data;
  const teamId = STATE.selectedTeamId;
  const box = $("unit-detail");

  if (!teamId) {
    box.innerHTML = "";
    return;
  }

  const team = data.teams.find((item) => Number(item.id) === Number(teamId));
  if (!team) {
    box.innerHTML = "";
    return;
  }

  const spots = data.enemyRows.filter((row) => Number(row.teamId) === Number(teamId)).map((row) => row.spotId);
  const spotText = spots.length ? `出现在节点 ${spots.join("、")}` : "没有对应节点";

  if (!team.units.length) {
    box.innerHTML = `
      <div class="head">
        <strong>梯队 ${team.id}</strong>
        <span class="hint">${esc(team.leader)} · ${esc(spotText)}</span>
      </div>
      <div class="empty">这是友军/后勤梯队，没有敌方单位属性。</div>`;
    return;
  }

  const rows = team.units.map((unit) => {
    const s = unit.stats;
    return `
      <tr>
        <td><div>${esc(unit.name)}</div><span class="u-code">${esc(unit.code)}</span></td>
        <td class="num">${unit.number}</td>
        <td class="num">${unit.level}</td>
        <td class="num">${fmtInt(s.hp)}</td>
        <td class="num">${s.pow}</td>
        <td class="num">${s.rate}</td>
        <td class="num">${s.hit}</td>
        <td class="num">${s.dodge}</td>
        <td class="num">${s.range}</td>
        <td class="num">${s.speed}</td>
        <td class="num">${s.armorPiercing}</td>
        <td class="num">${s.armor}</td>
        <td class="num">${s.tenacity}</td>
        <td class="num">${s.debuffResistance}</td>
        <td class="num">${s.shield}</td>
        <td class="num">${fmtInt(s.def)}</td>
        <td class="num">${unit.defPercent}%</td>
        <td class="mono">${unit.x},${unit.y}</td>
        <td class="num">${fmtInt(team.unitCe[unit.rowId])}</td>
      </tr>`;
  }).join("");

  box.innerHTML = `
    <div class="head">
      <strong>梯队 ${team.id}</strong>
      <span class="hint">${esc(team.leader)} · ${team.units.length} 个单位 · ${esc(spotText)}</span>
      <span class="hint">${team.fakeCe
        ? `效能 ${fmtInt(team.ce)}（游戏内展示值；公式值 600 → ${fmtInt(team.ce600)}，300 → ${fmtInt(team.ce300)}）`
        : `效能 ${fmtInt(team.ce)}`}</span>
    </div>
    <div class="table-wrap tall">
      <table>
        <thead>
          <tr>
            <th>单位</th><th class="num">扩编</th><th class="num">等级</th><th class="num">生命</th>
            <th class="num">火力</th><th class="num">射速</th><th class="num">命中</th><th class="num">回避</th>
            <th class="num">射程</th><th class="num">移速</th><th class="num">穿甲</th><th class="num">护甲</th>
            <th class="num">韧性</th><th class="num">减伤</th><th class="num">护盾</th><th class="num">防御</th>
            <th class="num">防御%</th><th>站位</th><th class="num">单兵效能</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

/* ------------------------------------------------------------------ 节点 */
function nodeNote(spot) {
  const notes = [];
  if (spot.activeCycle) {
    const match = String(spot.activeCycle).match(/^(\d+),(\d+)$/);
    notes.push(match ? `限时开放 ${match[1]}/${match[2]}` : `周期 ${spot.activeCycle}`);
  }
  if (spot.randomGet && spot.randomGet !== "0") notes.push(`随机点 ${spot.randomGet}`);
  if (spot.specialEft) notes.push("特殊效果");
  if (spot.hostage) notes.push(`人质 ${spot.hostage}`);
  return notes.join("；");
}

function renderNodeTable() {
  const data = STATE.data;
  if (!data) return;
  const teamById = new Map(data.teams.map((team) => [team.id, team]));
  const buildingById = new Map(data.buildings.map((item) => [item.spotId, item]));
  const rowBySpot = new Map(data.enemyRows.map((row) => [row.spotId, row]));

  const rows = data.spots.filter((spot) => {
    const row = rowBySpot.get(spot.id);
    const team = row ? teamById.get(row.teamId) : null;
    const building = buildingById.get(spot.id);
    return matchesFilter([spot.id, spot.typeLabel, spot.belongLabel, team && team.leader, building && building.name]
      .filter(Boolean).join(" "));
  });

  $("node-count").textContent = `${rows.length} / ${data.spots.length}`;

  if (!rows.length) {
    $("node-table").innerHTML = '<div class="empty">没有匹配的节点</div>';
    return;
  }

  const body = rows.map((spot) => {
    const row = rowBySpot.get(spot.id);
    const team = row ? teamById.get(row.teamId) : null;
    const building = buildingById.get(spot.id);
    let teamCell = "—";
    if (row) {
      const suffix = row.kind === "ally" ? "友军" : row.kind === "third" ? "第三方" : (team ? esc(team.leader) : "");
      teamCell = `<span class="mono">${row.teamId}</span> ${suffix}`;
    }
    return `
      <tr>
        <td class="mono">${spot.id}</td>
        <td>${spot.typeLabel}</td>
        <td><span class="belong ${BELONG_CLASS[spot.belong] || ""}">${spot.belongLabel}</span></td>
        <td class="mono">${spot.x}, ${spot.y}</td>
        <td class="num">${spot.route.length || "—"}</td>
        <td>${teamCell}</td>
        <td>${building ? esc(building.name) : "—"}</td>
        <td class="muted">${nodeNote(spot) || "—"}</td>
      </tr>`;
  }).join("");

  $("node-table").innerHTML = `
    <table>
      <thead>
        <tr>
          <th>编号</th><th>类型</th><th>归属</th><th>坐标</th><th class="num">连接</th>
          <th>梯队</th><th>建筑</th><th>备注</th>
        </tr>
      </thead>
      <tbody>${body}</tbody>
    </table>`;
}

/* ------------------------------------------------------------------ 建筑 / 传送 */
function renderBuildings(data) {
  $("building-count").textContent = String(data.buildings.length);
  if (!data.buildings.length) {
    $("building-table").innerHTML = '<div class="empty">这张地图没有建筑数据</div>';
    return;
  }

  const body = data.buildings.map((item) => `
    <tr>
      <td class="mono">${item.spotId}</td>
      <td class="mono">${item.id}</td>
      <td>${esc(item.name)}</td>
      <td class="mono">${dash(item.code)}</td>
      <td class="num">${dash(item.type)}</td>
      <td class="num">${fmtInt(item.defender)}</td>
      <td>${dash(item.destroy)}</td>
      <td class="mono">${dash(item.assistRange)}</td>
      <td class="muted">${dash(item.notes)}</td>
    </tr>`).join("");

  $("building-table").innerHTML = `
    <table>
      <thead>
        <tr>
          <th>节点</th><th>建筑ID</th><th>名称</th><th>代码</th>
          <th class="num">类型</th><th class="num">耐久</th><th>破坏方式</th><th>支援范围</th><th>备注</th>
        </tr>
      </thead>
      <tbody>${body}</tbody>
    </table>`;
}

function renderPortals(data) {
  $("portal-count").textContent = String(data.portals.length);
  if (!data.portals.length) {
    $("portal-table").innerHTML = '<div class="empty">这张地图没有 auto_teleport 传送点</div>';
    return;
  }

  const body = data.portals.map((item) => `
    <tr>
      <td class="mono">${item.from}</td>
      <td class="mono">${item.to}</td>
      <td>${item.buildingId ? `<span class="mono">${item.buildingId}</span>` : "—"}</td>
    </tr>`).join("");

  $("portal-table").innerHTML = `
    <table>
      <thead><tr><th>起点节点</th><th>终点节点</th><th>控制建筑</th></tr></thead>
      <tbody>${body}</tbody>
    </table>`;
}

boot();
