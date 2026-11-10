// Browser check for the "Reading pane on the right" layout on a computer: the open email fills the right side from just under the top bar to the
// bottom of the window, and the title, the four counts, Today / Coming up and the list sit in a column on the left. The page itself does not scroll.
// On a phone and in every other layout nothing changes. Uses the demo build (made-up mail, no server).
// Usage: node scripts/check_split_reading.mjs      Set SHOTS=<folder> to save screenshots.
import { chromium } from "playwright";
import http from "node:http"; import fs from "node:fs"; import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
execFileSync("node", ["demo/build.mjs"], { cwd: root, stdio: "ignore" });
const dist = path.join(root, "demo", "dist");
const headers = Object.fromEntries(fs.readFileSync(path.join(dist, "_headers"), "utf8").split("\n").slice(1).filter((l) => l.includes(":")).map((l) => { const i = l.indexOf(":"); return [l.slice(0, i).trim(), l.slice(i + 1).trim()]; }));
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
const open = async (w, h, theme, layout, calm = "0") => {
  const ctx = await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
  await ctx.addInitScript(([t, l, c]) => { try { localStorage.setItem("enveliq-welcome-seen", "1"); localStorage.setItem("enveliq-theme", t); localStorage.setItem("enveliq-calm", c); localStorage.setItem("enveliq-view", JSON.stringify({ layout: l, density: "standard", width: "centered", rows: "collapsed", peek: true })); } catch {} }, [theme, layout, calm]);
  const page = await ctx.newPage(); const errs = []; page.on("pageerror", (e) => errs.push(e.message));
  await page.goto(origin + "/"); await page.waitForSelector("article.mail"); await page.waitForTimeout(700);
  return { page, errs };
};
const box = (page, sel) => page.evaluate((s) => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height, b: r.bottom, r: r.right }; }, sel);

