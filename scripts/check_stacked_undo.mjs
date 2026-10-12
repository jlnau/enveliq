// Browser check for stacked Undo bars: one bar for each Reviewed, Archive or Bin that is still waiting, the newest at the bottom,
// several emails done together are one bar, and a fourth makes the oldest go through. Uses the demo build (made-up mail, no server).
// Usage: node scripts/check_stacked_undo.mjs      Set SHOTS=<folder> to save screenshots.
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

for (const [name, vp] of [["desktop", { width: 1180, height: 760 }], ["phone", { width: 390, height: 780 }]]) {
  const p = await b.newPage({ viewport: vp }); const errors = [];
  p.on("pageerror", (e) => errors.push(String(e)));
  await p.goto(url); await p.waitForTimeout(600);
  await p.evaluate(() => {
    window.__undoMs = 60000;
    const base = data.find((x) => x.status === "inbox" && x.owner === currentUser.id);
    ["Electricity bill", "Dentist on Friday", "School form", "Parcel on its way", "Book club"].forEach((t, i) => data.push({ ...base, id: 9000 + i, subject: t }));
    render();
  });
  const queue = (status, count = 1) => p.evaluate(([st, n]) => { const ms = data.filter((x) => x.status === "inbox" && x.owner === currentUser.id && !x._pending).slice(0, n); queueAction(ms, st); }, [status, count]);
  const bars = () => p.locator("#undoBar .undobar");
  await queue("archived"); await queue("trashed"); await queue("reviewed");
  check(name + ": three actions in a row show three bars", (await bars().count()) === 3);
  check(name + ": the newest is at the bottom", /Marked reviewed/.test(await bars().last().innerText()) && /Archived/.test(await bars().first().innerText()));
  const boxes = await bars().evaluateAll((els) => els.map((e) => e.getBoundingClientRect()));
  check(name + ": the bars sit on top of each other without overlapping", boxes.every((r, i) => i === 0 || r.top >= boxes[i - 1].bottom - 0.5));
  check(name + ": the bars stay inside the screen", boxes.every((r) => r.left >= 0 && r.right <= vp.width && r.bottom <= vp.height));
  if (shots) await p.screenshot({ path: path.join(shots, `stacked-undo-${name}.png`) });
  const before = await p.locator("article.mail:not(.leaving)").count();
  await bars().nth(1).locator("button").click();
  check(name + ": Undo on the middle bar brings back only that email", (await bars().count()) === 2 && (await p.locator("article.mail:not(.leaving)").count()) === before + 1 && /Archived/.test(await bars().first().innerText()) && /Marked reviewed/.test(await bars().last().innerText()));
  await queue("trashed", 2);
  check(name + ": two emails done together are one bar", (await bars().count()) === 3 && /2 emails/.test(await bars().last().innerText()));
  await queue("archived");
  check(name + ": a fourth action makes the oldest go through, so three bars stay", (await bars().count()) === 3 && /Marked reviewed/.test(await bars().first().innerText()) && /2 emails/.test(await bars().nth(1).innerText()));
  check(name + ": no script errors", errors.length === 0);
  await p.close();
}
// Bars go away on their own, one by one
{
  const p = await b.newPage({ viewport: { width: 1180, height: 760 } });
  await p.goto(url); await p.waitForTimeout(600);
  await p.evaluate(() => { window.__undoMs = 1500; queueAction([data.find((x) => x.status === "inbox" && x.owner === currentUser.id)], "archived"); });
  await p.waitForTimeout(700);
  await p.evaluate(() => { queueAction([data.find((x) => x.status === "inbox" && x.owner === currentUser.id && !x._pending)], "trashed"); });
  check("two bars at first", (await p.locator("#undoBar .undobar").count()) === 2);
  await p.waitForTimeout(1200);
  check("the older bar goes first and the newer one stays", (await p.locator("#undoBar .undobar").count()) === 1 && /Moved to Bin/.test(await p.locator("#undoBar .undobar").innerText()));
  await p.waitForFunction(() => document.getElementById("undoBar").hidden, null, { timeout: 3000 });
  check("then none are left", true);
  await p.close();
}
await b.close(); srv.close();
process.exit(failed ? 1 : 0);
