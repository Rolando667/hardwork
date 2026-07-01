// Dashboard logic. The browser is UI only: it reads snapshots over a WebSocket
// (with a polling fallback) and POSTs control actions. It never sees API keys.
const $ = (id) => document.getElementById(id);
const fmt = (n, d = 2) => (n == null || isNaN(n)) ? "—" : Number(n).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
const sign = (n) => (n >= 0 ? "+" : "");
const cls = (n) => (n >= 0 ? "pos" : "neg");
const usd = (n) => (n == null || isNaN(n)) ? "—" : `${sign(n)}$${fmt(Math.abs(n))}`;

let CFG = null;

// Optional dashboard auth token (only needed if DASHBOARD_TOKEN is set server-side).
// Kept in sessionStorage, NOT localStorage, and never persisted to disk.
const getToken = () => sessionStorage.getItem("gb_token") || "";

async function api(path, opts = {}) {
  const tok = getToken();
  opts.headers = Object.assign({}, opts.headers, tok ? { "X-Auth-Token": tok } : {});
  let r = await fetch(path, opts);
  if (r.status === 401) {
    const t = prompt("Dashboard auth token required:");
    if (t) {
      sessionStorage.setItem("gb_token", t);
      opts.headers["X-Auth-Token"] = t;
      r = await fetch(path, opts);
    }
  }
  return r.json();
}

// ---- controls ----
$("btnStart").onclick = async () => { await api("/api/start", { method: "POST" }); refresh(); };
$("btnStop").onclick = async () => { await api("/api/stop", { method: "POST" }); refresh(); };
$("btnPanic").onclick = async () => {
  if (!confirm("PANIC: cancel ALL open orders and halt the bot. Continue?")) return;
  await api("/api/panic", { method: "POST" }); refresh();
};
$("btnResume").onclick = async () => { await api("/api/resume", { method: "POST" }); refresh(); };
$("btnSetup").onclick = () => $("setup").classList.toggle("open");

