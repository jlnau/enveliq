// Browser check for Calm mode (no numbers, softer colours, one task at a time). Uses the demo build (made-up mail, no server).
// Usage: node scripts/check_calm_mode.mjs      Set SHOTS=<folder> to save screenshots.
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
const url = `http://127.0.0.1:${srv.address().port}/`;
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
const b = await chromium.launch();
const shots = process.env.SHOTS; if (shots) fs.mkdirSync(shots, { recursive: true });

for (const [name, vp] of [["desktop", { width: 1180, height: 820 }], ["phone", { width: 390, height: 800 }]]) {
  const ctx = await b.newContext({ viewport: vp }); const p = await ctx.newPage(); const errors = [];
  p.on("pageerror", (e) => errors.push(String(e)));
  await p.goto(url); await p.waitForTimeout(600);
  await p.evaluate(() => document.querySelector(".demo-banner")?.remove());
  if (name === "phone") await p.click("#menuBtn");
  const sw = p.locator("#calmBtn");
  check(name + ": the Calm mode switch is just above Agent, in the footer of the menu", await p.evaluate(() => { const a = document.getElementById("agentBtn"), c = document.getElementById("calmBtn"); return !!c && c.nextElementSibling === a && a.parentElement.classList.contains("side-foot"); }));
  check(name + ": Calm mode starts enabled and announces its state", (await sw.getAttribute("role")) === "switch" && (await sw.getAttribute("aria-checked")) === "true");
  const calmState = () => p.evaluate(() => ({
    badges: [...document.querySelectorAll(".badge")].filter((e) => e.getClientRects().length && getComputedStyle(e).display !== "none").length,
    today: document.querySelector(".today-card .thead b")?.textContent || "",
    sub: [...document.getElementById("inboxSubtitle").childNodes].filter((n) => !(n.classList && n.classList.contains("sdate"))).map((n) => n.textContent).join(""),
    more: document.querySelector(".tmore")?.textContent || "",
    rows: document.querySelectorAll(".today-card .trow2").length,
    important: document.querySelectorAll(".preview-important .trow2").length,
    dueCount: typeof openTasks === "function" ? openTasks().filter(t => t.days <= 0).length : 0,
    laterCount: typeof openTasks === "function" ? openTasks().filter(t => t.days > 0).length : 0,
    overdueCount: typeof openTasks === "function" ? openTasks().filter(t => t.days < 0).length : 0,
    when: [...document.querySelectorAll(".twhen")].map((e) => e.textContent).join("|"),
    bar: getComputedStyle(document.getElementById("sumBar")).display
  }));
  const on = await calmState();
  check(name + ": Calm mode hides counters", on.badges === 0 && !/\d/.test(on.today) && !/\d/.test(on.sub) && !/\d/.test(on.more) && on.bar === "none");
  check(name + ": Calm mode shows one Start here task and a Later section when needed", on.today === "Start here" && on.rows === 1 && (on.laterCount > 0 ? /Later/.test(on.more) : !/Later/.test(on.more)));
  check(name + ": every due task remains visible in Calm mode", on.dueCount >= 1 && on.rows + on.important === on.dueCount);
  check(name + ": overdue task dates remain visible", on.overdueCount === 0 || /Waiting since/.test(on.when));
  if (shots) await p.screenshot({ path: path.join(shots, "calm-" + name + ".png") });

  await sw.click(); await p.waitForTimeout(300);
  check(name + ": switching Calm mode off announces the change", (await sw.getAttribute("aria-checked")) === "false");
  const off = await calmState();
  check(name + ": switching off restores counters", off.badges > 0 && /\d/.test(off.today) && /\d/.test(off.sub));
  await p.reload(); await p.waitForTimeout(800);
  check(name + ": explicit opt out is remembered after reload", await p.evaluate(() => !document.body.classList.contains("calm")));
  await p.evaluate(() => document.querySelector(".demo-banner")?.remove());
  if (name === "phone") await p.click("#menuBtn");
  await p.click("#calmBtn"); await p.waitForTimeout(300);
  check(name + ": Calm mode can be enabled again", (await p.locator("#calmBtn").getAttribute("aria-checked")) === "true" && (await calmState()).badges === 0);
  await p.reload(); await p.waitForTimeout(800);
  check(name + ": choosing Calm mode on is remembered after reload", await p.evaluate(() => document.body.classList.contains("calm")));
  check(name + ": no sideways scrolling", await p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
  check(name + ": no script errors", errors.length === 0);
  await ctx.close();
}
await b.close(); srv.close();
if (failed) process.exit(1);
console.log("All checks passed");