for (const theme of ["dark", "light"]) {
  const { page, errs } = await open(1400, 900, theme, "right");
  await page.evaluate(() => {
    tasksData.tasks = [{ id: "a", title: "Download and install new configurations", detail: "", sender: "Ultra.cc", state: "open", days: 0, due: "2026-10-14" }, { id: "a2", title: "Renew the domain", detail: "", sender: "Z", state: "open", days: 0, due: "2026-10-14" }, { id: "a3", title: "A third thing today", detail: "", sender: "Z", state: "open", days: 0, due: "2026-10-14" }, { id: "b", title: "Second thing", detail: "", sender: "X", state: "open", days: 3, due: "2026-10-17" }, { id: "c", title: "Third thing", detail: "", sender: "Y", state: "open", days: 5, due: "2026-10-19" }, { id: "d", title: "Fourth thing", detail: "", sender: "Y", state: "open", days: 6, due: "2026-10-20" }];
    dueOpen = false; renderToday();
  });
  await page.waitForTimeout(200);
  const t = `(${theme}) `;
  check(t + "the split layout is on", await page.evaluate(() => document.body.classList.contains("split-read")));
  const bar = await box(page, "#previewToolbar"), dock = await box(page, "#readDock"), list = await box(page, "#paneList"), reading = await box(page, "#readDock .reading");
  check(t + "the open email starts right under the top bar", Math.abs(dock.y - bar.b) <= 3);
  check(t + "the open email runs down to the bottom of the window", dock.b >= 900 - 30 && dock.b <= 900);
  check(t + "the list is on the left and the email on the right", list.r <= reading.x + 2);
  check(t + "the email panel is much taller than the list pane used to be", reading.h > 600);
  const tiles = await page.evaluate(() => [...document.querySelectorAll("#previewOverview .preview-stat")].map((e) => { const r = e.getBoundingClientRect(); return [Math.round(r.y), Math.round(r.height)]; }));
  check(t + "the four counts sit in one slim row", tiles.length === 4 && tiles.every((x) => x[0] === tiles[0][0]) && tiles[0][1] <= 60);
  const today = await box(page, "#dueBars .today-card"), later = await box(page, "#dueBars .preview-later");
  check(t + "Today and Coming up sit side by side", today && later && Math.abs(today.y - later.y) <= 2 && later.x >= today.r);
  const vis = (sel) => page.evaluate((q) => [...document.querySelectorAll(q)].filter((e) => e.getBoundingClientRect().height > 0).length, sel);
  check(t + "Today shows at most two things", (await vis("#dueBars .today-card .trow2")) === 2);
  check(t + "Coming up shows the soonest two things", (await vis("#dueBars .preview-later .trow2")) === 2);
  check(t + "there are no circles in the Today and Coming up boxes", (await vis("#dueBars .tick")) === 0);
  const t2 = await box(page, "#dueBars .today-card"), l2 = await box(page, "#dueBars .preview-later");
  const shade = await page.evaluate(() => { const g = (s) => getComputedStyle(document.querySelector(s)).backgroundColor; return [g("#dueBars .today-card"), g("#dueBars .preview-later")]; });
  check(t + "the Coming up box is the same shade as the Today box", shade[0] === shade[1]);
  check(t + "Coming up has no arrow to fold it", (await page.locator("#dueBars .preview-later .preview-fold-toggle").evaluate((e) => getComputedStyle(e).display)) === "none");
  check(t + "the Coming up box is the same height as the Today box", Math.abs(t2.h - l2.h) <= 2);
  check(t + `the first email in the list starts high up (at ${Math.round(list.y)}, it did not move down)`, list.y < 640);
  check(t + "no email is selected on first opening", (await page.locator("#readDock .enveliq-empty-actions .enveliq-empty-action").count()) === 4 && await page.locator("#paneList article.current").count() === 0);
  check(t + "unopened emails have blue glow", await page.locator("#paneList article.mail.enveliq-new").count() > 0);
  await page.locator("#paneList article.mail .qmain").first().click();
  check(t + "opening email clears its glow", await page.locator("#paneList article.mail").first().evaluate(e => !e.classList.contains("enveliq-new")));
  const btn = await box(page, "#readDock .reading .qbtns .reviewed");
  check(t + "selecting an email shows Reviewed, Archive and Bin at the bottom", btn && btn.b <= dock.b && btn.b >= dock.b - 80);
  await page.reload(); await page.waitForSelector("#paneList article.mail");
  check(t + "refresh returns the reading pane to blank", (await page.locator("#readDock .enveliq-empty-actions .enveliq-empty-action").count()) === 4 && await page.locator("#paneList article.current").count() === 0);
  check(t + "demo resets temporary opened state after refresh", await page.locator("#paneList article.mail.enveliq-new").count() > 0);
  // Demo tasks are in memory, so a reload removes the temporary Coming up rows.
  // Restore them before the remaining layout/navigation checks.
  await page.evaluate(() => {
    tasksData.tasks = [{ id: "a", title: "Download and install new configurations", detail: "", sender: "Ultra.cc", state: "open", days: 0, due: "2026-10-14" }, { id: "a2", title: "Renew the domain", detail: "", sender: "Z", state: "open", days: 0, due: "2026-10-14" }, { id: "a3", title: "A third thing today", detail: "", sender: "Z", state: "open", days: 0, due: "2026-10-14" }, { id: "b", title: "Second thing", detail: "", sender: "X", state: "open", days: 3, due: "2026-10-17" }, { id: "c", title: "Third thing", detail: "", sender: "Y", state: "open", days: 5, due: "2026-10-19" }, { id: "d", title: "Fourth thing", detail: "", sender: "Y", state: "open", days: 6, due: "2026-10-20" }];
    dueOpen = false; renderToday();
  });
  if (theme === "dark") {
    await page.locator("#dueBars .preview-later .tmore").click(); await page.waitForTimeout(250);
    check("clicking Coming up goes to the Tasks page, it does not fold", await page.evaluate(() => document.body.classList.contains("on-tasks")));
    await page.locator('[data-filter="all"]').first().click(); await page.waitForTimeout(250);
  }
  await page.mouse.move(300, 600); await page.mouse.wheel(0, 900); await page.waitForTimeout(150);
  check(t + "the page itself does not scroll", (await page.evaluate(() => window.scrollY)) === 0);
  check(t + "no script errors", errs.length === 0);
  if (shots) await page.screenshot({ path: path.join(shots, `split-${theme}.png`) });
  if (theme === "dark") {
    const second = (await page.locator("#paneList article.mail .subject").nth(1).innerText()).trim();
    await page.locator("#paneList article.mail .qmain").nth(1).click(); await page.waitForTimeout(200);
    check("clicking another email shows it in the panel on the right", (await page.locator("#readDock .rhead h3").innerText()).trim() === second);
    check("the email panel is not left over on the Tasks page", await (async () => { await page.locator('[data-filter="tasks"]').first().click(); await page.waitForTimeout(250); return (await page.evaluate(() => document.body.classList.contains("split-read"))) === false && (await page.locator("#readDock .reading").count()) === 0; })());
  }
  await page.context().close();
}
for (const theme of ["dark", "light"]) {
  const { page, errs } = await open(1400, 900, theme, "right", "1");
  await page.evaluate(() => {
    tasksData.tasks = [{ id: "a", title: "Download and install new configurations", detail: "Log in, download and import the new settings on each device you use.", sender: "Ultra.cc", state: "open", days: 0, due: "2026-10-14" }, { id: "a2", title: "Renew the domain", detail: "", sender: "Z", state: "open", days: 0, due: "2026-10-14" }, { id: "b", title: "Second thing", detail: "", sender: "X", state: "open", days: 3, due: "2026-10-17" }];
    renderToday();
  });
  await page.waitForTimeout(250);
  const t = `(calm, ${theme}) `;
  check(t + "the Calm mode bar on top is gone", !(await page.locator("#previewCalmNotice").isVisible()));
  check(t + "no icon in Start here", !(await page.locator("#dueBars .preview-focus-icon").isVisible()));
  const today = await box(page, "#dueBars .today-card"), later = await box(page, "#dueBars .preview-later"), imp = await box(page, "#dueBars .preview-important"), list = await box(page, "#paneList");
  check(t + "Also important today is under Later, on the right", imp && later && imp.x >= today.r && imp.y >= later.b && Math.abs(imp.x - later.x) <= 2);
  check(t + "both sides are the same height", Math.abs(today.b - imp.b) <= 2);
  check(t + `the cards are short: the list starts high up (at ${Math.round(list.y)})`, list.y < 640);
  check(t + "no script errors", errs.length === 0);
  if (shots) await page.screenshot({ path: path.join(shots, `split-calm-${theme}.png`) });
  await page.context().close();
}
{
  const { page } = await open(1400, 900, "dark", "list");
  await page.evaluate(() => { tasksData.tasks = [{ id: "a", title: "T", detail: "", sender: "U", state: "open", days: 0, due: "2026-10-14" }, { id: "b", title: "B", detail: "", sender: "X", state: "open", days: 3, due: "2026-10-17" }, { id: "c", title: "C", detail: "", sender: "X", state: "open", days: 5, due: "2026-10-19" }]; dueOpen = false; renderToday(); });
  await page.waitForTimeout(150);
  check("other layouts: Coming up is still a fold with its arrow, closed shows no items", (await page.locator("#dueBars .preview-later .preview-fold-toggle").isVisible()) && (await page.locator("#dueBars .preview-later .trow2:visible").count()) === 0);
  await page.locator("#dueBars .preview-later .tmore").click(); await page.waitForTimeout(200);
  check("other layouts: pressing Coming up opens it (shows its things) and does not go to Tasks", (await page.evaluate(() => dueOpen === true)) && !(await page.evaluate(() => document.body.classList.contains("on-tasks"))));
  check("the classic list layout is unchanged", (await page.evaluate(() => document.body.classList.contains("split-read"))) === false && (await page.locator("#readDock .reading").count()) === 0);
  await page.context().close();
}
{
  const { page } = await open(390, 800, "dark", "right");
  check("on a phone the page can still scroll", await page.evaluate(() => getComputedStyle(document.body).overflow !== "hidden"));
  check("on a phone there is no side panel; an email opens full screen when tapped", (await page.locator("#readDock .reading").count()) === 0 && (await page.locator(".reader").count()) === 0 && await (async () => { await page.locator("article.mail .qmain").first().click(); return (await page.locator(".reader").count()) === 1; })());
  await page.context().close();
}
await b.close(); srv.close();
if (failed) process.exit(1);
