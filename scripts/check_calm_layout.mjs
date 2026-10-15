// Browser check for the compact Calm layout: the Start here card is short with small buttons, it fills the full width when it is
// the only panel, and "Also important today" becomes a slim strip along the bottom of the card. Desktop only; phones keep their layout.
// Uses the demo build (made-up mail, no server).
// Usage: node scripts/check_calm_layout.mjs      Set SHOTS=<folder> to save screenshots.
import { chromium } from "playwright";
import http from "node:http"; import fs from "node:fs"; import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
execFileSync("node", ["demo/build.mjs"], { cwd: root, stdio: "ignore" });
const dist = path.join(root, "demo", "dist");
const headers = Object.fromEntries(fs.readFileSync(path.join(dist, "_headers"), "utf8").split("\n").slice(1).filter((l) => l.includes(":")).map((l) => { const i = l.indexOf(":"); return [l.slice(0, i).trim().toLowerCase(), l.slice(i + 1).trim()]; }));
const types = { ".html": "text/html; charset=utf-8", ".webp": "image/webp", ".png": "image/png" };
const srv = http.createServer((q, r) => {
  const p = q.url.split("?")[0], f = path.join(dist, p === "/" ? "index.html" : p.replace(/^\/+/, ""));
  if (!f.startsWith(dist + path.sep) || f.endsWith("_headers") || !fs.existsSync(f)) { r.statusCode = 404; return r.end("not found"); }
  for (const [k, v] of Object.entries(headers)) r.setHeader(k, v);
  r.setHeader("content-type", types[path.extname(f)] || "application/octet-stream"); r.end(fs.readFileSync(f));
}).listen(0);
const origin = `http://127.0.0.1:${srv.address().port}`;
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
const b = await chromium.launch();
const shots = process.env.SHOTS; if (shots) fs.mkdirSync(shots, { recursive: true });


const open = async (vp, dueToday, theme) => {
  const ctx = await b.newContext({ viewport: vp, deviceScaleFactor: 1 });
  await ctx.addInitScript((t) => { try { localStorage.setItem("enveliq-calm", "1"); localStorage.setItem("enveliq-welcome-seen", "1"); localStorage.setItem("enveliq-theme", t); } catch {} }, theme);
  const p = await ctx.newPage(); p.errors = []; p.on("pageerror", (e) => p.errors.push(String(e)));
  await p.goto(origin + "/"); await p.waitForTimeout(1200);
  await p.evaluate((n) => { demoTasks.length = 0; for (const m of data) m.task = null;
    for (let i = 0; i < n; i++) demoTasks.push({ id: "t" + i, demoId: null, owner: currentUser.id, title: "Made-up task " + i, detail: "Example detail", sender: "Example Sender", priority: "normal", due: isoLocal(new Date()), remind_at: null, state: "open", reason: null, closed_at: null, account_id: "", message_id: "", received: 0 });
    syncDemoTasks(); view.layout = "list"; view.rows = "open"; applyView(); render(); }, dueToday);
  await p.waitForTimeout(300);
  return p;
};
const box = (p, sel) => p.evaluate((s) => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height, b: r.bottom }; }, sel);
for (const theme of ["dark", "light"]) {
  const alone = await open({ width: 1600, height: 900 }, 1, theme);
  const g = await box(alone, ".preview-today-grid"), c = await box(alone, ".preview-today-grid > .today-card");
  check(theme + ": alone, Start here fills the full width", !!c && !!g && c.w >= g.w - 2 && (await alone.locator(".preview-important").count()) === 0);
  const f = await box(alone, ".preview-focus-card");
  check(theme + ": Start here is compact (the card is under 240px tall)", !!c && c.h < 240 && !!f && f.h < 190);
  check(theme + ": the heading sits close to the top of the card", await alone.evaluate(() => { const h = document.querySelector(".today-card .thead b").getBoundingClientRect(), c = document.querySelector(".today-card").getBoundingClientRect(); return h.top - c.top < 24; }));
  check(theme + ": Open email, Snooze and Mark done are small", await alone.evaluate(() => { const bs = [...document.querySelectorAll(".preview-focus-actions button")]; return bs.length >= 2 && bs.every((e) => e.getBoundingClientRect().height <= 34 && parseFloat(getComputedStyle(e).fontSize) <= 13.5); }));
  if (shots) await alone.screenshot({ path: path.join(shots, "calm-alone-" + theme + ".png") });
  check(theme + ": no page errors (alone)", alone.errors.length === 0);
  await alone.context().close();
  const both = await open({ width: 1600, height: 900 }, 2, theme);
  const c2 = await box(both, ".preview-today-grid > .today-card"), s2 = await box(both, ".preview-important");
  check(theme + ": with two, the important panel is a strip under the card", !!c2 && !!s2 && Math.abs(s2.y - c2.b) <= 2 && s2.w >= c2.w - 2 && s2.h < 90);
  check(theme + ": the strip is not shown beside the card", !!s2 && s2.x <= c2.x + 2);
  if (shots) await both.screenshot({ path: path.join(shots, "calm-both-" + theme + ".png") });
  check(theme + ": no page errors (both)", both.errors.length === 0);
  await both.context().close();
}
const ph = await open({ width: 390, height: 800 }, 2, "dark");
await ph.click("#menuBtn").catch(() => {});
const pb = await ph.evaluate(() => { const r = (s) => { const e = document.querySelector(s); return e ? getComputedStyle(e).display : ""; }; return { grid: getComputedStyle(document.querySelector(".preview-today-grid")).gridTemplateColumns.split(" ").length, imp: r(".preview-important") }; });
check("phone: the Calm panels keep their one-column layout", pb.grid === 1);
await b.close(); srv.close();
if (failed) process.exit(1);
console.log("Calm layout check passed.");
