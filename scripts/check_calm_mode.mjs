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
  check(name + ": it starts off, and says so to screen readers", (await sw.getAttribute("role")) === "switch" && (await sw.getAttribute("aria-checked")) === "false");
  const before = await p.evaluate(() => ({ badges: [...document.querySelectorAll(".badge")].filter((e) => e.offsetParent).length, today: document.querySelector(".today-card .thead b")?.textContent || "", sub: [...document.getElementById("inboxSubtitle").childNodes].filter((n) => !(n.classList && n.classList.contains("sdate"))).map((n) => n.textContent).join("") }));
  check(name + ": off, the page shows its numbers", before.badges > 0 && /\d/.test(before.today) && /\d/.test(before.sub));
  await sw.click(); await p.waitForTimeout(300);
  check(name + ": on, the switch says so", (await sw.getAttribute("aria-checked")) === "true");
  const after = await p.evaluate(() => ({ badges: [...document.querySelectorAll(".badge")].filter((e) => e.offsetParent).length, today: document.querySelector(".today-card .thead b")?.textContent || "", sub: [...document.getElementById("inboxSubtitle").childNodes].filter((n) => !(n.classList && n.classList.contains("sdate"))).map((n) => n.textContent).join(""), more: document.querySelector(".tmore")?.textContent || "", rows: document.querySelectorAll(".today-card .trow2").length, when: [...document.querySelectorAll(".twhen")].map((e) => e.textContent).join("|"), bar: getComputedStyle(document.getElementById("sumBar")).display }));
  check(name + ": on, no counts are shown anywhere (menu, greeting, Today card, queue bar)", after.badges === 0 && !/\d/.test(after.today) && !/\d/.test(after.sub) && !/\d/.test(after.more) && after.bar === "none");
  check(name + ": on, the Today card shows one task, headed Start here, with the rest under Later", after.today === "Start here" && after.rows === 1 && /Later/.test(after.more));
  check(name + ": on, nothing says Waiting since", !/Waiting since/.test(after.when));
  await p.reload(); await p.waitForTimeout(800);
  check(name + ": it is remembered after a reload", await p.evaluate(() => document.body.classList.contains("calm")));
  await p.evaluate(() => document.querySelector(".demo-banner")?.remove());
  if (shots) await p.screenshot({ path: path.join(shots, "calm-" + name + ".png") });
  if (name === "phone") await p.click("#menuBtn");
  await p.click("#calmBtn"); await p.waitForTimeout(300);
  check(name + ": off again brings the numbers back", await p.evaluate(() => [...document.querySelectorAll(".badge")].some((e) => e.offsetParent)));
  check(name + ": no sideways scrolling", await p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
  check(name + ": no script errors", errors.length === 0);
  await ctx.close();
}
await b.close(); srv.close();
if (failed) process.exit(1);
console.log("All checks passed");