$("btnSave").onclick = async () => {
  const body = {};
  const f = (id) => $(id).value.trim();
  const num = (id) => f(id) === "" ? null : Number(f(id));
  body.exchange = f("f_exchange") || null;
  body.symbol = f("f_symbol") || null;
  body.mode = $("f_mode").value;
  if (f("f_api_key")) body.api_key = f("f_api_key");
  if (f("f_api_secret")) body.api_secret = f("f_api_secret");
  if (f("f_api_password")) body.api_password = f("f_api_password");
  body.invest = num("f_invest");
  body.grids = num("f_grids");
  body.grid_mode = $("f_grid_mode").value;
  body.lower = num("f_lower");
  body.upper = num("f_upper");
  body.fee_pct = num("f_fee_pct");
  body.slip_bps = num("f_slip_bps");
  body.max_capital = num("f_max_capital");
  body.max_daily_loss = num("f_max_daily_loss");
  body.cycle_seconds = num("f_cycle_seconds");
  body.allow_live = $("f_allow_live").value === "true";
  body.use_ai = $("f_use_ai").value === "true";
  body.ai_model = f("f_ai_model") || null;
  if (f("f_anthropic_api_key")) body.anthropic_api_key = f("f_anthropic_api_key");
  Object.keys(body).forEach((k) => body[k] == null && delete body[k]);

  $("saveToast").textContent = "saving…";
  const res = await api("/api/config/keys", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  if (res.error) { $("saveToast").innerHTML = `<span class="neg">${res.error}</span>`; }
  else {
    $("saveToast").innerHTML = `<span class="pos">saved (${(res.changed || []).join(", ") || "no changes"})</span>`;
    ["f_api_key", "f_api_secret", "f_api_password", "f_anthropic_api_key"].forEach((id) => ($(id).value = ""));
    loadConfig(); refresh();
  }
};

// ---- rendering ----
function render(s) {
  if (!s) return;
  $("price").textContent = s.price == null ? "—" : fmt(s.price, 4);
  $("symbol").textContent = s.symbol || "—";
  const badge = $("modeBadge");
  badge.textContent = s.mode; badge.className = "badge " + (s.mode || "dry");

  const dot = $("statusDot"), txt = $("statusText");
  if (s.halted) { dot.className = "dot halt"; txt.textContent = "halted"; }
  else if (s.running) { dot.className = "dot on"; txt.textContent = "running"; }
  else { dot.className = "dot off"; txt.textContent = "stopped"; }
  $("resumeRow").style.display = s.halted ? "block" : "none";

  $("cycleTag").textContent = s.cycle ? `cycle ${s.cycle}` : "";

  // decision
  const d = s.last_decision;
  const dEl = $("decision");
  if (d) {
    dEl.className = "decision " + (d.action || "hold");
    $("decAct").textContent = d.action.replace("_", " ");
    $("decWhy").textContent = d.reason || "";
    $("decTrigs").innerHTML = (d.triggers || []).map((t) => `<span class="trig">${t}</span>`).join("");
    if (d.walk_forward) {
      const wf = d.walk_forward;
      const cl = wf.overfit ? "bad" : "ok";
      $("decWf").innerHTML = wf.wf
        ? `walk-forward — IS APR ${fmt(wf.is_apr, 0)}% · OOS APR ${wf.oos_apr == null ? "—" : fmt(wf.oos_apr, 0) + "%"} · <span class="${cl}">${wf.overfit ? "OVERFIT (rejected)" : "validated"}</span>`
        : `walk-forward: insufficient history to validate`;
    } else $("decWf").textContent = "";
  }

  // metrics
  const m = s.metrics || {};
  $("mAtr").textContent = m.atr_pct == null ? "—" : fmt(m.atr_pct, 3) + "%";
  $("mInrange").textContent = m.in_range_pct == null ? "—" : fmt(m.in_range_pct, 1) + "%";
  $("mFill").textContent = m.fill_rate_per_day == null ? "—" : fmt(m.fill_rate_per_day, 1);
  $("mVol").textContent = m.realized_vol_daily == null ? "—" : fmt(m.realized_vol_daily * 100, 2) + "%/d";
  $("mEff").textContent = m.grid_eff == null ? "—" : fmt(m.grid_eff, 1) + "%";
  $("mCov").textContent = m.range_cov == null ? "—" : fmt(m.range_cov, 0) + "%";

  // grid ladder
  const g = s.active_grid;
  if (g) {
    $("gridRange").textContent = `${fmt(g.config.lower, 4)} – ${fmt(g.config.upper, 4)} · ${g.config.grids} × ${g.config.mode} · epoch ${g.epoch}`;
    const price = s.price;
    const lv = (g.levels || []).slice().reverse();
    $("ladder").innerHTML = lv.map((p) => {
      const side = p >= price ? "sell" : "buy";
      const here = price != null && Math.abs(p - price) < ((g.config.upper - g.config.lower) / g.config.grids / 2);
      return `<div class="lvl ${side} ${here ? "price-here" : ""}"><span class="side">${side === "sell" ? "S" : "B"}</span><span>${fmt(p, 4)}</span><span class="qty">${here ? "← price" : ""}</span></div>`;
    }).join("");
  } else {
    $("gridRange").textContent = "";
    $("ladder").innerHTML = `<div class="muted" style="padding:12px">No grid deployed yet.</div>`;
  }

  // orders
  const o = s.open_orders || [];
  $("orderCount").textContent = `${o.length}`;
  $("orders").innerHTML = o.length
    ? o.map((x) => `<div class="order"><span class="s ${x.side}">${x.side.toUpperCase()}</span><span>${fmt(x.price, 4)}</span><span class="qty mono">${fmt(x.amount, 4)}</span></div>`).join("")
    : `<div class="muted">none</div>`;

  // pnl
  const p = s.pnl || {};
  $("pRealized").innerHTML = `<span class="${cls(p.realized || 0)}">${usd(p.realized)}</span>`;
  $("pFloating").innerHTML = `<span class="${cls(p.floating || 0)}">${usd(p.floating)}</span>`;
  $("pTotal").innerHTML = `<span class="${cls(p.total || 0)}">${usd(p.total)}</span>`;
  $("pInv").textContent = p.inventory_qty == null ? "—" : `${fmt(p.inventory_qty, 4)} @ cost ${usd(p.inventory_cost)}`;

  // monte carlo
  const mc = s.monte_carlo;
  if (mc) {
    $("mcMeta").textContent = `${mc.n} paths · ${fmt(mc.horizon_days, 0)}d`;
    $("mcP5").innerHTML = `<span class="${cls(mc.p5)}">${usd(mc.p5)}</span>`;
    $("mcP50").innerHTML = `<span class="${cls(mc.p50)}">${usd(mc.p50)}</span>`;
    $("mcP95").innerHTML = `<span class="${cls(mc.p95)}">${usd(mc.p95)}</span>`;
    $("mcWin").innerHTML = `<span class="${mc.win_rate >= 50 ? "pos" : "neg"}">${fmt(mc.win_rate, 0)}%</span>`;
  }

  // safety
  const sd = s.daily || {};
  $("sIntraday").innerHTML = `<span class="${cls(sd.intraday_pnl || 0)}">${usd(sd.intraday_pnl)}</span>`;
  $("sRepo").textContent = `${sd.repositions_today ?? 0} / ${sd.max_repositions ?? 0}`;
  $("sLoss").textContent = `-$${fmt(sd.max_daily_loss)}`;
  $("sHalt").innerHTML = s.halted ? `<span class="neg">ON — ${s.halt_reason || ""}</span>` : `<span class="muted">off</span>`;

  if (s.last_error) { $("saveToast").innerHTML = ""; }
}

async function refresh() {
  try { render(await api("/api/status")); } catch (e) {}
  loadLog();
}

async function loadLog() {
  try {
    const r = await api("/api/log?limit=120");
    $("logBody").innerHTML = (r.actions || []).map((a) => {
      const t = new Date(a.ts * 1000).toLocaleTimeString();
      return `<tr><td class="mono muted">${t}</td><td><span class="tag ${a.kind}">${a.kind}</span></td><td class="mono">${a.action}</td><td>${(a.reason || "").replace(/</g, "&lt;")}</td></tr>`;
    }).join("");
  } catch (e) {}
}

async function loadConfig() {
  try {
    CFG = await api("/api/config");
    const set = (id, v) => { if ($(id) && v != null) $(id).value = v; };
    set("f_exchange", CFG.exchange); set("f_symbol", CFG.symbol);
    $("f_mode").value = CFG.mode;
    set("f_invest", CFG.invest); set("f_grids", CFG.grids);
    $("f_grid_mode").value = CFG.grid_mode;
    set("f_lower", CFG.lower); set("f_upper", CFG.upper);
    set("f_fee_pct", CFG.fee_pct); set("f_slip_bps", CFG.slip_bps);
    set("f_max_capital", CFG.max_capital); set("f_max_daily_loss", CFG.max_daily_loss);
    set("f_cycle_seconds", CFG.cycle_seconds); set("f_ai_model", CFG.ai_model || "claude-haiku-4-5");
    $("f_allow_live").value = String(CFG.allow_live);
    $("f_use_ai").value = String(CFG.use_ai);
    $("setupCfgState").textContent = CFG.has_keys ? "· keys: set" : "· keys: none";
  } catch (e) {}
}

// ---- websocket with polling fallback ----
function connectWS() {
  try {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onmessage = (ev) => { try { render(JSON.parse(ev.data)); } catch (e) {} };
    ws.onclose = () => setTimeout(connectWS, 3000);
    ws.onerror = () => { try { ws.close(); } catch (e) {} };
  } catch (e) { setTimeout(connectWS, 3000); }
}

loadConfig();
refresh();
connectWS();
setInterval(refresh, 5000);   // poll fallback + log refresh
