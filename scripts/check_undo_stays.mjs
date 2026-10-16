// Browser check: an email you press Reviewed, Archive or Bin on stays in the list, greyed and pulsing, with a line that runs across
// its bottom for the five seconds, then leaves. Undo puts it back. Works in the list, the deck and on a phone swipe.
// Uses the demo build (made-up mail, no server). Usage: node scripts/check_undo_stays.mjs      Set SHOTS=<folder> to save screenshots.
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
const more = (ms) => { const base = data.find((x) => x.status === "inbox" && x.owner === currentUser.id); ["Electricity bill", "Dentist on Friday", "School form"].forEach((t, i) => data.push({ ...base, id: 9000 + i, subject: t })); window.__undoMs = ms; render(); };
const lineScale = (p) => p.evaluate(() => { const a = document.querySelector("article.leaving"); if (!a) return -1; const t = getComputedStyle(a, "::after").transform; return t === "none" ? 1 : +t.match(/matrix\(([^,]+)/)[1]; });

// 1. The list, on a computer
{
  const p = await b.newPage({ viewport: { width: 1180, height: 820 } }); const errors = []; p.on("pageerror", (e) => errors.push(String(e)));
  await p.goto(url); await p.waitForTimeout(600); await p.evaluate(more, 3000);
  const rows = await p.locator("article.mail").count();
  await p.evaluate(() => queueAction([data.find((x) => x.status === "inbox" && x.owner === currentUser.id)], "trashed"));
  check("list: the email stays in the list after Bin", (await p.locator("article.mail").count()) === rows && (await p.locator("article.mail.leaving.to-trashed").count()) === 1);
  const op = () => p.evaluate(() => +getComputedStyle(document.querySelector("article.leaving .qrow")).opacity);
  check("list: it is greyed out", (await op()) < 0.7);
  await p.waitForTimeout(500); const s1 = await lineScale(p); await p.waitForTimeout(900); const s2 = await lineScale(p);
  check("list: a line runs across its bottom, left to right", s1 > 0 && s2 > s1 && s2 < 1);
  check("list: it cannot be pressed while it waits", await p.evaluate(() => getComputedStyle(document.querySelector("article.leaving")).pointerEvents === "none"));
  if (shots) await p.screenshot({ path: path.join(shots, "undo-stays-desktop.png") });
  await p.waitForTimeout(2000);
  check("list: when the time is up it leaves", (await p.locator("article.mail").count()) === rows - 1 && (await p.locator("article.leaving").count()) === 0);
  await p.evaluate(() => queueAction([data.find((x) => x.status === "inbox" && x.owner === currentUser.id)], "archived"));
  await p.locator("#undoBar button").click();
  check("list: Undo puts it back, no longer greyed", (await p.locator("article.leaving").count()) === 0 && (await p.locator("article.mail").count()) === rows - 1);
  check("list: no script errors", errors.length === 0); await p.close();
}
// 2. Finishing one action must not close a different email's original viewer
{
  const p = await b.newPage({ viewport: { width: 1180, height: 820 } }); const errors = []; p.on("pageerror", (e) => errors.push(String(e)));
  await p.goto(url); await p.waitForTimeout(600);
  await p.evaluate(() => {
    window.__undoMs = 700;
    const inbox = data.filter((x) => x.status === "inbox" && x.owner === currentUser.id);
    const acted = inbox[0], viewed = inbox.find((x) => x.id !== acted.id && x.body);
    queueAction([acted], "trashed");
    openEmailViewer(viewed.id);
    window.__viewerRegression = { acted: acted.id, viewed: viewed.id, subject: viewed.subject };
  });
  check("viewer isolation: a different original email is open during the countdown", await p.evaluate(() => document.getElementById("attachmentModal").classList.contains("open") && document.getElementById("attachmentModalName").textContent === window.__viewerRegression.subject));
  await p.waitForTimeout(1000);
  check("viewer isolation: completing Bin does not close the different original email", await p.evaluate(() => document.getElementById("attachmentModal").classList.contains("open") && document.getElementById("attachmentModalName").textContent === window.__viewerRegression.subject));
  check("viewer isolation: the pending action still completes only for its own email", await p.evaluate(() => !data.some((x) => x.id === window.__viewerRegression.acted && x.status === "inbox")));
  check("viewer isolation: no script errors", errors.length === 0); await p.close();
}
// 2. Reduced motion: still greyed, no pulsing
{
  const p = await b.newPage({ viewport: { width: 1180, height: 820 }, reducedMotion: "reduce" });
  await p.goto(url); await p.waitForTimeout(600); await p.evaluate(more, 3000);
  await p.evaluate(() => queueAction([data.find((x) => x.status === "inbox" && x.owner === currentUser.id)], "reviewed"));
  check("reduced motion: greyed and not pulsing", await p.evaluate(() => { const c = getComputedStyle(document.querySelector("article.leaving .qrow")); return c.animationName === "none" && +c.opacity < 0.7; }));
  await p.close();
}
// 3. The deck: the card stays, then the next one comes
{
  const p = await b.newPage({ viewport: { width: 1180, height: 820 } });
  await p.goto(url); await p.waitForTimeout(600); await p.evaluate(more, 2500);
  await p.evaluate(() => { view.layout = "deck"; applyView(); render(); });
  const title = await p.locator(".dctitle").innerText();
  await p.evaluate(() => queueAction([data.find((x) => x.id === paneId)], "archived"));
  check("deck: the card stays and is greyed", (await p.locator(".dctitle").innerText()) === title && (await p.locator(".deckcard.leaving").count()) === 1);
  await p.waitForTimeout(2900);
  check("deck: when the time is up the next card shows", (await p.locator(".dctitle").innerText()) !== title);
  await p.close();
}
// 4. A phone swipe: the email springs back and waits in place
{
  const p = await b.newPage({ viewport: { width: 390, height: 780 }, hasTouch: true, isMobile: true }); const errors = []; p.on("pageerror", (e) => errors.push(String(e)));
  await p.goto(url); await p.waitForTimeout(600); await p.evaluate(more, 3000);
  await p.evaluate(() => { const l = document.getElementById("list"); window.scrollTo(0, l.getBoundingClientRect().top + scrollY - 70); }); await p.waitForTimeout(200);
  const rows = await p.locator("article.mail.quiet").count();
  const box = await p.locator("article.mail.quiet").nth(1).boundingBox();
  const cdp = await p.context().newCDPSession(p), y = box.y + box.height / 2;
  const touch = (type, x) => cdp.send("Input.dispatchTouchEvent", { type, touchPoints: type === "touchEnd" ? [] : [{ x, y }] });
  await touch("touchStart", 40); for (let x = 40; x <= 300; x += 20) await touch("touchMove", x); await touch("touchEnd");
  await p.waitForTimeout(500);
  check("phone: after a swipe the email stays in the list", (await p.locator("article.mail.quiet").count()) === rows && (await p.locator("article.mail.quiet.leaving").count()) === 1);
  check("phone: it has sprung back into place", await p.evaluate(() => { const a = document.querySelector("article.leaving"); const r = a.getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth; }));
  if (shots) await p.screenshot({ path: path.join(shots, "undo-stays-phone.png") });
  await p.waitForTimeout(3000);
  check("phone: when the time is up it leaves", (await p.locator("article.mail.quiet").count()) === rows - 1);
  check("phone: no script errors", errors.length === 0); await p.close();
}
await b.close(); srv.close();
if (failed) process.exit(1);
