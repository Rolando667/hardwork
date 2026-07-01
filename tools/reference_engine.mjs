// Reference-engine harness for parity testing.
//
// Extracts the calibrated strategy functions DIRECTLY from grid_bot_calculator.html
// (by name + brace matching, so we test against the real source rather than a
// hand-retyped copy) and runs them on inputs piped in as JSON on stdin. Used by
// tests/test_engine_parity.py to confirm the Python port matches the JS to a tiny
// tolerance.
//
// Usage:  node reference_engine.mjs <path-to-html>   < input.json   > output.json
//   input: {"cmd":"backtest","candles":[...],"s":0,"e":N,"p":{...}}
//          {"cmd":"path","args":[lastClose,lastTs,count,stepSec,vol,drift,seed,trend]}
//          {"cmd":"rng","seed":123,"n":20}
import fs from "node:fs";

const htmlPath = process.argv[2];
const html = fs.readFileSync(htmlPath, "utf8");

// The calibrated math lives in the single large inline <script>.
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
const code = scripts.sort((a, b) => b.length - a.length)[0];

function extractFn(name) {
  const re = new RegExp("function\\s+" + name + "\\s*\\(", "g");
  const m = re.exec(code);
  if (!m) throw new Error("function not found: " + name);
  const open = code.indexOf("{", m.index);
  let depth = 0;
  let j = open;
  for (; j < code.length; j++) {
    const ch = code[j];
    if (ch === "{") depth++;
    else if (ch === "}") {
      depth--;
      if (depth === 0) {
        j++;
        break;
      }
    }
  }
  return code.slice(m.index, j);
}

// Rebuild only the pure functions in an isolated scope, stubbing the two globals
// the backtest touches (clamp + state.symbol; state is display-only when
// recordTrades is false).
const harness = `
  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  const state={symbol:'SOLUSDT'};
  ${extractFn("buildLevels")}
  ${extractFn("mulberry32")}
  ${extractFn("gaussRand")}
  ${extractFn("genOnePath")}
  ${extractFn("backtest")}
  return { buildLevels, backtest, mulberry32, gaussRand, genOnePath };
`;
// eslint-disable-next-line no-new-func
const api = new Function(harness)();

function pick(r) {
  // Numeric fields we compare in the parity test.
  return {
    gridProfit: r.gridProfit,
    floating: r.floating,
    total: r.total,
    totalFees: r.totalFees,
    buyTrades: r.buyTrades,
    sellTrades: r.sellTrades,
    matched: r.matched,
    qtyPerOrder: r.qtyPerOrder,
    initialBuyQty: r.initialBuyQty,
    entryPrice: r.entryPrice,
    days: r.days,
    apr: r.apr,
    inRange: r.inRange,
    atrPct: r.atrPct,
    rangeCov: r.rangeCov,
    feeImpact: r.feeImpact,
    maxDD: r.maxDD,
    finalPrice: r.finalPrice,
    gridEff: r.gridEff,
    riskRatio: r.riskRatio,
    cashEnd: r.cashEnd,
    invQtyEnd: r.invQtyEnd,
    profitPerGridPct: r.profitPerGridPct,
  };
}

let raw = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (d) => (raw += d));
process.stdin.on("end", () => {
  const req = JSON.parse(raw);
  let out;
  if (req.cmd === "backtest") {
    out = pick(api.backtest(req.candles, req.s, req.e, req.p));
  } else if (req.cmd === "path") {
    out = api.genOnePath(...req.args);
  } else if (req.cmd === "rng") {
    const rnd = api.mulberry32(req.seed >>> 0);
    out = Array.from({ length: req.n }, () => rnd());
  } else {
    throw new Error("unknown cmd: " + req.cmd);
  }
  process.stdout.write(JSON.stringify(out));
});
