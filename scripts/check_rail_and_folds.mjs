// Browser check for the sidebar rail and the fold arrows: the user button stays in the top bar when the sidebar is narrow,
// the collapse arrow sits on the sidebar edge with the logo centred, the More icon carries its own arrow, and the
// "Coming up" and Calm "Later" panels have an arrow that opens and closes them.
// Uses the demo build (made-up mail, no server). Usage: node scripts/check_rail_and_folds.mjs      Set SHOTS=<folder> to save screenshots.
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



const open = async (calm, collapsed) => {
  const ctx = await b.newContext({ viewport: { width: 1600, height: 900 }, deviceScaleFactor: 1 });
  await ctx.addInitScript((c) => { try { localStorage.setItem("enveliq-calm", c); localStorage.setItem("enveliq-welcome-seen", "1"); } catch {} }, calm ? "1" : "0");
  const p = await ctx.newPage(); p.errors = []; p.on("pageerror", (e) => p.errors.push(String(e)));
  await p.goto(origin + "/"); await p.waitForTimeout(1200);
  await p.evaluate(() => { const d = (n) => { const x = new Date(); x.setDate(x.getDate() + n); return isoLocal(x); };
    for (const [i, t] of [[1, "Select next week's meals"], [10, "Pay the made-up invoice"]]) demoTasks.push({ id: "x" + i, demoId: null, owner: currentUser.id, title: t, detail: "", sender: "Example Sender", priority: "normal", due: d(i), remind_at: null, state: "open", reason: null, closed_at: null, account_id: "", message_id: "", received: 0 });
    syncDemoTasks(); view.layout = "list"; view.rows = "open"; applyView(); render(); });
  if (collapsed) { await p.click("#collapseToggle"); await p.waitForTimeout(450); }
  return [ctx, p];
};
const vis = (p, sel) => p.evaluate((s) => { const e = document.querySelector(s); if (!e) return false; const r = e.getBoundingClientRect(); return r.width > 2 && r.height > 2 && getComputedStyle(e).visibility !== "hidden" && getComputedStyle(e).display !== "none"; }, sel);

