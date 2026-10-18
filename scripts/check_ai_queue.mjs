// Browser check for the AI queue bar at the bottom of the page. Uses the demo build (made-up mail, no server).
// Usage: node scripts/check_ai_queue.mjs      Set SHOTS=<folder> to save screenshots.
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
  // The queue is operational feedback, so it must remain visible in default Calm mode.
  await p.goto(url); await p.waitForTimeout(600);
  await p.evaluate(() => { document.querySelector(".demo-banner")?.remove(); });
  const bar = p.locator("#sumBar");
  check(name + ": default Calm mode is active", await p.evaluate(() => document.body.classList.contains("calm")));
  const paint = (q, live = 0) => p.evaluate(([q, live]) => { sq = { items: [], ...q }; aiLive = live; paintSumBar(); }, [q, live]);
  await paint({ waiting: 0, writing: 0, new_mail: 0 });
  check(name + ": the bar is hidden when nothing is queued", await bar.evaluate((e) => e.hidden));
  await paint({ waiting: 2, writing: 1, new_mail: 3 });
  const text = await bar.innerText();
  check(name + ": AI processing status stays visible in Calm mode", await bar.isVisible());
  check(name + ": it says what is being written and what is waiting", text.includes("AI queue") && text.includes("1 being written") && text.includes("2 waiting"));
  check(name + ": it says new emails appear when their summary and files are ready", text.includes("3 new emails appear in your inbox when its summary and files are ready."));
  if (shots) await p.screenshot({ path: path.join(shots, `ai-queue-${name}.png`) });
  const fit = await bar.evaluate((e) => { const r = e.getBoundingClientRect(); return r.left >= 0 && r.right <= window.innerWidth && r.bottom <= window.innerHeight; });
  check(name + ": the bar sits inside the page at the bottom", fit && (await bar.evaluate((e) => e.getBoundingClientRect().bottom > window.innerHeight - 140)));
  await paint({ waiting: 0, writing: 1, new_mail: 1 });
  check(name + ": one new email reads naturally", (await bar.innerText()).includes("1 new email appears in your inbox"));
  await paint({ waiting: 0, writing: 1, new_mail: 0 });
  check(name + ": work started by a button has no new-mail line", !(await bar.innerText()).includes("new email"));
  await paint({ waiting: 0, writing: 0, new_mail: 0 }, 1);
  check(name + ": an AI answer you are waiting for (Write help, Agent) shows in the bar", !(await bar.evaluate((e) => e.hidden)) && (await bar.innerText()).includes("an AI answer is on its way"));
  await paint({ waiting: 0, writing: 0, new_mail: 0 }, 0);
  check(name + ": and goes away when it arrives", await bar.evaluate((e) => e.hidden));
  const card = await p.evaluate(() => { sq = { items: [], waiting: 0, writing: 0, notice: { text: "No AI model is set up yet." } }; return genBlock({ id: 1, real: { accountId: "a", messageId: "m" } }); });
  check(name + ": an email with no summary offers a button and says why when it cannot be summarised", card.includes("data-gen=") && card.includes("No AI model is set up yet."));
  check(name + ": no sideways scrolling", await p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
  check(name + ": no script errors", errors.length === 0);
  await p.close();
}
await b.close(); srv.close();
process.exit(failed ? 1 : 0);
