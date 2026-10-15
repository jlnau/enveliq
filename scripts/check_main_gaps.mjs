// Browser check for the main screen on a computer: the boxes (count tiles, Today, Coming up, the delivery / subscription / trip / reply / message
// cards and the Recent emails bar) are all separated by the same small gap, so no space is taken up by nothing.
// Uses the demo build (made-up mail, no server).
// Usage: node scripts/check_main_gaps.mjs      Set SHOTS=<folder> to save screenshots.
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
const GAP = 12;
for (const calm of ["0", "1"]) for (const theme of ["dark", "light"]) {
  const ctx = await b.newContext({ viewport: { width: 1400, height: 1000 }, deviceScaleFactor: 1 });
  await ctx.addInitScript(([c, t]) => { try { localStorage.setItem("enveliq-calm", c); localStorage.setItem("enveliq-welcome-seen", "1"); localStorage.setItem("enveliq-theme", t); } catch {} }, [calm, theme]);
  const page = await ctx.newPage(); await page.goto(origin + "/"); await page.waitForSelector("article.mail"); await page.waitForTimeout(700);
  await page.evaluate(() => {
    view.layout = "list"; view.rows = "open"; applyView(); render();
    tasksData.tasks = [{ id: "a", title: "Download and install new configurations", detail: "", sender: "Ultra.cc", state: "open", days: 0, due: "2026-10-14" }, { id: "b", title: "Second thing", detail: "", sender: "X", state: "open", days: 3, due: "2026-10-17" }, { id: "c", title: "Third thing", detail: "", sender: "Y", state: "open", days: 5, due: "2026-10-19" }];
    renderToday();
  });
  for (const more of [false, true]) {
    if (more) await page.evaluate(() => { const cls = { shipBars: "shipcard", subBars: "subcard", tripBars: "tripcard", waitBars: "waitcard", msgBars: "msgcard" }; for (const id in cls) { const el = document.getElementById(id); el.hidden = false; el.innerHTML = `<div class="${cls[id]}" style="min-height:60px">test</div>`; } });
    await page.waitForTimeout(150);
    const rows = await page.evaluate(() => {
      const out = []; const add = (name, el) => { if (!el) return; const r = el.getBoundingClientRect(); if (r.height > 0) out.push([name, Math.round(r.top), Math.round(r.bottom)]); };
      add("count tiles", document.querySelector("#previewOverview"));
      for (const id of ["dueBars", "shipBars", "subBars", "tripBars", "waitBars", "msgBars"]) { const el = document.getElementById(id); if (el && !el.hidden) [...el.children].forEach((c) => add(id + " " + (c.className || c.tagName).toString().split(" ")[0], c)); }
      add("Recent emails bar", document.querySelector("#previewListHeading")); add("first email", document.querySelector("article.mail"));
      return out;
    });
    const label = `calm ${calm === "1" ? "on" : "off"}, ${theme}, ${more ? "with extra cards" : "Today and Coming up"}`;
    check(`${label}: ${rows.length - 1} gaps all ${GAP}px (${rows.slice(1).map((r, i) => r[1] - rows[i][2]).join(", ")})`, rows.length >= 3 && rows.slice(1).every((r, i) => Math.abs(r[1] - rows[i][2] - GAP) <= 1));
    if (shots) await page.screenshot({ path: path.join(shots, `gaps-calm${calm}-${theme}-${more ? "more" : "base"}.png`) });
  }
  await ctx.close();
}
await b.close(); srv.close();
if (failed) process.exit(1);
console.log("Main-screen gaps check passed.");