{ // wide screen, sidebar narrow
  const [ctx, p] = await open(false, true);
  check("narrow sidebar: the user button is still in the top bar, with the name", await vis(p, ".preview-toolbar #userPill") && await vis(p, ".preview-toolbar #userName"));
  const g = await p.evaluate(() => { const s = document.querySelector("#sidebar").getBoundingClientRect(), t = document.querySelector("#collapseToggle").getBoundingClientRect(), l = [...document.querySelectorAll(".sidebar .brand img, .sidebar .brand-mark, .sidebar .brand svg")].find((e) => e.getBoundingClientRect().width > 4), lr = l && l.getBoundingClientRect(); const av = document.querySelector("#avatar").getBoundingClientRect(); return { edge: s.right, toggleMid: t.left + t.width / 2, logoMid: lr ? lr.left + lr.width / 2 : -1, railMid: s.left + s.width / 2, avRight: av.right, iw: innerWidth }; });
  check("narrow sidebar: the arrow sits on the sidebar edge line", Math.abs(g.toggleMid - g.edge) <= 3);
  check("narrow sidebar: the logo is centred in the rail", Math.abs(g.logoMid - g.railMid) <= 4);
  check("narrow sidebar: the user picture is on screen", g.avRight <= g.iw);
  check("narrow sidebar: the More icon holds its own arrow, with no separate arrow beside it", await vis(p, "#moreToggle .more-chev") && !(await vis(p, "#moreToggle .more-arrow")));
  // the picture is not rebuilt while it is the same
  const same = await p.evaluate(() => { currentUser.avatar = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="; paintAvatar(); const a = document.querySelector("#avatar img"); render(); render(); return a === document.querySelector("#avatar img"); });
  check("the profile picture is kept between refreshes (it does not blink out)", same);
  // Coming up arrow
  const ar = p.locator("[data-due-toggle].always");
  check("Coming up has an arrow that is always there", await ar.count() === 1 && await ar.isVisible());
  check("Coming up starts closed", (await ar.getAttribute("aria-expanded")) === "false" && (await p.locator(".preview-later .trow2:visible").count()) === 0);
  await ar.click(); await p.waitForTimeout(250);
  check("pressing the arrow opens it", (await p.locator(".preview-later .trow2").count()) === 2 && (await p.locator("[data-due-toggle].always").getAttribute("aria-expanded")) === "true");
  await p.locator("[data-due-toggle].always").click(); await p.waitForTimeout(250);
  check("pressing it again closes it", (await p.locator(".preview-later .trow2:visible").count()) === 0);
  check("no script errors (narrow sidebar)", p.errors.length === 0);
  await ctx.close();
}
{ // Customise in the account menu
  const [ctx, p] = await open(false, false);
  await p.click("#userPill"); await p.waitForTimeout(250);
  check("the account menu has a Customise button", await vis(p, "#customiseBtn"));
  await p.click("#customiseBtn"); await p.waitForTimeout(500);
  check("pressing Customise closes the menu", !(await p.evaluate(() => document.querySelector("#userMenu").classList.contains("open"))));
  check("and opens the panel on the right", await p.evaluate(() => document.body.classList.contains("vopen") && document.querySelector("#viewTab").getAttribute("aria-expanded") === "true"));
  if (shots) await p.screenshot({ path: path.join(shots, "customise-open.png") });
  await p.click("#viewPanel [data-view]"); await p.waitForTimeout(250);
  check("pressing a choice inside the panel keeps it open", await p.evaluate(() => document.body.classList.contains("vopen")));
  await p.mouse.click(300, 400); await p.waitForTimeout(400);
  check("clicking outside the panel closes it", await p.evaluate(() => !document.body.classList.contains("vopen") && document.querySelector("#viewTab").getAttribute("aria-expanded") === "false"));
  await p.click("#viewTab"); await p.waitForTimeout(300);
  check("the little arrow still opens it", await p.evaluate(() => document.body.classList.contains("vopen")));
  await p.click("#viewTab"); await p.waitForTimeout(300);
  check("and still closes it", await p.evaluate(() => !document.body.classList.contains("vopen")));
  await ctx.close();
}
{ // Calm mode works the same: the icon buttons are in the Recent emails panel and the filter bar stays hidden
  const [ctx, p] = await open(true, false);
  await p.evaluate(() => document.getElementById("selectAll").click()); await p.waitForTimeout(400);
  check("calm mode, emails ticked: the icon buttons show in the Recent emails panel", await vis(p, "#previewBulk") && (await p.locator("#previewBulk [data-bulk]").count()) === 3);
  check("calm mode, emails ticked: the filter bar stays hidden", !(await vis(p, "#bulk")));
  await ctx.close();
}
{ // ticked-email buttons stay in view when Options is closed
  const [ctx, p] = await open(false, false);
  await p.evaluate(() => { const base = data.filter((m) => m.status === "inbox" && !m.kept); let id = 9000; while (data.filter((m) => m.status === "inbox" && !m.kept && !m._pending).length < 4) data.push({ ...base[0], id: ++id, subject: "Another made-up email " + id, sender: "Example Sender " + id }); render(); });
  await p.locator("[data-select]").nth(0).check(); await p.waitForTimeout(150);
  check("one ticked email: no bulk buttons yet", !(await vis(p, "#previewBulk")));
  await p.locator("[data-select]").nth(1).check(); await p.waitForTimeout(250);
  check("two ticked, Inbox options closed: the buttons show in the Recent emails panel", await p.evaluate(() => { const r = document.querySelector("#previewBulk").getBoundingClientRect(), h = document.querySelector("#previewListHeading").getBoundingClientRect(); return r.width > 50 && r.top >= h.top && r.bottom <= h.bottom + 1 && document.querySelector("#previewSelCount").textContent === "2"; }));
  await p.click("#previewInboxOptions"); await p.waitForTimeout(250);
  check("Inbox options open: the buttons are in the filter bar and not shown twice", !(await vis(p, "#previewBulk")) && await vis(p, "#bulk"));
  await p.click("#previewInboxOptions"); await p.waitForTimeout(250);
  await p.click("#previewBulk [data-bulk=\"archived\"]"); await p.waitForTimeout(300);
  check("pressing Archive in the panel sends both emails away", (await p.locator("article.mail.quiet.leaving").count()) === 2 && !(await vis(p, "#previewBulk")));
  await ctx.close();
}
{ // wide sidebar
  const [ctx, p] = await open(false, false);
  const g = await p.evaluate(() => ({ edge: document.querySelector("#sidebar").getBoundingClientRect().right, t: (() => { const r = document.querySelector("#collapseToggle").getBoundingClientRect(); return r.left + r.width / 2; })() }));
  check("wide sidebar: the arrow sits on the edge line too", Math.abs(g.t - g.edge) <= 3);
  check("wide sidebar: the user button shows the name", await vis(p, ".preview-toolbar #userName"));
  check("wide sidebar: the More row keeps its usual arrow", await vis(p, "#moreToggle .more-arrow") && !(await vis(p, "#moreToggle .more-chev")));
  await ctx.close();
}
{ // Calm mode
  const [ctx, p] = await open(true, false);
  const ar = p.locator("[data-later-toggle].always");
  check("Calm mode: Later has an arrow", await ar.count() === 1 && await ar.isVisible());
  check("Calm mode: Later starts open", (await ar.getAttribute("aria-expanded")) === "true" && (await p.locator(".preview-later .trow2").count()) === 2);
  await ar.click(); await p.waitForTimeout(250);
  check("Calm mode: pressing the arrow closes Later", (await p.locator(".preview-later .trow2:visible").count()) === 0 && (await p.locator(".preview-later [data-later-toggle].always").getAttribute("aria-expanded")) === "false");
  await p.locator(".preview-later [data-later-toggle].always").click(); await p.waitForTimeout(250);
  check("Calm mode: and opens it again", (await p.locator(".preview-later .trow2").count()) === 2);
  check("no script errors (Calm mode)", p.errors.length === 0);
  await ctx.close();
}
await b.close(); srv.close();
process.exit(failed ? 1 : 0);
