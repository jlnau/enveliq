// Browser check for the paperclip under the date on emails that have an attachment. Uses the demo build (made-up mail, no server).
// Usage: node scripts/check_attachment_clip.mjs      Set SHOTS=<folder> to save screenshots.
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
    const base = data.find((x) => x.status === "inbox" && x.owner === currentUser.id);
    data.push({ ...base, id: 9001, subject: "No files here", attachments: [] });
    data.push({ ...base, id: 9002, subject: "Two files here", attachments: [base.attachments[0], base.attachments[0]] });
    document.querySelector(".demo-banner")?.remove(); render();
  });
  const row = (t) => p.locator("article.mail", { hasText: t });
  check(name + ": an email with an attachment has a paperclip", (await row("Your Skyline Air Travel Reminder").locator(".time .clip").count()) === 1);
  check(name + ": an email without one has none", (await row("No files here").locator(".clip").count()) === 0);
  check(name + ": the paperclip says so for a screen reader", (await row("Your Skyline Air Travel Reminder").locator(".clip").getAttribute("aria-label")) === "Has an attachment" && (await row("Two files here").locator(".clip").getAttribute("aria-label")) === "Has 2 attachments");
  const t = await row("Your Skyline Air Travel Reminder").locator(".time").evaluate((e) => { const c = e.querySelector(".clip").getBoundingClientRect(), r = e.getBoundingClientRect(), tx = document.createRange(); tx.selectNodeContents(e.firstChild); const d = tx.getBoundingClientRect(); return { below: c.top >= d.bottom - 1, inside: c.right <= r.right + 1 && c.left >= r.left - 1, right: Math.abs(c.right - d.right) < 3 }; });
  check(name + ": it sits under the date and time, lined up on the right", t.below && t.inside && t.right);
  check(name + ": no sideways scrolling", await p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
  if (shots) await p.screenshot({ path: path.join(shots, `clip-${name}.png`) });
  check(name + ": no script errors", errors.length === 0);
  await p.close();
}
await b.close(); srv.close();
process.exit(failed ? 1 : 0);
