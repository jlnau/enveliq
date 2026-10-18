// Browser check for the Reviewed / Archive / Bin buttons that show only while the mouse is over a row (on a computer),
// in the place of the date. Uses the demo build (made-up mail, no server).
// Usage: node scripts/check_hover_actions.mjs      Set SHOTS=<folder> to save screenshots.
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
const op = (p, sel) => p.locator(sel).first().evaluate((e) => +getComputedStyle(e).opacity);
const settle = (p) => p.waitForTimeout(350);

{
  const p = await b.newPage({ viewport: { width: 1180, height: 760 } }); const errors = [];
  p.on("pageerror", (e) => errors.push(String(e)));
  await p.goto(url); await p.waitForTimeout(600);
  await p.evaluate(() => { view.layout = "list"; applyView(); render(); });   // the classic list; the default is now the reading panel on the right
  await p.evaluate(() => { const base = data.find((x) => x.status === "inbox" && x.owner === currentUser.id); ["Electricity bill", "Dentist on Friday", "School form"].forEach((t, i) => data.push({ ...base, id: 9000 + i, subject: t, attachments: i % 2 ? [] : base.attachments })); document.querySelector(".demo-banner")?.remove(); render(); });
  await p.mouse.move(5, 5); await settle(p);
  const rows = p.locator("article.mail"), pair = (i) => rows.nth(i).locator(".qpair"), time = (i) => rows.nth(i).locator(".time");
  const o = (loc) => loc.evaluate((e) => +getComputedStyle(e).opacity);
  check("with the mouse elsewhere, no row shows its buttons", (await o(pair(0))) === 0 && (await o(pair(1))) === 0 && (await o(time(0))) === 1);
  await rows.nth(2).hover(); await settle(p);
  check("the mouse over a row shows that row's three buttons", (await o(pair(2))) === 1 && (await pair(2).locator("button").count()) === 3);
  check("…in the place of its date and paperclip", (await o(time(2))) === 0);
  check("…and the other rows stay as they were", (await o(pair(1))) === 0 && (await o(time(1))) === 1);
  const fits = await rows.nth(2).evaluate((a) => { const r = a.getBoundingClientRect(), q = a.querySelector(".qpair").getBoundingClientRect(), t = a.querySelector(".time").getBoundingClientRect(), s = a.querySelector(".subject").getBoundingClientRect(); return { inside: q.left >= r.left && q.right <= r.right && q.top >= r.top && q.bottom <= r.bottom, overDate: q.right > t.left && q.left < t.right + 40, notOnSubject: q.left >= s.right - 1 || s.right - s.left < q.left - s.left }; });
  check("the buttons sit inside the row, over the date", fits.inside && fits.overDate);
  if (shots) await p.screenshot({ path: path.join(shots, "hover-desktop.png"), clip: { x: 250, y: 300, width: 920, height: 230 } });
  const before = await rows.count();
  await pair(2).locator(".archive").click();
  await p.waitForSelector("#undoBar:not([hidden])");
  check("a button works: Archive greys the email out and shows Undo", (await rows.count()) === before && (await p.locator("article.mail.leaving").count()) === 1);
  await p.mouse.move(5, 5); await settle(p);
  await p.keyboard.press("Tab");
  // Keyboard: a button that has focus shows its row's buttons
  await rows.nth(0).locator(".qic.reviewed").focus(); await settle(p);
  check("a button with the keyboard focus shows its row's buttons", (await o(pair(0))) === 1 && (await o(time(0))) === 0);
  // An open row keeps the buttons it already has
  await rows.nth(1).locator(".qmain").click(); await p.waitForTimeout(300);
  check("an opened email still has its own Reviewed, Archive and Bin buttons", (await p.locator("article.mail.open .qbtns button").count()) === 3);
  check("no script errors", errors.length === 0);
  await p.close();
}
{
  // The reading-pane layout (list beside the email) and the Reviewed list show the same buttons on hover
  const p = await b.newPage({ viewport: { width: 1280, height: 800 } }); const errors = [];
  p.on("pageerror", (e) => errors.push(String(e)));
  await p.goto(url); await p.waitForTimeout(600);
  await p.evaluate(() => { view.layout = "right"; applyView(); render(); });
  await p.mouse.move(5, 5); await settle(p);
  const rows = p.locator("#paneList article.mail"), pair = (i) => rows.nth(i).locator(".qpair"), time = (i) => rows.nth(i).locator(".time");
  const o = (loc) => loc.evaluate((e) => +getComputedStyle(e).opacity);
  check("[reading pane] with the mouse elsewhere, no row shows its buttons", (await o(pair(0))) === 0 && (await o(time(0))) === 1);
  await rows.nth(1).hover(); await settle(p);
  check("[reading pane] the mouse over a row shows its three buttons in place of the date", (await o(pair(1))) === 1 && (await pair(1).locator("button").count()) === 3 && (await o(time(1))) === 0);
  const inside = await rows.nth(1).evaluate((a) => { const r = a.getBoundingClientRect(), q = a.querySelector(".qpair").getBoundingClientRect(); return q.left >= r.left && q.right <= r.right && q.top >= r.top && q.bottom <= r.bottom; });
  check("[reading pane] the buttons sit inside the row", inside);
  if (shots) await p.screenshot({ path: path.join(shots, "hover-reading-pane.png") });
  const n = await rows.count();
  await pair(1).locator(".archive").click();
  await p.waitForSelector("#undoBar:not([hidden])");
  check("[reading pane] a button works: Archive greys the email out and shows Undo", (await rows.count()) === n && (await p.locator("#paneList article.mail.leaving").count()) === 1);
  // A kept email in the Reviewed list gets one button: Remove from this list
  await p.evaluate(() => { const m = data.find((x) => x.owner === currentUser.id && x.status === "inbox"); m.status = "reviewed"; m.kept = true; m.keptUntil = "1 Nov"; filter = "reviewed"; render(); });
  await p.mouse.move(5, 5); await settle(p);
  const kept = p.locator("#paneList article.mail").first();
  await kept.hover(); await settle(p);
  const btns = kept.locator(".qpair button");
  check("[reviewed list] hovering a kept email shows one button, Remove from this list", (await btns.count()) === 1 && (await btns.first().getAttribute("data-status")) === "expired" && (await o(kept.locator(".qpair"))) === 1);
  await p.evaluate(() => { view.layout = "list"; applyView(); render(); });
  const keptList = p.locator("article.mail.quiet").first();
  await p.mouse.move(5, 5); await settle(p); await keptList.hover(); await settle(p);
  check("[reviewed list] the classic list shows it too", (await keptList.locator(".qpair button").count()) === 1 && (await o(keptList.locator(".qpair"))) === 1);
  check("[reading pane] no script errors", errors.length === 0);
  await p.close();
}
{
  const p = await b.newPage({ viewport: { width: 390, height: 780 }, hasTouch: true, isMobile: true });
  await p.goto(url); await p.waitForTimeout(600);
  await p.evaluate(() => { view.layout = "list"; applyView(); render(); });   // the classic list; the default is now the reading panel on the right
  check("on a phone the row buttons stay out of the way (swiping is used)", (await p.locator("article.mail .qpair").first().evaluate((e) => getComputedStyle(e).display)) === "none");
  await p.close();
}
await b.close(); srv.close();
process.exit(failed ? 1 : 0);
